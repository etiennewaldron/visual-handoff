from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import textwrap
from contextlib import contextmanager


READ_ONLY_GIT_COMMANDS = {
    None,
    "",
    "blame",
    "cat-file",
    "describe",
    "diff",
    "for-each-ref",
    "grep",
    "help",
    "log",
    "ls-files",
    "merge-base",
    "rev-parse",
    "show",
    "status",
    "symbolic-ref",
    "version",
}

GLOBAL_OPTIONS_WITH_VALUE = {
    "-C",
    "-c",
    "--attr-source",
    "--exec-path",
    "--git-dir",
    "--namespace",
    "--super-prefix",
    "--work-tree",
}


def extract_git_subcommand(args: list[str]) -> str | None:
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in {"--help", "--version"}:
            return arg.removeprefix("--")
        if arg in GLOBAL_OPTIONS_WITH_VALUE:
            index += 2
            continue
        if arg.startswith("-c") and arg != "-c":
            index += 1
            continue
        if any(
            arg.startswith(prefix)
            for prefix in (
                "--attr-source=",
                "--exec-path=",
                "--git-dir=",
                "--namespace=",
                "--super-prefix=",
                "--work-tree=",
            )
        ):
            index += 1
            continue
        if arg.startswith("-"):
            index += 1
            continue
        return arg
    return None


def is_allowed_git_invocation(args: list[str]) -> bool:
    return extract_git_subcommand(args) in READ_ONLY_GIT_COMMANDS


def build_git_guard_script(real_git_path: str) -> str:
    commands_literal = ", ".join(repr(command) for command in sorted(cmd for cmd in READ_ONLY_GIT_COMMANDS if cmd))
    return textwrap.dedent(
        f"""\
        #!/usr/bin/env python3
        import os
        import sys

        READ_ONLY_GIT_COMMANDS = {{{commands_literal}}}
        GLOBAL_OPTIONS_WITH_VALUE = {sorted(GLOBAL_OPTIONS_WITH_VALUE)!r}


        def extract_git_subcommand(args):
            index = 0
            while index < len(args):
                arg = args[index]
                if arg in ("--help", "--version"):
                    return arg.removeprefix("--")
                if arg in GLOBAL_OPTIONS_WITH_VALUE:
                    index += 2
                    continue
                if arg.startswith("-c") and arg != "-c":
                    index += 1
                    continue
                if any(
                    arg.startswith(prefix)
                    for prefix in (
                        "--attr-source=",
                        "--exec-path=",
                        "--git-dir=",
                        "--namespace=",
                        "--super-prefix=",
                        "--work-tree=",
                    )
                ):
                    index += 1
                    continue
                if arg.startswith("-"):
                    index += 1
                    continue
                return arg
            return None


        command = extract_git_subcommand(sys.argv[1:])
        real_git = os.environ.get("VISUAL_HANDOFF_REAL_GIT", {real_git_path!r})
        if command in READ_ONLY_GIT_COMMANDS or command is None:
            os.execv(real_git, [real_git, *sys.argv[1:]])

        sys.stderr.write(
            "visual-handoff: blocked mutating git command during specialist run: "
            + "git "
            + " ".join(sys.argv[1:])
            + "\\n"
        )
        sys.exit(97)
        """
    )


@contextmanager
def git_guard_environment(enabled: bool) -> tuple[dict[str, str] | None, str | None]:
    if not enabled:
        yield None, None
        return

    real_git = shutil.which("git")
    if real_git is None:
        yield os.environ.copy(), None
        return

    with tempfile.TemporaryDirectory(prefix="visual-handoff-git-guard-") as temp_dir:
        guard_dir = Path(temp_dir)
        guard_path = guard_dir / "git"
        guard_path.write_text(build_git_guard_script(real_git), encoding="utf-8")
        guard_path.chmod(0o755)

        env = os.environ.copy()
        env["PATH"] = f"{guard_dir}{os.pathsep}{env.get('PATH', '')}"
        env["VISUAL_HANDOFF_REAL_GIT"] = real_git
        env["VISUAL_HANDOFF_GIT_POLICY"] = "readonly"
        env["GIT_TERMINAL_PROMPT"] = "0"
        yield env, str(guard_path)


def run_git_readonly(cwd: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None


def capture_git_state(cwd: Path) -> dict[str, str]:
    state: dict[str, str] = {}
    commands = {
        "head": ("rev-parse", "HEAD"),
        "branch": ("symbolic-ref", "--short", "HEAD"),
        "refs": ("for-each-ref", "--format=%(refname) %(objectname)", "refs/heads", "refs/tags", "refs/remotes"),
        "stash": ("stash", "list"),
    }
    for key, command in commands.items():
        result = run_git_readonly(cwd, *command)
        if result is None:
            continue
        if result.returncode == 0:
            state[key] = result.stdout.strip()
        else:
            state[key] = ""
    return state


def detect_git_state_violations(before: dict[str, str], after: dict[str, str]) -> list[str]:
    violations: list[str] = []
    if before.get("head", "") != after.get("head", ""):
        violations.append("Git HEAD changed during specialist run.")
    if before.get("branch", "") != after.get("branch", ""):
        violations.append("Checked-out git branch changed during specialist run.")
    if before.get("refs", "") != after.get("refs", ""):
        violations.append("Git refs changed during specialist run.")
    if before.get("stash", "") != after.get("stash", ""):
        violations.append("Git stash state changed during specialist run.")
    return violations
