# Visual Handoff

`visual-handoff` is a small CLI for assess-first delegation of UI and visual work.

Use it when you want one agent to own reasoning, scoping, and orchestration, while a specialist model handles visual critique and UI implementation for a tightly scoped slice.

Visual Handoff exists because the model you trust most for UI critique and visual polish is not always the one you want making broad repo decisions. Specialist models can be excellent at design work while still being over-eager about git actions, adjacent files, or scope expansion. Visual Handoff keeps the specialist focused on the visual slice: broad enough to inspect the UI properly, narrow enough to keep edits, git behavior, and auditability under control.

The default path is:

1. Initialize a repo with `visual-handoff init`.
2. Run `visual-handoff assess visual ...` to get a read-only visual critique.
3. Approve a write scope.
4. Run `visual-handoff run visual ...` for the actual edit.

It works across web, Flutter, SwiftUI, Jetpack Compose, React Native, and docs/decks. The core abstraction is `visual`, not just `frontend`.

```text
Controller agent
  -> defines the task and constraints
  -> runs `visual-handoff assess`

visual-handoff
  -> builds the assessment prompt
  -> runs the specialist CLI

Visual specialist
  -> assesses the current UI
  -> returns visual issues and a suggested write scope

Controller agent
  -> approves the write scope
  -> runs `visual-handoff run`

visual-handoff
  -> builds the implementation prompt
  -> runs the specialist CLI
  -> records logs and checks boundaries

Visual specialist
  -> implements the approved visual slice

Controller agent
  -> reviews and integrates the result
```

## What It Gives You

- a standard handoff contract for visual work
- project-level config via `.visual-handoff.toml`
- starter templates for common repo types
- audit logs with prompt, response, touched paths, and policy checks
- git mutation blocking during the specialist run

It is a guardrailed delegation workflow with auditability. It is not a hard sandbox.

## Fast Start

Install the CLI once per machine:

```bash
pipx install 'git+https://github.com/etiennewaldron/visual-handoff.git'
```

If your `pipx` default Python is older than 3.11, install with an explicit interpreter:

```bash
pipx install --python python3.11 'git+https://github.com/etiennewaldron/visual-handoff.git'
```

If you are using the default specialist path, also install and authenticate `gemini`.

Then, in a target repo:

```bash
cd /path/to/project
visual-handoff init --template mixed-visual .
visual-handoff assess visual \
  --platform web \
  --goal "Audit the settings screen"
```

After you approve the suggested scope:

```bash
visual-handoff run visual \
  --platform web \
  --goal "Redesign the settings screen" \
  --allow src/routes/settings \
  --accept "Keep the current brand direction" \
  --accept "Improve hierarchy, spacing, and CTA clarity"
```

`--cwd` must point to an existing directory. The tool does not create a missing repo path for you.

## Agent Adoption

The agent should do this:

1. Verify `visual-handoff` is installed and available on `PATH`.
2. Verify the intended specialist CLI is installed and authenticated.
3. Run `visual-handoff init --template ...` if the repo does not already have `.visual-handoff.toml`.
4. Start with `visual-handoff assess visual ...`.
5. Use `visual-handoff run visual ...` only after the write scope is approved.

Installing `visual-handoff` does not automatically make GPT, Claude, or other agents use it for visual work. That routing behavior is repo-specific. If you want agents working in a project to use it by default, add that rule to the project's own instructions, such as `AGENTS.md`.

## Templates

`visual-handoff init` supports three starter templates:

- `mixed-visual`: general starter for repos that may delegate across web, mobile, or docs. This is the safest default.
- `web`: web-focused starter.
- `flutter`: Flutter-focused starter.

Example:

```bash
visual-handoff init --template mixed-visual .
```

`init` writes:

- `.visual-handoff.toml`
- `AGENTS.handoff.md`

`AGENTS.handoff.md` is a starter routing guide. If your environment relies on a different agent-instruction file such as `AGENTS.md`, copy or adapt that guidance there.

## How It Works

`assess` is read-only. The specialist is asked to inspect the UI and return:

- `VISUAL_ISSUES`
- `SUGGESTED_WRITE_SCOPE`
- `PRESERVE`
- `ACCEPTANCE_CRITERIA`

`run` is the implementation step. The specialist is told:

- this is a delegated visual task
- stay within allowed paths
- never touch denied paths
- do not mutate git
- stop and report if non-visual changes are required

The controller still owns scope approval, integration, and final verification.

## Config

The toolkit reads `.visual-handoff.toml` from the current directory or any parent directory.

Repo config extends built-in defaults instead of wiping them out. That lets you add project-specific rules without accidentally removing the base safety contract.

Minimal example:

```toml
[project]
name = "my-app"
instructions = [
  "Preserve the established brand voice.",
  "Keep changes scoped to visual surfaces unless the task explicitly requires more."
]

[toolkit]
output_dir = "output/visual-handoffs"
protect_git = true

[adapters.gemini]
command = "gemini"
args = ["--approval-mode", "auto_edit", "--output-format", "text"]

[roles.visual]
adapter = "gemini"
profiles = ["visual/base"]

[platforms.web]
profiles = ["visual/web"]
```

If you use a starter template, you already get a working Gemini-backed config.

## Custom Specialists

Projects can replace Gemini with another CLI by defining a custom adapter.

Supported prompt delivery modes:

- `prompt_mode = "argv"`: append the prompt as the final argument
- `prompt_mode = "stdin"`: send the prompt on stdin
- `{prompt}` placeholder inside `args`

Example:

```toml
[adapters.visual_specialist]
command = "claude"
args = ["<your-cli-flags>"]
prompt_mode = "stdin"

[roles.visual]
adapter = "visual_specialist"
profiles = ["visual/base"]
```

## Safety Model

Each run:

- snapshots the workspace before and after
- records touched paths
- flags allow/deny violations
- blocks mutating git commands during the specialist run
- checks for git state drift afterward

In `assess` mode, any workspace write is treated as a policy violation.

What it does not do:

- it does not provide OS-level filesystem sandboxing
- it does not prevent arbitrary non-git shell commands by itself
- it should not be described as a hard security boundary

## Commands

`visual-handoff init`

- bootstraps a repo with `.visual-handoff.toml` and `AGENTS.handoff.md`

`visual-handoff assess`

- runs a delegated read-only visual assessment
- use `--focus` to point the specialist at the primary surface first

`visual-handoff run`

- runs the scoped implementation step
- use `--allow` aggressively to keep writes narrow

Inspect a prompt without invoking the specialist:

```bash
visual-handoff assess visual \
  --platform web \
  --goal "Polish the pricing page hero" \
  --focus src/routes/pricing \
  --dry-run
```

## Output

Each handoff writes a timestamped record under `output/visual-handoffs/` by default.

Common files:

- `request.txt`
- `prompt-context.txt`
- `full-prompt.txt`
- `specialist-response.txt`
- `workspace-before.tsv`
- `workspace-after.tsv`
- `touched-paths.txt`
- `policy-violations.txt`
- `resume.txt`

When the target repo is a git repository and `protect_git = true`, the run also records git safety artifacts such as `git-head-before.txt`, `git-head-after.txt`, and `git-guard-path.txt`.

## Development

Run tests:

```bash
python3.11 -m unittest discover -s tests -v
```

Build artifacts:

```bash
python3.11 -m build
```

## License

MIT. See `LICENSE`.
