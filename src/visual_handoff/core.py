from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable
import hashlib
import os
import re

from visual_handoff.adapters import AdapterResult, build_adapter
from visual_handoff.config import AppConfig, ScopeConfig
from visual_handoff.git_safety import capture_git_state, detect_git_state_violations, git_guard_environment, run_git_readonly
from visual_handoff.profiles import load_profile


RUN_SECTION_NAMES = [
    "STATUS",
    "SUMMARY",
    "FILES_CHANGED",
    "CHECKS_RUN",
    "BLOCKERS",
    "NEXT_FOR_CONTROLLER",
]

ASSESS_SECTION_NAMES = [
    "STATUS",
    "SUMMARY",
    "VISUAL_ISSUES",
    "SUGGESTED_WRITE_SCOPE",
    "PRESERVE",
    "ACCEPTANCE_CRITERIA",
    "CHECKS_RUN",
    "BLOCKERS",
    "NEXT_FOR_CONTROLLER",
]

RUN_SECTION_FILES = {
    "STATUS": "status.txt",
    "SUMMARY": "summary.txt",
    "FILES_CHANGED": "files-changed.txt",
    "CHECKS_RUN": "checks-run.txt",
    "BLOCKERS": "blockers.txt",
    "NEXT_FOR_CONTROLLER": "next-for-controller.txt",
}

ASSESS_SECTION_FILES = {
    "STATUS": "status.txt",
    "SUMMARY": "summary.txt",
    "VISUAL_ISSUES": "visual-issues.txt",
    "SUGGESTED_WRITE_SCOPE": "suggested-write-scope.txt",
    "PRESERVE": "preserve.txt",
    "ACCEPTANCE_CRITERIA": "acceptance-criteria.txt",
    "CHECKS_RUN": "checks-run.txt",
    "BLOCKERS": "blockers.txt",
    "NEXT_FOR_CONTROLLER": "next-for-controller.txt",
}


@dataclass(slots=True)
class RunOptions:
    role: str
    goal: str
    cwd: Path
    platform: str | None
    label: str | None
    allow: list[str]
    deny: list[str]
    accept: list[str]
    facts: list[str]
    preserve: list[str]
    verify: list[str]
    dry_run: bool
    adapter_override: str | None = None
    mode: str = "run"
    focus: list[str] = field(default_factory=list)


@dataclass(slots=True)
class HandoffResult:
    log_dir: Path
    exit_code: int
    policy_violations: list[str]
    touched_paths: list[str]
    dry_run: bool


@dataclass(slots=True)
class MergedScope:
    adapter: str
    profiles: list[str]
    instructions: list[str]
    allow: list[str]
    deny: list[str]
    accept: list[str]
    verify: list[str]


@dataclass(slots=True)
class WorkflowSpec:
    mode: str
    section_names: list[str]
    section_files: dict[str, str]


def _merge_unique(*values: Iterable[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in values:
        for item in group:
            if item not in seen:
                seen.add(item)
                merged.append(item)
    return merged


def workflow_spec(mode: str) -> WorkflowSpec:
    if mode == "run":
        return WorkflowSpec(mode=mode, section_names=RUN_SECTION_NAMES, section_files=RUN_SECTION_FILES)
    if mode == "assess":
        return WorkflowSpec(mode=mode, section_names=ASSESS_SECTION_NAMES, section_files=ASSESS_SECTION_FILES)
    raise ValueError(f"Unsupported handoff mode: {mode}")


def merge_scope(role: ScopeConfig, platform: ScopeConfig | None, options: RunOptions) -> MergedScope:
    adapter = options.adapter_override or (platform.adapter if platform else None) or role.adapter or "gemini"
    return MergedScope(
        adapter=adapter,
        profiles=_merge_unique(role.profiles, platform.profiles if platform else [], []),
        instructions=_merge_unique(role.instructions, platform.instructions if platform else []),
        allow=_merge_unique(role.default_allow, platform.default_allow if platform else [], options.allow),
        deny=_merge_unique(role.default_deny, platform.default_deny if platform else [], options.deny),
        accept=_merge_unique(role.default_accept, platform.default_accept if platform else [], options.accept),
        verify=_merge_unique(role.default_verify, platform.default_verify if platform else [], options.verify),
    )


def format_list(items: list[str], empty: str = "- none") -> str:
    if not items:
        return f"{empty}\n"
    return "".join(f"- {item}\n" for item in items)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-")
    return slug or "handoff"


def _build_run_prompt(config: AppConfig, options: RunOptions, scope: MergedScope, profile_texts: list[str]) -> tuple[str, str, str]:
    project_instructions = config.project.instructions
    platform_line = f"- Platform target: {options.platform}\n" if options.platform else ""

    context = (
        "Handoff contract:\n"
        f"- This is a delegated {options.role} step. {config.toolkit.controller} will review and integrate after you finish.\n"
        f"- {config.toolkit.specialist} owns the visual assessment and implementation for this delegated slice. Stop after this step.\n"
        "- You may inspect adjacent surfaces, shared components, themes, styles, assets, and screenshots broadly enough to understand the current visual language and avoid isolated UI changes.\n"
        "- Restrict edits to allowed paths when they are provided.\n"
        "- Never edit denied paths.\n"
        "- If the task truly requires a non-delegated change, stop and explain it in NEXT_FOR_CONTROLLER.\n"
        "- Never interact with databases or persistence systems. Do not connect to local or remote databases, do not run migrations or seed scripts, do not change schemas, queries, ORM models, or persistence configuration. If a visual change truly requires a supporting data-layer change, stop and explain it in NEXT_FOR_CONTROLLER.\n"
        "- Never use git to mutate the working tree, index, refs, or remotes. Do not run commands such as `git checkout`, `git switch`, `git restore`, `git reset`, `git revert`, `git add`, `git rm`, `git mv`, `git stash`, `git commit`, `git merge`, `git rebase`, `git cherry-pick`, `git am`, `git apply`, `git branch` creation/deletion, `git tag`, `git fetch`, `git pull`, or `git push`. If you think one is required, stop and explain it in NEXT_FOR_CONTROLLER.\n"
        f"{platform_line}\n"
        "Allowed paths:\n"
        f"{format_list(scope.allow)}"
        "\nDenied paths:\n"
        f"{format_list(scope.deny)}"
        "\nFacts to preserve:\n"
        f"{format_list(options.facts)}"
        "\nExisting elements to preserve:\n"
        f"{format_list(options.preserve)}"
        "\nAcceptance criteria:\n"
        f"{format_list(scope.accept)}"
        "\nVerification expectations:\n"
        f"{format_list(scope.verify)}"
        "\nAt the end, respond in plain text with these exact sections and no code fences. Use bullet lines under each section. If a section has nothing to report, write \"- none\".\n"
        "STATUS:\n"
        "SUMMARY:\n"
        "FILES_CHANGED:\n"
        "CHECKS_RUN:\n"
        "BLOCKERS:\n"
        "NEXT_FOR_CONTROLLER:\n"
    )

    prompt = (
        f"You are {config.toolkit.specialist}, the specialist agent for this delegated {options.role} task.\n\n"
        "Follow the role and platform guidance below closely.\n\n"
        "Built-in profiles:\n"
        + "\n\n".join(profile_texts)
        + "\n\nProject instructions:\n"
        + format_list(project_instructions)
        + ("\nAdditional scoped instructions:\n" + format_list(scope.instructions) if scope.instructions else "")
        + "\n"
        + context
        + "\nTask:\n"
        + options.goal
    )

    request_text = (
        f"Mode: run\n"
        f"Role: {options.role}\n"
        f"Platform: {options.platform or 'none'}\n"
        f"Goal: {options.goal}\n"
        f"Label: {options.label or options.role}\n\n"
        "Allowed paths:\n"
        f"{format_list(scope.allow).rstrip()}\n\n"
        "Denied paths:\n"
        f"{format_list(scope.deny).rstrip()}\n\n"
        "Facts to preserve:\n"
        f"{format_list(options.facts).rstrip()}\n\n"
        "Existing elements to preserve:\n"
        f"{format_list(options.preserve).rstrip()}\n\n"
        "Acceptance criteria:\n"
        f"{format_list(scope.accept).rstrip()}\n\n"
        "Verification expectations:\n"
        f"{format_list(scope.verify).rstrip()}\n"
    )

    return prompt, context, request_text


def _build_assess_prompt(config: AppConfig, options: RunOptions, scope: MergedScope, profile_texts: list[str]) -> tuple[str, str, str]:
    project_instructions = config.project.instructions
    platform_line = f"- Platform target: {options.platform}\n" if options.platform else ""

    context = (
        "Assessment contract:\n"
        f"- This is a delegated {options.role} assessment step. {config.toolkit.controller} will review your assessment and decide whether to approve a follow-up implementation.\n"
        f"- {config.toolkit.specialist} owns the visual critique for this step. Evaluate the current UI, interaction clarity, layout, hierarchy, rhythm, responsiveness, and polish.\n"
        "- You may inspect the repository broadly enough to understand shared visual language, neighboring surfaces, themes, styles, assets, and screenshots relevant to the task.\n"
        "- This step is read-only. Do not create, modify, rename, or delete files.\n"
        "- Avoid denied paths when they are provided.\n"
        "- Never interact with databases or persistence systems. Do not connect to local or remote databases, do not run migrations or seed scripts, do not change schemas, queries, ORM models, or persistence configuration.\n"
        "- Never use git to mutate the working tree, index, refs, or remotes. Do not run commands such as `git checkout`, `git switch`, `git restore`, `git reset`, `git revert`, `git add`, `git rm`, `git mv`, `git stash`, `git commit`, `git merge`, `git rebase`, `git cherry-pick`, `git am`, `git apply`, `git branch` creation/deletion, `git tag`, `git fetch`, `git pull`, or `git push`.\n"
        f"{platform_line}\n"
        "Primary focus areas:\n"
        f"{format_list(options.focus, empty='- none specified; inspect the most relevant visual surfaces for the task.')}"
        "\nDenied paths:\n"
        f"{format_list(scope.deny)}"
        "\nFacts to preserve:\n"
        f"{format_list(options.facts)}"
        "\nExisting elements to preserve:\n"
        f"{format_list(options.preserve)}"
        "\nVerification priorities:\n"
        f"{format_list(scope.verify)}"
        "\nAt the end, respond in plain text with these exact sections and no code fences. Use bullet lines under each section. If a section has nothing to report, write \"- none\".\n"
        "STATUS:\n"
        "SUMMARY:\n"
        "VISUAL_ISSUES:\n"
        "SUGGESTED_WRITE_SCOPE:\n"
        "PRESERVE:\n"
        "ACCEPTANCE_CRITERIA:\n"
        "CHECKS_RUN:\n"
        "BLOCKERS:\n"
        "NEXT_FOR_CONTROLLER:\n"
    )

    prompt = (
        f"You are {config.toolkit.specialist}, the specialist agent for this delegated {options.role} assessment.\n\n"
        "Follow the role and platform guidance below closely.\n\n"
        "Built-in profiles:\n"
        + "\n\n".join(profile_texts)
        + "\n\nProject instructions:\n"
        + format_list(project_instructions)
        + ("\nAdditional scoped instructions:\n" + format_list(scope.instructions) if scope.instructions else "")
        + "\n"
        + context
        + "\nTask:\n"
        + options.goal
    )

    request_text = (
        f"Mode: assess\n"
        f"Role: {options.role}\n"
        f"Platform: {options.platform or 'none'}\n"
        f"Goal: {options.goal}\n"
        f"Label: {options.label or f'assess-{options.role}'}\n\n"
        "Primary focus areas:\n"
        f"{format_list(options.focus, empty='- none specified').rstrip()}\n\n"
        "Denied paths:\n"
        f"{format_list(scope.deny).rstrip()}\n\n"
        "Facts to preserve:\n"
        f"{format_list(options.facts).rstrip()}\n\n"
        "Existing elements to preserve:\n"
        f"{format_list(options.preserve).rstrip()}\n\n"
        "Verification priorities:\n"
        f"{format_list(scope.verify).rstrip()}\n"
    )

    return prompt, context, request_text


def build_prompt(config: AppConfig, options: RunOptions, scope: MergedScope) -> tuple[str, str, str]:
    profile_texts = [load_profile(name) for name in scope.profiles]
    if options.mode == "assess":
        return _build_assess_prompt(config, options, scope, profile_texts)
    return _build_run_prompt(config, options, scope, profile_texts)


def _hash_file(path: Path) -> str:
    if not path.exists() and not path.is_symlink():
        return "DELETED"
    if path.is_dir():
        return "DIRECTORY"
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def detect_repo_mode(cwd: Path) -> str:
    result = run_git_readonly(cwd, "rev-parse", "--show-toplevel")
    if result and result.returncode == 0:
        return "git"
    return "filesystem"


def should_ignore_path(rel_path: str, cwd: Path, *, ignore_names: list[str], output_dir: Path) -> bool:
    path = cwd / rel_path
    if path.resolve().is_relative_to(output_dir.resolve()):
        return True
    parts = Path(rel_path).parts
    return any(part in ignore_names for part in parts)


def snapshot_workspace(cwd: Path, *, ignore_names: list[str], output_dir: Path, mode: str) -> dict[str, str]:
    if mode == "git":
        result = run_git_readonly(cwd, "ls-files", "-z", "-m", "-d", "-o", "--exclude-standard")
        if result is None or result.returncode != 0:
            return {}
        entries = result.stdout.split("\x00")
        snapshot: dict[str, str] = {}
        for entry in entries:
            if not entry:
                continue
            if should_ignore_path(entry, cwd, ignore_names=ignore_names, output_dir=output_dir):
                continue
            path = cwd / entry
            snapshot[entry] = _hash_file(path)
        return snapshot

    snapshot = {}
    output_resolved = output_dir.resolve()
    ignore_set = set(ignore_names)
    for root, dirs, files in os.walk(cwd):
        root_path = Path(root)
        dirs[:] = [
            name
            for name in dirs
            if name not in ignore_set and not (root_path / name).resolve().is_relative_to(output_resolved)
        ]
        for filename in files:
            if filename in ignore_set:
                continue
            path = root_path / filename
            if path.resolve().is_relative_to(output_resolved):
                continue
            rel = path.relative_to(cwd).as_posix()
            snapshot[rel] = _hash_file(path)
    return snapshot


def write_snapshot(path: Path, snapshot: dict[str, str]) -> None:
    lines = [f"{rel}\t{digest}\n" for rel, digest in sorted(snapshot.items())]
    path.write_text("".join(lines), encoding="utf-8")


def diff_snapshots(before: dict[str, str], after: dict[str, str]) -> list[str]:
    touched = []
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            touched.append(key)
    return touched


def path_in_scope(path: str, scope: str) -> bool:
    clean_scope = scope.rstrip("/")
    return path == clean_scope or path.startswith(clean_scope + "/")


def path_matches(path: str, scopes: list[str]) -> bool:
    return any(path_in_scope(path, scope) for scope in scopes if scope)


def extract_sections(text: str, section_names: list[str]) -> dict[str, list[str]]:
    sections = {name: [] for name in section_names}
    current: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line in {f"{name}:" for name in section_names}:
            current = line[:-1]
            continue
        if re.match(r"^[A-Z_]+:$", line):
            current = None
            continue
        if current is not None:
            sections[current].append(line)

    return sections


def write_sections(log_dir: Path, sections: dict[str, list[str]], mapping: dict[str, str]) -> None:
    for name, filename in mapping.items():
        content = "\n".join(sections.get(name, []))
        (log_dir / filename).write_text(content + ("\n" if content else ""), encoding="utf-8")


def run_handoff(config: AppConfig, options: RunOptions) -> HandoffResult:
    spec = workflow_spec(options.mode)

    role = config.roles.get(options.role)
    if role is None:
        raise ValueError(f"Unknown role: {options.role}")
    platform = config.platforms.get(options.platform) if options.platform else None
    if options.platform and platform is None:
        raise ValueError(f"Unknown platform: {options.platform}")

    scope = merge_scope(role, platform, options)
    prompt, context, request_text = build_prompt(config, options, scope)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    default_label = options.role if options.mode == "run" else f"{options.mode}-{options.role}"
    label = slugify(options.label or default_label)
    output_root = options.cwd / config.toolkit.output_dir
    log_dir = output_root / f"{timestamp}-{label}"
    log_dir.mkdir(parents=True, exist_ok=True)

    (log_dir / "metadata.env").write_text(
        "".join(
            [
                f"mode={options.mode}\n",
                f"role={options.role}\n",
                f"platform={options.platform or ''}\n",
                f"created_at={datetime.now().astimezone().isoformat()}\n",
                f"cwd={options.cwd}\n",
                f"goal={options.goal}\n",
                f"label={options.label or default_label}\n",
                f"log_dir={log_dir}\n",
            ]
        ),
        encoding="utf-8",
    )
    (log_dir / "request.txt").write_text(request_text, encoding="utf-8")
    (log_dir / "prompt-context.txt").write_text(context, encoding="utf-8")
    (log_dir / "full-prompt.txt").write_text(prompt, encoding="utf-8")

    mode = detect_repo_mode(options.cwd)
    (log_dir / "workspace-mode.txt").write_text(mode + "\n", encoding="utf-8")
    git_state_before: dict[str, str] = {}
    git_state_after: dict[str, str] = {}
    before = snapshot_workspace(
        options.cwd,
        ignore_names=config.toolkit.ignore,
        output_dir=output_root,
        mode=mode,
    )
    write_snapshot(log_dir / "workspace-before.tsv", before)
    if mode == "git":
        git_state_before = capture_git_state(options.cwd)
        for name, value in git_state_before.items():
            (log_dir / f"git-{name}-before.txt").write_text(value + ("\n" if value else ""), encoding="utf-8")

    if mode == "git":
        git_status_before = run_git_readonly(options.cwd, "status", "--short")
        if git_status_before:
            (log_dir / "git-status-before.txt").write_text(git_status_before.stdout, encoding="utf-8")
        git_diff_before = run_git_readonly(options.cwd, "diff", "--stat")
        if git_diff_before:
            (log_dir / "git-diff-before.txt").write_text(git_diff_before.stdout, encoding="utf-8")

    if options.dry_run:
        response = AdapterResult(exit_code=0, stdout="", stderr="")
        (log_dir / "specialist-response.txt").write_text("", encoding="utf-8")
    else:
        adapter_config = config.adapters.get(scope.adapter)
        if adapter_config is None:
            raise ValueError(f"Unknown adapter: {scope.adapter}")
        adapter = build_adapter(scope.adapter, adapter_config)
        with git_guard_environment(enabled=(mode == "git" and config.toolkit.protect_git)) as (adapter_env, guard_path):
            if guard_path:
                (log_dir / "git-guard-path.txt").write_text(guard_path + "\n", encoding="utf-8")
            response = adapter.run(prompt, cwd=options.cwd, env=adapter_env)
            (log_dir / "specialist-response.txt").write_text(response.stdout, encoding="utf-8")
            if response.stderr:
                (log_dir / "adapter-stderr.txt").write_text(response.stderr, encoding="utf-8")

    after = snapshot_workspace(
        options.cwd,
        ignore_names=config.toolkit.ignore,
        output_dir=output_root,
        mode=mode,
    )
    write_snapshot(log_dir / "workspace-after.tsv", after)
    if mode == "git":
        git_state_after = capture_git_state(options.cwd)
        for name, value in git_state_after.items():
            (log_dir / f"git-{name}-after.txt").write_text(value + ("\n" if value else ""), encoding="utf-8")
    touched_paths = diff_snapshots(before, after)
    (log_dir / "touched-paths.txt").write_text("".join(f"{path}\n" for path in touched_paths), encoding="utf-8")

    if mode == "git":
        git_status_after = run_git_readonly(options.cwd, "status", "--short")
        if git_status_after:
            (log_dir / "git-status-after.txt").write_text(git_status_after.stdout, encoding="utf-8")
        git_diff_after = run_git_readonly(options.cwd, "diff", "--stat")
        if git_diff_after:
            (log_dir / "git-diff-after.txt").write_text(git_diff_after.stdout, encoding="utf-8")
        git_patch = run_git_readonly(options.cwd, "diff", "--binary")
        if git_patch:
            (log_dir / "git-diff.patch").write_text(git_patch.stdout, encoding="utf-8")

    policy_violations: list[str] = []
    if options.mode == "assess":
        for path in touched_paths:
            policy_violations.append(f"Read-only assess touched path: {path}")
    else:
        for path in touched_paths:
            if path_matches(path, scope.deny):
                policy_violations.append(f"Denied path touched: {path}")
            if scope.allow and not path_matches(path, scope.allow):
                policy_violations.append(f"Path outside allow list touched: {path}")
    if mode == "git" and config.toolkit.protect_git:
        policy_violations.extend(detect_git_state_violations(git_state_before, git_state_after))

    (log_dir / "policy-violations.txt").write_text(
        "".join(f"{line}\n" for line in policy_violations),
        encoding="utf-8",
    )

    sections = extract_sections(response.stdout, spec.section_names)
    write_sections(log_dir, sections, spec.section_files)

    resume_lines = [
        f"Handoff record: {log_dir}",
        f"Mode: {options.mode}",
        f"Request: {log_dir / 'request.txt'}",
        f"Prompt: {log_dir / 'full-prompt.txt'}",
        f"Specialist response: {log_dir / 'specialist-response.txt'}",
    ]
    if options.mode == "assess":
        resume_lines.extend(
            [
                f"Visual issues: {log_dir / 'visual-issues.txt'}",
                f"Suggested write scope: {log_dir / 'suggested-write-scope.txt'}",
                f"Acceptance criteria: {log_dir / 'acceptance-criteria.txt'}",
            ]
        )
    else:
        resume_lines.append(f"Next for controller: {log_dir / 'next-for-controller.txt'}")
    resume_lines.append(f"Touched paths: {log_dir / 'touched-paths.txt'}")
    if policy_violations:
        resume_lines.append(f"Policy violations: {log_dir / 'policy-violations.txt'}")
    if options.dry_run:
        resume_lines.append("Dry run: adapter was not invoked.")
    (log_dir / "resume.txt").write_text("\n".join(resume_lines) + "\n", encoding="utf-8")

    latest_links = [
        output_root / "latest",
        output_root / f"latest-{options.mode}",
        output_root / f"latest-{options.role}",
        output_root / f"latest-{options.mode}-{options.role}",
    ]
    for latest in latest_links:
        if latest.exists() or latest.is_symlink():
            latest.unlink()
        latest.symlink_to(log_dir.name)

    exit_code = response.exit_code
    if policy_violations:
        exit_code = 1

    return HandoffResult(
        log_dir=log_dir,
        exit_code=exit_code,
        policy_violations=policy_violations,
        touched_paths=touched_paths,
        dry_run=options.dry_run,
    )
