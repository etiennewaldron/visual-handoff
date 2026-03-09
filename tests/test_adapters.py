from pathlib import Path
import sys
import unittest

import _bootstrap

from visual_handoff.adapters import build_adapter
from visual_handoff.config import AdapterConfig


class AdapterTests(unittest.TestCase):
    def test_subprocess_adapter_appends_prompt_as_argv_by_default(self) -> None:
        adapter = build_adapter(
            "anything",
            AdapterConfig(
                command=sys.executable,
                args=["-c", "import sys; print(sys.argv[1])"],
            ),
        )
        result = adapter.run("hello argv", cwd=Path("."))
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.stdout.strip(), "hello argv")

    def test_subprocess_adapter_supports_prompt_placeholder(self) -> None:
        adapter = build_adapter(
            "anything",
            AdapterConfig(
                command=sys.executable,
                args=["-c", "import sys; print(sys.argv[2])", "--prompt", "{prompt}"],
            ),
        )
        result = adapter.run("hello placeholder", cwd=Path("."))
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.stdout.strip(), "hello placeholder")

    def test_subprocess_adapter_supports_stdin_prompt_mode(self) -> None:
        adapter = build_adapter(
            "anything",
            AdapterConfig(
                command=sys.executable,
                args=["-c", "import sys; print(sys.stdin.read())"],
                prompt_mode="stdin",
            ),
        )
        result = adapter.run("hello stdin", cwd=Path("."))
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.stdout.strip(), "hello stdin")


if __name__ == "__main__":
    unittest.main()
