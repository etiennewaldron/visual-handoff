# Visual Handoff

`visual-handoff` is a small CLI for controller-led delegation of visual work.

The intended model is simple:

1. A primary agent frames the task and boundaries.
2. A specialist agent can assess the UI read-only first.
3. The primary agent approves a write scope.
4. The specialist agent handles only that write slice.
5. The primary agent reviews the result, integrates follow-up, and verifies the outcome.

The toolkit is portable across web apps, Flutter, SwiftUI, Jetpack Compose, React Native, and docs/decks. The core abstraction is `visual`, not just `frontend`.

## What It Is

This toolkit gives you:

- a standard handoff contract for visual work
- project-level config via `.visual-handoff.toml`
- starter templates for common repo types
- run logs with prompt, response, workspace diffing, and policy checks
- git mutation blocking during the specialist run

This toolkit does not give you a hard sandbox. It is a guardrailed delegation workflow with auditability, not a full isolation boundary.

## Default Path

The default out-of-the-box path is:

1. Install `visual-handoff` on the machine.
2. Install and authenticate `gemini`.
3. Run `visual-handoff init --template ...` in the target repo.
4. Use `visual-handoff assess visual ...` to let Gemini critique the UI read-only.
5. Approve a write scope.
6. Use `visual-handoff run visual ...` for the actual edit.

Projects can switch to another specialist CLI later, but the starter config uses `gemini` by default.

## Install

Recommended for day-to-day use: install `visual-handoff` once per machine with `pipx`.

From a public GitHub repo:

```bash
pipx install 'git+https://github.com/<your-org>/<your-repo>.git'
```

From a local checkout while developing:

```bash
pipx install --editable /path/to/visual-handoff
```

On macOS, if `pipx` is not installed yet:

```bash
brew install pipx
```

Verify:

```bash
visual-handoff --help
```

If you want the default path, also install and authenticate `gemini` on that machine.

Alternative for an already activated virtual environment or local dev shell:

```bash
cd /path/to/visual-handoff
python3 -m pip install -e .
```

Project repos do not vendor the CLI. They assume `visual-handoff` is already installed and available on `PATH`.

## Quick Start

Initialize a target repo:

```bash
visual-handoff init --template mixed-visual /path/to/my-app
```

Start with a read-only visual assessment:

```bash
cd /path/to/my-app
visual-handoff assess visual \
  --platform flutter \
  --goal "Audit the onboarding flow on smaller phones" \
  --focus lib/features/onboarding \
  --verify "Check hierarchy and touch targets on compact widths"
```

`--cwd` must point to an existing target repo directory. The tool does not create a missing repo path for you.

Then run the approved implementation slice:

```bash
cd /path/to/my-app
visual-handoff run visual \
  --platform flutter \
  --goal "Refine the onboarding flow for smaller phones" \
  --allow lib/features/onboarding \
  --accept "Keep the current color system" \
  --accept "Improve hierarchy and touch targets on 390px wide screens"
```

Inspect a prompt without invoking the specialist:

```bash
visual-handoff assess visual \
  --platform web \
  --goal "Polish the pricing page hero" \
  --focus src/routes/pricing \
  --dry-run
```

## How To Adopt It In A Repo

In a new project repo, the controller agent should:

1. Verify `visual-handoff` is installed and available on `PATH`.
2. Verify the intended specialist CLI is installed and authenticated.
3. Run `visual-handoff init --template ...` if the repo does not already have `.visual-handoff.toml`.
4. Leave `roles.visual.adapter = "gemini"` in place unless the project intentionally uses a different specialist CLI.
5. Start with `visual-handoff assess visual ... --dry-run` or a real read-only assessment before delegating edits.
6. Use `visual-handoff run visual ...` only after the controller agrees on the write scope.

Installing `visual-handoff` does not automatically make GPT, Claude, or other agents use it for visual work. That routing behavior is repo-specific. If you want agents working in a project to use `visual-handoff` by default for UI tasks, add that rule to the project's own agent instructions, such as `AGENTS.md`.

## Config

The toolkit reads `.visual-handoff.toml` from the current directory or any parent directory.

For built-in names such as `visual`, `web`, or `flutter`, repo config extends the built-in defaults instead of wiping them out. That lets you add repo-specific rules without accidentally removing the base safety contract.

Starter example:

```toml
[project]
name = "my-app"
instructions = [
  "Preserve the established brand voice.",
  "Keep changes scoped to visual surfaces unless the task explicitly requires more."
]

[toolkit]
controller = "Primary agent"
specialist = "Visual specialist"
output_dir = "output/visual-handoffs"
protect_git = true
ignore = [".git", "node_modules", "dist", "build", ".dart_tool"]

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
  "Review responsive behavior on compact and regular phone widths.",
  "Preserve semantics, focus order, and touch target clarity."
]
```

If the repo uses the starter config, no extra adapter wiring is needed. `roles.visual.adapter = "gemini"` is already set.

## Custom Adapters

Projects can define their own specialist adapters. The toolkit supports CLIs that receive the prompt:

- as the final argv value with `prompt_mode = "argv"` (default)
- on stdin with `prompt_mode = "stdin"`
- via a `{prompt}` placeholder inside `args`

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

Use a custom adapter only when the project wants something other than the default Gemini specialist.

## Safety Model

Each `run` builds a handoff contract that tells the specialist:

- this is a delegated visual step
- stay within allowed paths
- never touch denied paths
- do not mutate git
- stop and report when non-visual work is required

Each `assess` run is read-only by contract and asks the specialist to return:

- visual issues
- suggested write scope
- preserve constraints
- proposed acceptance criteria

The toolkit also:

- snapshots the workspace before and after the run
- records touched paths
- flags allow/deny violations
- blocks mutating git commands during the specialist run
- checks for git state drift afterward

In `assess` mode, any workspace write is treated as a policy violation.

What it does not do:

- it does not provide OS-level filesystem sandboxing
- it does not prevent arbitrary non-git shell commands by itself
- it should not be described as a hard security boundary

## CLI

### `visual-handoff init`

Bootstraps a target repo with:

- `.visual-handoff.toml`
- `AGENTS.handoff.md`

Examples:

```bash
visual-handoff init --template web /path/to/site
visual-handoff init --template flutter /path/to/mobile-app
visual-handoff init --template mixed-visual /path/to/product
```

### `visual-handoff run`

Runs a delegated specialist step.

Example:

```bash
visual-handoff run visual \
  --platform docs \
  --goal "Make the launch deck feel more projection-ready" \
  --allow docs/deck.html \
  --accept "Reduce chrome and increase whitespace" \
  --fact "Copy must stay consistent with current product scope"
```

Important flags:

- `--platform`: selects a built-in platform profile
- `--allow`: allowed file or directory, repeatable
- `--deny`: denied file or directory, repeatable
- `--accept`: acceptance criterion, repeatable
- `--fact`: fact that must remain true, repeatable
- `--preserve`: existing element or pattern to preserve, repeatable
- `--verify`: verification expectation, repeatable
- `--dry-run`: write handoff artifacts without calling the specialist adapter

### `visual-handoff assess`

Runs a delegated read-only visual assessment.

Example:

```bash
visual-handoff assess visual \
  --platform web \
  --goal "Audit the pricing page hero before implementation" \
  --focus src/routes/pricing \
  --verify "Call out hierarchy, spacing, and responsive risks"
```

Important flags:

- `--focus`: primary path or surface to inspect first, repeatable
- `--deny`: denied path, repeatable
- `--fact`: fact that must remain true, repeatable
- `--preserve`: existing element or pattern to preserve, repeatable
- `--verify`: inspection priority to pass to the specialist, repeatable
- `--dry-run`: write the assessment prompt and logs without calling the specialist adapter

## Output

Each handoff writes a timestamped record under `output/visual-handoffs/` by default:

- `request.txt`
- `prompt-context.txt`
- `full-prompt.txt`
- `specialist-response.txt`
- `workspace-before.tsv`
- `workspace-after.tsv`
- `touched-paths.txt`
- `policy-violations.txt`
- `resume.txt`

When the target repo is a git repository and `protect_git = true`, the run also records git safety artifacts such as:

- `git-head-before.txt`
- `git-head-after.txt`
- `git-refs-before.txt`
- `git-refs-after.txt`
- `git-stash-before.txt`
- `git-stash-after.txt`
- `git-guard-path.txt`

## Development

Run the unit tests from a fresh checkout:

```bash
python3.11 -m unittest discover -s tests -v
```

Build the distributable package artifacts:

```bash
python3.11 -m build
```

## License

MIT. See `LICENSE`.
