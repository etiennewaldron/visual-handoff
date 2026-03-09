from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import _bootstrap

from visual_handoff.cli import main


class CliTests(unittest.TestCase):
    def run_main(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = StringIO()
        stderr = StringIO()
        with patch("sys.argv", argv), redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main()
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def test_main_reports_missing_adapter_command_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / ".visual-handoff.toml"
            config_path.write_text(
                """
[adapters.missing]
command = "definitely-not-a-real-command"

[roles.visual]
adapter = "missing"
""".strip(),
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self.run_main(
                ["visual-handoff", "assess", "visual", "--cwd", tmp, "--goal", "Audit the UI"]
            )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout, "")
            self.assertIn("Adapter command not found on PATH: definitely-not-a-real-command", stderr)
            self.assertNotIn("Traceback", stderr)

    def test_main_rejects_missing_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "does-not-exist"

            exit_code, stdout, stderr = self.run_main(
                ["visual-handoff", "assess", "visual", "--cwd", str(missing), "--goal", "Audit the UI", "--dry-run"]
            )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout, "")
            self.assertIn(f"--cwd does not exist: {missing}", stderr)
            self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
