from pathlib import Path
import tempfile
import unittest

import _bootstrap

from visual_handoff.git_safety import detect_git_state_violations, extract_git_subcommand, is_allowed_git_invocation


class GitSafetyTests(unittest.TestCase):
    def test_extract_git_subcommand_skips_global_options(self) -> None:
        self.assertEqual(extract_git_subcommand(["-C", "repo", "status"]), "status")
        self.assertEqual(extract_git_subcommand(["-c", "color.ui=always", "diff"]), "diff")
        self.assertEqual(extract_git_subcommand(["--git-dir=.git", "--work-tree=.", "rev-parse", "HEAD"]), "rev-parse")

    def test_is_allowed_git_invocation_blocks_mutating_commands(self) -> None:
        self.assertTrue(is_allowed_git_invocation(["status", "--short"]))
        self.assertTrue(is_allowed_git_invocation(["show", "HEAD"]))
        self.assertFalse(is_allowed_git_invocation(["checkout", "--", "file.txt"]))
        self.assertFalse(is_allowed_git_invocation(["commit", "-m", "oops"]))
        self.assertFalse(is_allowed_git_invocation(["push", "origin", "HEAD"]))

    def test_detect_git_state_violations_reports_drift(self) -> None:
        before = {
            "head": "abc",
            "branch": "main",
            "refs": "refs/heads/main abc",
            "stash": "",
        }
        after = {
            "head": "def",
            "branch": "feature",
            "refs": "refs/heads/main def\nrefs/heads/feature def",
            "stash": "stash@{0}: WIP on main",
        }
        violations = detect_git_state_violations(before, after)
        self.assertIn("Git HEAD changed during specialist run.", violations)
        self.assertIn("Checked-out git branch changed during specialist run.", violations)
        self.assertIn("Git refs changed during specialist run.", violations)
        self.assertIn("Git stash state changed during specialist run.", violations)


if __name__ == "__main__":
    unittest.main()
