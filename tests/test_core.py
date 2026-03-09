from pathlib import Path
import sys
import tempfile
import unittest

import _bootstrap

from visual_handoff.config import AdapterConfig, default_config
from visual_handoff.core import (
    ASSESS_SECTION_NAMES,
    RUN_SECTION_NAMES,
    RunOptions,
    build_prompt,
    diff_snapshots,
    extract_sections,
    merge_scope,
    path_in_scope,
    run_handoff,
    should_ignore_path,
)


class CoreTests(unittest.TestCase):
    def test_merge_scope_includes_role_platform_and_cli_inputs(self) -> None:
        config = default_config()
        options = RunOptions(
            role="visual",
            goal="Polish layout",
            cwd=Path("."),
            platform="flutter",
            label=None,
            allow=["lib/features/home"],
            deny=["lib/domain"],
            accept=["Improve type hierarchy"],
            facts=["Business logic must remain unchanged"],
            preserve=["Current brand colors"],
            verify=["Check phone widths"],
            dry_run=True,
        )
        scope = merge_scope(config.roles["visual"], config.platforms["flutter"], options)
        self.assertIn("visual/base", scope.profiles)
        self.assertIn("visual/flutter", scope.profiles)
        self.assertIn("lib/features/home", scope.allow)
        self.assertIn("lib/domain", scope.deny)
        self.assertIn("Improve type hierarchy", scope.accept)

    def test_merge_scope_prefers_platform_adapter_over_role_default(self) -> None:
        config = default_config()
        config.roles["visual"].adapter = "gemini"
        config.platforms["web"].adapter = "custom-web"
        options = RunOptions(
            role="visual",
            goal="Polish layout",
            cwd=Path("."),
            platform="web",
            label=None,
            allow=[],
            deny=[],
            accept=[],
            facts=[],
            preserve=[],
            verify=[],
            dry_run=True,
        )
        scope = merge_scope(config.roles["visual"], config.platforms["web"], options)
        self.assertEqual(scope.adapter, "custom-web")

    def test_build_prompt_contains_contract_sections(self) -> None:
        config = default_config()
        options = RunOptions(
            role="visual",
            goal="Polish layout",
            cwd=Path("."),
            platform="web",
            label=None,
            allow=["src/ui"],
            deny=[],
            accept=[],
            facts=["Facts stay true"],
            preserve=["Keep current navigation structure"],
            verify=["Check mobile"],
            dry_run=True,
        )
        scope = merge_scope(config.roles["visual"], config.platforms["web"], options)
        prompt, context, request = build_prompt(config, options, scope)
        self.assertIn("Facts to preserve", prompt)
        self.assertIn("NEXT_FOR_CONTROLLER", prompt)
        self.assertIn("Allowed paths", context)
        self.assertIn("Role: visual", request)

    def test_build_assess_prompt_contains_assessment_sections(self) -> None:
        config = default_config()
        options = RunOptions(
            role="visual",
            goal="Audit the pricing hero",
            cwd=Path("."),
            platform="web",
            label=None,
            allow=[],
            deny=["server"],
            accept=[],
            facts=["Do not change product scope"],
            preserve=["Keep the current brand tone"],
            verify=["Check mobile hierarchy"],
            dry_run=True,
            mode="assess",
            focus=["src/routes/pricing"],
        )
        scope = merge_scope(config.roles["visual"], config.platforms["web"], options)
        prompt, context, request = build_prompt(config, options, scope)
        self.assertIn("Assessment contract", prompt)
        self.assertIn("VISUAL_ISSUES", prompt)
        self.assertIn("SUGGESTED_WRITE_SCOPE", prompt)
        self.assertIn("Primary focus areas", context)
        self.assertIn("Mode: assess", request)

    def test_extract_sections_reads_expected_headers(self) -> None:
        text = """STATUS:
- completed
SUMMARY:
- changed files
FILES_CHANGED:
- lib/main.dart
CHECKS_RUN:
- reviewed
BLOCKERS:
- none
NEXT_FOR_CONTROLLER:
- review
"""
        sections = extract_sections(text, RUN_SECTION_NAMES)
        self.assertEqual(sections["STATUS"], ["- completed"])
        self.assertEqual(sections["FILES_CHANGED"], ["- lib/main.dart"])

    def test_extract_sections_supports_assess_headers(self) -> None:
        text = """STATUS:
- completed
VISUAL_ISSUES:
- weak hierarchy
SUGGESTED_WRITE_SCOPE:
- src/routes/pricing
"""
        sections = extract_sections(text, ASSESS_SECTION_NAMES)
        self.assertEqual(sections["VISUAL_ISSUES"], ["- weak hierarchy"])
        self.assertEqual(sections["SUGGESTED_WRITE_SCOPE"], ["- src/routes/pricing"])

    def test_diff_snapshots_detects_new_or_changed_paths(self) -> None:
        before = {"a.txt": "1", "b.txt": "2"}
        after = {"a.txt": "1", "b.txt": "3", "c.txt": "4"}
        self.assertEqual(diff_snapshots(before, after), ["b.txt", "c.txt"])

    def test_path_in_scope(self) -> None:
        self.assertTrue(path_in_scope("lib/features/home.dart", "lib"))
        self.assertTrue(path_in_scope("lib/features", "lib/features"))
        self.assertFalse(path_in_scope("server/index.ts", "lib"))

    def test_should_ignore_output_and_named_ignored_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "output" / "visual-handoffs"
            output_dir.mkdir(parents=True)
            self.assertTrue(
                should_ignore_path(
                    "output/visual-handoffs/record/request.txt",
                    root,
                    ignore_names=["node_modules"],
                    output_dir=output_dir,
                )
            )
            self.assertTrue(
                should_ignore_path(
                    "node_modules/pkg/index.js",
                    root,
                    ignore_names=["node_modules"],
                    output_dir=output_dir,
                )
            )
            self.assertFalse(
                should_ignore_path(
                    "src/app.ts",
                    root,
                    ignore_names=["node_modules"],
                    output_dir=output_dir,
                )
            )

    def test_assess_mode_flags_any_workspace_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            config = default_config()
            config.adapters["writer"] = AdapterConfig(
                command=sys.executable,
                args=["-c", "from pathlib import Path; Path('changed.txt').write_text('x', encoding='utf-8')"],
            )
            config.roles["visual"].adapter = "writer"
            result = run_handoff(
                config,
                RunOptions(
                    role="visual",
                    goal="Assess only",
                    cwd=cwd,
                    platform="web",
                    label=None,
                    allow=[],
                    deny=[],
                    accept=[],
                    facts=[],
                    preserve=[],
                    verify=[],
                    dry_run=False,
                    mode="assess",
                    focus=["src/ui"],
                ),
            )
            self.assertEqual(result.exit_code, 1)
            self.assertIn("changed.txt", result.touched_paths)
            self.assertIn("Read-only assess touched path: changed.txt", result.policy_violations)

    def test_filesystem_mode_does_not_write_git_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            config = default_config()
            result = run_handoff(
                config,
                RunOptions(
                    role="visual",
                    goal="Assess only",
                    cwd=cwd,
                    platform="web",
                    label=None,
                    allow=[],
                    deny=[],
                    accept=[],
                    facts=[],
                    preserve=[],
                    verify=[],
                    dry_run=True,
                    mode="assess",
                    focus=["src/ui"],
                ),
            )

            names = {path.name for path in result.log_dir.iterdir()}
            self.assertIn("workspace-mode.txt", names)
            self.assertNotIn("git-status-before.txt", names)
            self.assertNotIn("git-status-after.txt", names)
            self.assertNotIn("git-diff-before.txt", names)
            self.assertNotIn("git-diff-after.txt", names)
            self.assertNotIn("git-diff.patch", names)


if __name__ == "__main__":
    unittest.main()
