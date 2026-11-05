"""Build or install the locked ARMv6 substitutes for the compiled-UI toolchain."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
from urllib.request import urlopen


ESBUILD_VERSION = "0.25.12"
GO_SYS_VERSION = "v0.0.0-20220715151400-c0bba94af5f8"
ROLLUP_VERSION = "4.65.1"
ROLLUP_SHA256 = "8fd2e64dfeaa6334a683ce198e4b6487df44c63f02f3b7843339300b3e5f459a"
ROLLUP_URL = f"https://registry.npmjs.org/@rollup/wasm-node/-/wasm-node-{ROLLUP_VERSION}.tgz"
TOOLS_PATH = "deployment/armv6-ui"
FILES = ("esbuild", "rollup.tgz", "esbuild-notices.txt")
MAX_BYTES = 16 * 1024 * 1024


def _version(manifest):
    return json.loads(manifest.read_text(encoding="utf-8"))["version"]


def check_lock(compiler):
    packages = json.loads((compiler / "package-lock.json").read_text(encoding="utf-8"))["packages"]
    if (packages["node_modules/esbuild"]["version"] != ESBUILD_VERSION
            or packages["node_modules/rollup"]["version"] != ROLLUP_VERSION):
        raise ValueError("ARMv6 compiler pins must match the locked compiler dependencies")


def _rollup_digest(blob):
    if hashlib.sha256(blob).hexdigest() != ROLLUP_SHA256:
        raise ValueError("ARMv6 Rollup archive does not match its pinned digest")


def _read(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"ARMv6 compiler input is missing: {path.name}")
    with path.open("rb") as source:
        blob = source.read(MAX_BYTES + 1)
    if not 0 < len(blob) <= MAX_BYTES:
        raise ValueError("ARMv6 compiler input is outside its size budget")
    return blob


def artifact_inputs(directory):
    binary, rollup, notices = (_read(directory / name) for name in FILES)
    # ELF32 little-endian ARM. Execution on the target below also verifies ISA.
    if binary[:6] != b"\x7fELF\x01\x01" or binary[18:20] != b"\x28\x00":
        raise ValueError("ARMv6 esbuild is not a Linux ARM binary")
    _rollup_digest(rollup)
    return binary, rollup, notices


def prepare(output, compiler):
    check_lock(compiler)
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    with urlopen(ROLLUP_URL, timeout=30) as source:
        rollup = source.read(MAX_BYTES + 1)
    if len(rollup) > MAX_BYTES:
        raise ValueError("ARMv6 Rollup archive is too large")
    _rollup_digest(rollup)
    (output / "rollup.tgz").write_bytes(rollup)
    env = dict(os.environ, GOOS="linux", GOARCH="arm", GOARM="6", CGO_ENABLED="0",
               GOTOOLCHAIN="local", GOBIN="", GOFLAGS="", GOPATH=str(output / ".go"),
               GOPROXY="https://proxy.golang.org", GOSUMDB="sum.golang.org", GONOSUMDB="", GOPRIVATE="")
    # Build twice in the release workflow with the same pinned Go toolchain.
    subprocess.run(["go", "install", "-trimpath", "-buildvcs=false",
                    f"github.com/evanw/esbuild/cmd/esbuild@v{ESBUILD_VERSION}"],
                   check=True, timeout=420, env=env)
    shutil.move(output / ".go/bin/linux_arm/esbuild", output / "esbuild")
    goroot = Path(subprocess.check_output(["go", "env", "GOROOT"], env=env, text=True, timeout=10).strip())
    modules = output / ".go/pkg/mod"
    esbuild = modules / f"github.com/evanw/esbuild@v{ESBUILD_VERSION}"
    sys_module = modules / f"golang.org/x/sys@{GO_SYS_VERSION}"
    notices = [
        ("esbuild LICENSE", esbuild / "LICENSE.md"),
        ("Go LICENSE", goroot / "LICENSE"),
        ("Go PATENTS", goroot / "PATENTS"),
        ("golang.org/x/sys LICENSE", sys_module / "LICENSE"),
        ("golang.org/x/sys PATENTS", sys_module / "PATENTS"),
    ]
    (output / "esbuild-notices.txt").write_bytes(b"\n".join(
        heading.encode("ascii") + b"\n\n" + _read(path) for heading, path in notices
    ))
    artifact_inputs(output)


def install(release):
    compiler = release / "frontend/compiler"
    check_lock(compiler)
    binary, _, _ = artifact_inputs(release / TOOLS_PATH)
    modules = compiler / "node_modules"
    native_rollup = modules / "rollup"
    esbuild = modules / "@esbuild/linux-arm"
    esbuild_binary = esbuild / "bin/esbuild"
    for path in (modules, native_rollup, esbuild, esbuild_binary):
        if path.resolve() != path:
            raise ValueError("Unexpected symlink in the ARMv6 compiler installation")
    if (_version(native_rollup / "package.json") != ROLLUP_VERSION
            or _version(esbuild / "package.json") != ESBUILD_VERSION
            or not esbuild_binary.is_file()):
        raise ValueError("ARMv6 compiler installation does not match the lock")
    with tempfile.TemporaryDirectory(prefix=".armv6-", dir=modules) as work:
        work = Path(work)
        replacement = work / "package"
        with tarfile.open(release / TOOLS_PATH / "rollup.tgz", mode="r:gz") as archive:
            members = archive.getmembers()
            if (len(members) > 256 or sum(item.size for item in members) > MAX_BYTES
                    or any(not item.isfile() or not item.name.startswith("package/")
                           for item in members)):
                raise ValueError("Unexpected ARMv6 Rollup archive contents")
            archive.extractall(work, members=members, filter="data")
        manifest = json.loads((replacement / "package.json").read_text(encoding="utf-8"))
        if (manifest["name"], manifest["version"]) != ("@rollup/wasm-node", ROLLUP_VERSION):
            raise ValueError("ARMv6 Rollup package identity changed")
        native_rollup.rename(work / "native")
        replacement.rename(native_rollup)
        candidate = work / "esbuild"
        candidate.write_bytes(binary)
        candidate.chmod(0o755)
        candidate.replace(esbuild_binary)
    # Cold execution on ARMv6: import Rollup, run a build and launch esbuild.
    subprocess.run(["node", "--input-type=module", "-e",
                    "import {parseAst} from 'rollup/parseAst'; import {transform} from 'esbuild';"
                    "parseAst('export default 1'); await transform('const x: number = 1', {loader:'ts'});"],
                   cwd=compiler, check=True, timeout=120)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "install"))
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.path, Path(__file__).resolve().parents[1] / "frontend/compiler")
    else:
        install(args.path.resolve())
