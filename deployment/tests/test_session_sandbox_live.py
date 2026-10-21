"""Opt-in root acceptance on a disposable Linux systemd host, never owner data.

THREE_MM_RUN_SESSION_SANDBOX_TESTS=1 and THREE_MM_TERMINAL_SOURCE are required.
Creates only uniquely named /run units and /opt code fixtures, then removes them.
Does not edit/start/stop installed 3mm units, approve authority or run on hardware.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]
ENABLED = os.getenv("THREE_MM_RUN_SESSION_SANDBOX_TESTS") == "1"
pytestmark = pytest.mark.skipif(
    not ENABLED, reason="Explicit disposable systemd acceptance only"
)


def test_actual_socket_activated_pty_sandbox_and_owned_cleanup():
    assert os.geteuid() == 0 and Path("/run/systemd/system").is_dir()
    assert os.getenv("WSL_DISTRO_NAME") in (
        None,
        "3mm-WP4-Test",
    ), "Never test on owner Hub WSL"
    terminal = Path(os.environ["THREE_MM_TERMINAL_SOURCE"]).resolve()
    assert (terminal / "provider/terminal_provider/runtime.py").is_file()
    directory = Path(tempfile.mkdtemp(prefix="3mm-m21-session-", dir="/opt"))
    directory.chmod(0o755)
    name = "3mm-session-worker-acceptance" + uuid4().hex[:8]
    unit_root = Path("/run/systemd/system")
    service_path = unit_root / (name + "@.service")
    socket_path = unit_root / (name + ".socket")
    endpoint = directory / "worker.sock"
    assert not service_path.exists() and not socket_path.exists()

    def run(*arguments, **kwargs):
        result = subprocess.run(
            arguments, capture_output=True, text=True, timeout=35, **kwargs
        )
        assert result.returncode == 0, (result.stdout, result.stderr)
        return result

    try:
        for package in (
            "three_mm_runtime",
            "three_mm_protocol",
            "three_mm_application_sdk",
            "three_mm_provisioning",
        ):
            shutil.copytree(
                ROOT / package,
                directory / package,
                ignore=shutil.ignore_patterns("__pycache__"),
            )
        unit = (ROOT / "deployment/systemd/3mm-session-worker@.service").read_text()
        unit = unit.replace(
            "WorkingDirectory=/opt/3mm/current", "WorkingDirectory=" + str(directory)
        )
        service_path.write_text(unit)
        socket_path.write_text(
            "[Socket]\nListenStream="
            + str(endpoint)
            + "\nSocketUser=root\nSocketGroup=3mm\nSocketMode=0660\nAccept=yes\nMaxConnections=4\nRemoveOnStop=yes\n"
        )
        # Test wheel is deliberately not published/reviewed; no installed state.
        import io
        import zipfile

        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            for source in sorted(
                (terminal / "provider/terminal_provider").glob("*.py")
            ):
                archive.writestr(
                    "terminal_provider/" + source.name, source.read_bytes()
                )
            archive.writestr(
                "terminal-0.dist-info/WHEEL",
                "Root-Is-Purelib: true\nTag: py3-none-any\n",
            )
        (directory / "fixture.whl").write_bytes(stream.getvalue())
        script = directory / "client.py"
        script.write_text(
            """
import asyncio, json, os, sys
from pathlib import Path
from three_mm_runtime import session_worker_client as ipc

async def main():
    ipc.SOCKET_PATH = Path(sys.argv[1])
    provider = ipc.SandboxedSessionProvider(wheel=Path("fixture.whl").read_bytes(),
        factory="terminal_provider.runtime:create_provider", provider_id="org.3mm.terminal")
    sid = "ses_" + "a" * 32
    await provider.open({"session_id": sid, "device_id": "dev_" + "a" * 32,
        "capability_id": "org.3mm.terminal.shell", "access_mode": "write", "options": {"cols":80,"rows":24}})
    output = bytearray()
    async def until(marker):
        while marker not in output:
            chunk = await provider.read_output(sid)
            assert chunk is not None
            output.extend(chunk)
    await asyncio.wait_for(until(b"3mm> "), 5)
    await provider.control(sid, {"action":"resize","arguments":{"cols":101,"rows":37}})
    # Read actual OS facts INSIDE the shell, not inferred from unit settings.
    program = "import os,socket,json; from pathlib import Path; r={'uid':os.geteuid(),'size':list(os.get_terminal_size(0)),'cwd':os.getcwd(),'env':dict(os.environ),'blocked':{p:not os.access(p,os.R_OK|os.X_OK) for p in ['/etc/3mm','/var/lib/3mm','/run/3mm','/mnt','/home','/root']}};\\ntry: socket.socket(socket.AF_INET); r['network']=True\\nexcept OSError: r['network']=False\\nprint('FACTS:'+json.dumps(r))"
    await provider.receive(sid, ("python3 -c " + __import__('shlex').quote(program) + "\\n").encode())
    # The echoed command includes FACTS:; distinguish the actual JSON result.
    await asyncio.wait_for(until(b'FACTS:{'), 5)
    while b'\\r\\n3mm> ' not in output[output.index(b'FACTS:{'):]:
        output.extend(await provider.read_output(sid))
    line = bytes(output[output.index(b'FACTS:{') + 6:]).split(b'\\r\\n',1)[0]
    facts = json.loads(line)
    assert 61184 <= facts['uid'] <= 65519 and facts['size'] == [101,37], facts
    assert all(facts['blocked'].values()) and facts['network'] is False, facts
    assert not any('TOKEN' in k or 'KEY' in k or 'DATABASE' in k for k in facts['env']), facts
    assert facts['cwd'].startswith('/tmp/terminal-work-'), facts
    await provider.receive(sid, b"sleep 0.05; printf 'ASYNC_OK\\n'\\n")
    await asyncio.wait_for(until(b'ASYNC_OK\\r\\n'), 5)
    # Deliberately escape the shell's process group, but NOT its systemd cgroup.
    await provider.receive(sid, b"setsid sh -c 'echo $$ > orphan.pid; exec sleep 600' &\\n")
    await provider.receive(sid, b"while [ ! -s orphan.pid ]; do sleep 0.01; done; printf 'ORPHAN:%s\\n' $(cat orphan.pid)\\n")
    await asyncio.wait_for(until(b'ORPHAN:'), 5)
    # The echoed command can contain ORPHAN:, so read the actual numeric line.
    import re
    while not re.search(rb'ORPHAN:(\\d+)', output):
        output.extend(await provider.read_output(sid))
    orphan = int(re.search(rb'ORPHAN:(\\d+)', output)[1])
    await provider.close(sid, 'acceptance')
    # A second session must be cleaned even when Core loses the socket abruptly.
    second = ipc.SandboxedSessionProvider(wheel=Path("fixture.whl").read_bytes(),
        factory="terminal_provider.runtime:create_provider", provider_id="org.3mm.terminal")
    await second.open({"session_id": "ses_" + "b" * 32, "device_id": "dev_" + "a" * 32,
        "capability_id": "org.3mm.terminal.shell", "access_mode": "write", "options": {"cols":80,"rows":24}})
    assert await second.read_output(second.session_id)
    second.writer.close()
    await second.writer.wait_closed()
    await second._wait_empty()
    await asyncio.gather(second.receiving, return_exceptions=True)
    print(json.dumps({'sandbox':facts,'prompt_before_input':True,'resize':True,'async_output':True,'closed':True,'orphan_pid':orphan,'link_loss_cleanup':True}))
asyncio.run(asyncio.wait_for(main(),25))
"""
        )
        run("systemctl", "daemon-reload")
        run("systemctl", "start", name + ".socket")
        result = run(
            "runuser",
            "-u",
            "3mm",
            "--",
            "/opt/3mm/current/.venv/bin/python",
            str(script),
            str(endpoint),
            cwd=directory,
        )
        facts = json.loads(result.stdout.strip())
        assert facts["prompt_before_input"] and facts["closed"]
        # Compose the actual sealed M20/browser boundary with the SAME sandbox,
        # as the Core UID, using a second independent SDK provider.
        for package in (
            "backend",
            "agent",
            "three_mm_public_web",
            "three_mm_web",
            "deployment",
        ):
            shutil.copytree(
                ROOT / package,
                directory / package,
                ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"),
            )
        shutil.copytree(ROOT / "frontend/compiler", directory / "frontend/compiler")
        shutil.copy2(ROOT / "VERSION", directory / "VERSION")
        integration = directory / "integration.py"
        integration_source = """
import os,sys,tempfile
sys.path.insert(0,PYTEST_PATH)
temporary = tempfile.TemporaryDirectory(prefix="3mm-m21-browser-fixture-")
os.environ["DATABASE_URL"]="sqlite:///"+temporary.name+"/entry.db"
os.environ["UPLOADS_DIR"]=temporary.name+"/uploads"
os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"]="1"
os.environ["THREE_MM_TEST_SESSION_SOCKET"]=sys.argv[1]
import pytest
raise SystemExit(pytest.main(["-xq","--tb=short","-p","no:cacheprovider","backend/tests/test_application_session_worker_integration.py"]))
"""
        integration.write_text(
            integration_source.replace(
                "PYTEST_PATH", repr(str(Path(pytest.__file__).resolve().parent.parent))
            )
        )
        result = run(
            "runuser",
            "-u",
            "3mm",
            "--",
            "/opt/3mm/current/.venv/bin/python",
            str(integration),
            str(endpoint),
            cwd=directory,
        )
        assert "2 passed" in result.stdout, result.stdout
        facts["m20_browser_sandbox"] = True
        # Unit must end, not merely return a cosmetic close acknowledgement.
        run("systemctl", "stop", name + ".socket")
        instances = run(
            "systemctl",
            "list-units",
            "--all",
            "--plain",
            "--no-legend",
            name + "@*.service",
        ).stdout
        assert (
            " running " not in instances and " stop-sigterm " not in instances
        ), instances
        print(json.dumps(facts, sort_keys=True))
    finally:
        subprocess.run(
            ["systemctl", "stop", name + ".socket", name + "@*.service"],
            capture_output=True,
            timeout=15,
        )
        service_path.unlink(missing_ok=True)
        socket_path.unlink(missing_ok=True)
        subprocess.run(["systemctl", "daemon-reload"], capture_output=True, timeout=15)
        subprocess.run(
            ["systemctl", "reset-failed", name + ".socket", name + "@*.service"],
            capture_output=True,
            timeout=15,
        )
        assert directory.parent == Path("/opt") and directory.name.startswith(
            "3mm-m21-session-"
        )
        shutil.rmtree(directory)
