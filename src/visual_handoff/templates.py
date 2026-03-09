from __future__ import annotations

from pathlib import Path


CONFIG_TEMPLATES = {
    "web": """[project]
name = "web-project"
instructions = [
  "Preserve the established brand voice and interaction style.",
  "Keep changes scoped to visual surfaces unless the task explicitly requires more."
]

[toolkit]
controller = "Primary agent"
specialist = "Visual specialist"
output_dir = "output/visual-handoffs"
protect_git = true
ignore = [".git", "node_modules", "dist", "build", ".next"]

[adapters.gemini]
command = "gemini"
args = ["--approval-mode", "auto_edit", "--output-format", "text"]

[roles.visual]
adapter = "gemini"
profiles = ["visual/base"]
default_accept = [
  "Keep changes scoped to visual surfaces.",
  "If non-visual changes are required, stop and explain them in NEXT_FOR_CONTROLLER.",
  "Do not interact with local or remote databases, run migrations, or modify persistence/query layers."
]

[platforms.web]
profiles = ["visual/web"]
default_verify = [
  "Review desktop and mobile layouts.",
  "Preserve accessibility, hierarchy, and responsive behavior."
]
""",
    "flutter": """[project]
name = "flutter-project"
instructions = [
  "Preserve the current product tone and core user flows.",
  "Keep changes focused on visual presentation, interaction clarity, and accessibility."
]

[toolkit]
controller = "Primary agent"
specialist = "Visual specialist"
output_dir = "output/visual-handoffs"
protect_git = true
ignore = [".git", ".dart_tool", "build", ".idea"]

[adapters.gemini]
command = "gemini"
args = ["--approval-mode", "auto_edit", "--output-format", "text"]

[roles.visual]
adapter = "gemini"
profiles = ["visual/base"]
default_accept = [
  "Keep changes scoped to visual surfaces.",
  "If non-visual changes are required, stop and explain them in NEXT_FOR_CONTROLLER.",
  "Do not interact with local or remote databases, run migrations, or modify persistence/query layers."
]

[platforms.flutter]
profiles = ["visual/flutter"]
default_verify = [
  "Review compact and regular phone widths.",
  "Preserve semantics, focus order, and touch-target clarity."
]
""",
    "mixed-visual": """[project]
name = "visual-project"
instructions = [
  "Preserve the existing product voice and strongest visual patterns.",
  "Split mixed tasks so the specialist only handles the visual layer before the primary agent integrates."
]

[toolkit]
controller = "Primary agent"
specialist = "Visual specialist"
output_dir = "output/visual-handoffs"
protect_git = true
ignore = [".git", ".dart_tool", ".idea", ".vscode", "node_modules", "dist", "build", ".next"]

[adapters.gemini]
command = "gemini"
args = ["--approval-mode", "auto_edit", "--output-format", "text"]

[roles.visual]
adapter = "gemini"
profiles = ["visual/base"]
default_accept = [
  "Keep changes scoped to visual surfaces.",
  "If non-visual changes are required, stop and explain them in NEXT_FOR_CONTROLLER.",
  "Do not interact with local or remote databases, run migrations, or modify persistence/query layers."
]

[platforms.web]
profiles = ["visual/web"]

[platforms.flutter]
profiles = ["visual/flutter"]

[platforms.swiftui]
profiles = ["visual/swiftui"]

[platforms.compose]
profiles = ["visual/compose"]

[platforms.react-native]
profiles = ["visual/react-native"]

[platforms.docs]
profiles = ["visual/docs"]
""",
}


AGENTS_TEMPLATE = """# Repository Routing

- The primary agent is the control-plane agent for this repository.
- The specialist agent owns visual work.

# Visual Scope

- Treat any pixel-facing task as visual work: web UI, Flutter, SwiftUI, Jetpack Compose, React Native, Electron, responsive layout, styling, motion, screenshot-driven fixes, and visual docs/decks.
- When a task is primarily visual, start with `visual-handoff assess visual` when the visual problems or right write scope are still unclear.
- Use `visual-handoff run visual` after the controller approves the execution slice.

# Non-Visual Scope

- Backend logic, data models, security behavior, packaging, build plumbing, architecture, and cross-cutting integration remain with the primary agent unless the task explicitly requires a tightly scoped supporting change.

# Delegation Workflow

- The primary agent reads the repo, defines the safe delegated slice, and sets constraints.
- For larger or ambiguous visual work, the specialist should assess the UI read-only first and propose the right write scope.
- The starter config uses the `gemini` adapter for `visual` by default. Only change `roles.visual.adapter` if the repo intentionally uses a different specialist CLI.
- The specialist handles only the visual slice and stops after that step.
- The primary agent reviews the result, integrates any cross-cutting follow-up, and runs verification.
"""


def write_init_template(target_dir: Path, template: str, *, force: bool = False) -> list[Path]:
    if template not in CONFIG_TEMPLATES:
        raise ValueError(f"Unknown init template: {template}")

    target_dir.mkdir(parents=True, exist_ok=True)

    config_path = target_dir / ".visual-handoff.toml"
    agents_path = target_dir / "AGENTS.handoff.md"

    created: list[Path] = []
    for path, contents in [
        (config_path, CONFIG_TEMPLATES[template]),
        (agents_path, AGENTS_TEMPLATE),
    ]:
        if path.exists() and not force:
            raise FileExistsError(f"Refusing to overwrite existing file: {path}")
        path.write_text(contents, encoding="utf-8")
        created.append(path)

    return created
