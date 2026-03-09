from __future__ import annotations

import argparse
from pathlib import Path
import sys

from visual_handoff.config import CONFIG_FILENAME, find_config, load_config
from visual_handoff.core import RunOptions, run_handoff
from visual_handoff.templates import write_init_template


def add_common_handoff_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("role", help="Configured role name, for example 'visual'.")
    parser.add_argument("--goal", required=True, help="Delegated goal statement.")
    parser.add_argument("--platform", help="Optional platform profile, for example 'flutter' or 'web'.")
    parser.add_argument("--cwd", default=".", help="Working directory for the target repository.")
    parser.add_argument("--config", help=f"Path to {CONFIG_FILENAME}. Defaults to searching upward from --cwd.")
    parser.add_argument("--label", help="Optional label for the handoff record.")
    parser.add_argument("--deny", action="append", default=[], help="Denied path. Repeatable.")
    parser.add_argument("--fact", action="append", default=[], help="Fact that must remain true. Repeatable.")
    parser.add_argument(
        "--preserve",
        action="append",
        default=[],
        help="Existing element, behavior, or pattern to preserve. Repeatable.",
    )
    parser.add_argument(
        "--verify",
        action="append",
        default=[],
        help="Verification expectation to pass to the specialist. Repeatable.",
    )
    parser.add_argument("--adapter", help="Override the adapter configured for the role.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write the handoff prompt and logs without invoking the specialist adapter.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="visual-handoff",
        description="Portable handoff runner for controller-led specialist delegation.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize a target repo with starter handoff files.")
    init_parser.add_argument("target", help="Target repository directory.")
    init_parser.add_argument(
        "--template",
        choices=["web", "flutter", "mixed-visual"],
        default="mixed-visual",
        help="Starter template to write.",
    )
    init_parser.add_argument("--force", action="store_true", help="Overwrite existing generated files.")

    run_parser = subparsers.add_parser("run", help="Run a delegated specialist handoff.")
    add_common_handoff_arguments(run_parser)
    run_parser.add_argument("--allow", action="append", default=[], help="Allowed path. Repeatable.")
    run_parser.add_argument("--accept", action="append", default=[], help="Acceptance criterion. Repeatable.")

    assess_parser = subparsers.add_parser("assess", help="Run a delegated read-only visual assessment.")
    add_common_handoff_arguments(assess_parser)
    assess_parser.add_argument(
        "--focus",
        action="append",
        default=[],
        help="Primary path or surface to inspect first. Repeatable.",
    )
    return parser


def cmd_init(args: argparse.Namespace) -> int:
    created = write_init_template(Path(args.target).expanduser().resolve(), args.template, force=args.force)
    for path in created:
        print(path)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    return _cmd_handoff(args, mode="run")


def cmd_assess(args: argparse.Namespace) -> int:
    return _cmd_handoff(args, mode="assess")


def resolve_working_dir(raw_cwd: str) -> Path:
    cwd = Path(raw_cwd).expanduser()
    if not cwd.exists():
        raise ValueError(f"--cwd does not exist: {cwd}")
    if not cwd.is_dir():
        raise ValueError(f"--cwd must be a directory: {cwd}")
    return cwd.resolve()


def _cmd_handoff(args: argparse.Namespace, *, mode: str) -> int:
    cwd = resolve_working_dir(args.cwd)
    if args.config:
        config_path = Path(args.config).expanduser()
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        config_path = config_path.resolve()
    else:
        config_path = find_config(cwd)
    config = load_config(config_path)

    result = run_handoff(
        config,
        RunOptions(
            role=args.role,
            goal=args.goal,
            cwd=cwd,
            platform=args.platform,
            label=args.label,
            allow=getattr(args, "allow", []),
            deny=args.deny,
            accept=getattr(args, "accept", []),
            facts=args.fact,
            preserve=args.preserve,
            verify=args.verify,
            dry_run=args.dry_run,
            adapter_override=args.adapter,
            mode=mode,
            focus=getattr(args, "focus", []),
        ),
    )

    print(f"Handoff record saved to {result.log_dir}")
    if result.policy_violations:
        print(f"Policy violations recorded in {result.log_dir / 'policy-violations.txt'}")
    if result.dry_run:
        print("Dry run complete. Adapter was not invoked.")
    return result.exit_code


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "init":
            return cmd_init(args)
        if args.command == "run":
            return cmd_run(args)
        if args.command == "assess":
            return cmd_assess(args)
        parser.error(f"Unknown command: {args.command}")
        return 2
    except (FileExistsError, FileNotFoundError, ValueError) as exc:
        print(f"visual-handoff: {exc}", file=sys.stderr)
        return 1
