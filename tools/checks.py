"""Plan proportionate repository checks; execute only with --run (stdlib only)."""

from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
from dataclasses import dataclass


PYTHON_SUITES = (
    "backend/tests", "agent/tests", "three_mm_protocol/tests",
    "three_mm_provisioning/tests", "three_mm_runtime/tests", "three_mm_web/tests",
    "three_mm_public_web/tests", "setup_service/tests", "deployment/tests",
    "three_mm_application_sdk/tests",
)
# Production Python remains one integration group until its consumers are audited.
# Narrowing it by filenames would guess at authority/runtime/installer dependencies.
PYTHON_ROOTS = {suite.split("/")[0] for suite in PYTHON_SUITES}
DOC_SUFFIXES = {".md", ".rst"}


@dataclass(frozen=True)
class Plan:
    python: tuple[str, ...] = ()
    frontend: bool = False
    tooling: bool = False
    reasons: tuple[str, ...] = ()


def full_plan(reason: str) -> Plan:
    return Plan(PYTHON_SUITES, True, True, (reason,))


def select_checks(paths: list[str]) -> Plan:
    selected: set[str] = set()
    frontend = tooling = False
    reasons: set[str] = set()
    for raw in paths:
        path = raw.replace("\\", "/")
        parts = PurePosixPath(path).parts
        if not parts or path.startswith("/") or ":" in path or ".." in parts:
            return full_plan("Unrecognized path: use full checks")
        root = parts[0]
        suffix = PurePosixPath(path).suffix.lower()
        # Executable examples and config files inside docs are NOT documentation.
        if suffix in DOC_SUFFIXES or path in {"LICENSE", "LICENSE.txt", "COPYING"}:
            continue
        if path in {".github/workflows/ci.yml", ".github/workflows/release.yml"} or root == "tools":
            return full_plan("Check selection or workflow changed: validate all groups")
        if root == "frontend":
            frontend = True
            reasons.add("frontend changed")
            continue
        if root in PYTHON_ROOTS:
            if (suffix == ".py" and len(parts) > 2 and parts[1] == "tests"
                    and PurePosixPath(path).name.startswith("test_")
                    and root != "deployment"):
                selected.add(f"{root}/tests")
                reasons.add(f"test-only change: {root}")
            else:
                selected.update(PYTHON_SUITES)
                reasons.add(f"Python integration boundary: {root}")
            continue
        # Includes dependency locks, root scripts/config, unknown/new components.
        return full_plan(f"Unmapped input: {path}; use full checks")
    return Plan(tuple(p for p in PYTHON_SUITES if p in selected), frontend, tooling,
                tuple(sorted(reasons)) or ("No executable changes detected",))


def git_paths(repo: Path, *arguments: str) -> list[str]:
    result = subprocess.run(["git", *arguments], cwd=repo, check=True, capture_output=True)
    return [os.fsdecode(p) for p in result.stdout.split(b"\0") if p]


def changed_paths(repo: Path, base: str | None, head: str) -> list[str]:
    if base is not None:
        if not base or set(base) == {"0"}:
            raise ValueError("No usable base commit (manual run or first push)")
        commits = []
        for ref in (base, head):
            result = subprocess.run(["git", "rev-parse", "--verify", "--end-of-options",
                                     f"{ref}^{{commit}}"], cwd=repo, check=True, capture_output=True)
            commit = result.stdout.decode("ascii").strip()
            if len(commit) not in (40, 64) or any(c not in "0123456789abcdef" for c in commit):
                raise ValueError("Cannot resolve comparison commit")
            commits.append(commit)
        # Disable rename detection so BOTH the old and new component are selected.
        return git_paths(repo, "diff", "--no-renames", "--name-only", "-z", *commits, "--")
    paths = git_paths(repo, "diff", "--no-renames", "--name-only", "-z")
    paths += git_paths(repo, "diff", "--cached", "--no-renames", "--name-only", "-z")
    paths += git_paths(repo, "ls-files", "--others", "--exclude-standard", "-z")
    return sorted(set(paths))


def commands(plan: Plan, only: str, python: str) -> list[tuple[str, list[str]]]:
    result = []
    if plan.tooling and only in {"all", "tooling"}:
        result.append((".", [python, "-m", "unittest", "discover", "-s", "tools/tests", "-v"]))
    if plan.python and only in {"all", "python"}:
        # Keep the existing two-process boundary between default and SDK/deployment.
        extra = {"deployment/tests", "three_mm_application_sdk/tests"}
        for group in (tuple(p for p in plan.python if p not in extra),
                      tuple(p for p in plan.python if p in extra)):
            if group:
                result.append((".", [python, "-m", "pytest", "-q", *group]))
    if plan.frontend and only in {"all", "frontend"}:
        pnpm = shutil.which("pnpm") or "pnpm"
        for args in (("test:unit", "--", "--run"), ("type-check",), ("build-only",)):
            result.append(("frontend", [pnpm, "run", *args]))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--base", help="Compare this ref with --head (CI)")
    source.add_argument("--paths", nargs="+", help="Explicit changed paths; planning only")
    source.add_argument("--full", action="store_true", help="All existing suites plus tooling")
    parser.add_argument("--head", default="HEAD")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--run", action="store_true", help="Execute selected checks, stopping on failure")
    parser.add_argument("--only", choices=("all", "python", "frontend", "tooling"), default="all")
    parser.add_argument("--github-output", type=Path, help="Append boolean job outputs to this file")
    args = parser.parse_args(argv)
    if args.paths and args.run:
        parser.error("--paths is a planning preview; use actual Git changes or --full to run")
    if args.full:
        plan = full_plan("Explicit full check")
    else:
        try:
            paths = args.paths if args.paths is not None else changed_paths(args.repo, args.base, args.head)
            plan = select_checks(paths)
        except (OSError, ValueError, subprocess.CalledProcessError):
            plan = full_plan("Cannot establish the changed paths: use full checks")
    print("; ".join(plan.reasons), flush=True)
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as output:
            for name, enabled in (("python", bool(plan.python)), ("frontend", plan.frontend),
                                  ("tooling", plan.tooling)):
                output.write(f"{name}={str(enabled).lower()}\n")
    for relative, command in commands(plan, args.only, sys.executable):
        print(f"[{relative}] {subprocess.list2cmdline(command)}", flush=True)
        if args.run:
            try:
                result = subprocess.run(command, cwd=args.repo / relative, check=False)
            except OSError as error:
                print(f"Cannot start check: {error}", file=sys.stderr)
                return 2
            if result.returncode:
                return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
