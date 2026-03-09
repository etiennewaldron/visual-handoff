from pathlib import Path
import tempfile
import unittest

import _bootstrap

from visual_handoff.config import find_config, load_config


class ConfigTests(unittest.TestCase):
    def test_find_config_walks_upward(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "a" / "b"
            nested.mkdir(parents=True)
            config = root / ".visual-handoff.toml"
            config.write_text("[project]\nname = 'demo'\n", encoding="utf-8")
            found = find_config(nested)
            self.assertEqual(found.resolve(), config.resolve())

    def test_load_config_extends_built_in_role_and_platform_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".visual-handoff.toml"
            path.write_text(
                """
[toolkit]
protect_git = true

[roles.visual]
adapter = "gemini"
default_accept = ["Keep scope narrow"]

[platforms.flutter]
profiles = ["visual/flutter"]
default_verify = ["Check compact widths"]
""".strip(),
                encoding="utf-8",
            )
            config = load_config(path)
            self.assertIn("visual", config.roles)
            self.assertIn("flutter", config.platforms)
            self.assertTrue(config.toolkit.protect_git)
            self.assertIn("visual/base", config.roles["visual"].profiles)
            self.assertIn("Keep scope narrow", config.roles["visual"].default_accept)
            self.assertIn(
                "Do not interact with local or remote databases, run migrations, or modify persistence/query layers.",
                config.roles["visual"].default_accept,
            )
            self.assertEqual(config.platforms["flutter"].default_verify, ["Check compact widths"])

    def test_load_config_validates_optional_adapter_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".visual-handoff.toml"
            path.write_text(
                """
[roles.visual]
adapter = 123
""".strip(),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "roles.visual.adapter"):
                load_config(path)

    def test_load_config_reads_adapter_prompt_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".visual-handoff.toml"
            path.write_text(
                """
[adapters.claude]
command = "claude"
args = ["--print"]
prompt_mode = "stdin"
""".strip(),
                encoding="utf-8",
            )
            config = load_config(path)
            self.assertEqual(config.adapters["claude"].prompt_mode, "stdin")

    def test_load_config_validates_adapter_prompt_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".visual-handoff.toml"
            path.write_text(
                """
[adapters.claude]
command = "claude"
prompt_mode = "socket"
""".strip(),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "adapters.claude.prompt_mode"):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
