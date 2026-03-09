from __future__ import annotations

from importlib.resources import files


PROFILE_MAP = {
    "visual/base": "visual-base.md",
    "visual/web": "visual-web.md",
    "visual/flutter": "visual-flutter.md",
    "visual/swiftui": "visual-swiftui.md",
    "visual/compose": "visual-compose.md",
    "visual/react-native": "visual-react-native.md",
    "visual/docs": "visual-docs.md",
}


def load_profile(name: str) -> str:
    filename = PROFILE_MAP.get(name)
    if filename is None:
        raise ValueError(f"Unknown built-in profile: {name}")
    return files("visual_handoff").joinpath("profiles", filename).read_text(encoding="utf-8").strip()
