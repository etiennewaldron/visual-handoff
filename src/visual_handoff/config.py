from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import tomllib


CONFIG_FILENAME = ".visual-handoff.toml"


@dataclass(slots=True)
class ProjectConfig:
    name: str = ""
    instructions: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ToolkitConfig:
    controller: str = "Primary agent"
    specialist: str = "Specialist agent"
    output_dir: str = "output/visual-handoffs"
    protect_git: bool = True
    ignore: list[str] = field(
        default_factory=lambda: [
            ".git",
            ".hg",
            ".svn",
            ".idea",
            ".vscode",
            "node_modules",
            "dist",
            "build",
            ".dart_tool",
            ".turbo",
            ".next",
        ]
    )


@dataclass(slots=True)
class AdapterConfig:
    command: str
    args: list[str] = field(default_factory=list)
    prompt_mode: str = "argv"


@dataclass(slots=True)
class ScopeConfig:
    profiles: list[str] = field(default_factory=list)
    instructions: list[str] = field(default_factory=list)
    default_allow: list[str] = field(default_factory=list)
    default_deny: list[str] = field(default_factory=list)
    default_accept: list[str] = field(default_factory=list)
    default_verify: list[str] = field(default_factory=list)
    adapter: str | None = None


@dataclass(slots=True)
class AppConfig:
    project: ProjectConfig
    toolkit: ToolkitConfig
    adapters: dict[str, AdapterConfig]
    roles: dict[str, ScopeConfig]
    platforms: dict[str, ScopeConfig]
    path: Path | None = None


def _merge_unique_strings(existing: list[str], incoming: list[str]) -> list[str]:
    merged = list(existing)
    for item in incoming:
        if item not in merged:
            merged.append(item)
    return merged


def _string_list(value: Any, *, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must be a list of strings")
    return list(value)


def _optional_string(value: Any, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be a non-empty string when provided")
    return value


def _choice(value: Any, *, field_name: str, choices: set[str], default: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str) or value not in choices:
        allowed = ", ".join(sorted(choices))
        raise ValueError(f"{field_name} must be one of: {allowed}")
    return value


def _bool(value: Any, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field_name} must be a boolean")


def _load_scope(section: dict[str, Any], *, base: ScopeConfig | None = None, field_prefix: str = "scope") -> ScopeConfig:
    base = base or ScopeConfig()
    return ScopeConfig(
        profiles=_merge_unique_strings(
            base.profiles,
            _string_list(section.get("profiles"), field_name=f"{field_prefix}.profiles"),
        ),
        instructions=_merge_unique_strings(
            base.instructions,
            _string_list(section.get("instructions"), field_name=f"{field_prefix}.instructions"),
        ),
        default_allow=_merge_unique_strings(
            base.default_allow,
            _string_list(section.get("default_allow"), field_name=f"{field_prefix}.default_allow"),
        ),
        default_deny=_merge_unique_strings(
            base.default_deny,
            _string_list(section.get("default_deny"), field_name=f"{field_prefix}.default_deny"),
        ),
        default_accept=_merge_unique_strings(
            base.default_accept,
            _string_list(section.get("default_accept"), field_name=f"{field_prefix}.default_accept"),
        ),
        default_verify=_merge_unique_strings(
            base.default_verify,
            _string_list(section.get("default_verify"), field_name=f"{field_prefix}.default_verify"),
        ),
        adapter=_optional_string(section.get("adapter"), field_name=f"{field_prefix}.adapter") or base.adapter,
    )


def default_config() -> AppConfig:
    return AppConfig(
        project=ProjectConfig(),
        toolkit=ToolkitConfig(),
        adapters={
            "gemini": AdapterConfig(
                command="gemini",
                args=["--approval-mode", "auto_edit", "--output-format", "text"],
                prompt_mode="argv",
            )
        },
        roles={
            "visual": ScopeConfig(
                profiles=["visual/base"],
                default_accept=[
                    "Keep changes scoped to visual surfaces.",
                    "If a non-visual change is required, stop and explain it in NEXT_FOR_CONTROLLER.",
                    "Do not interact with local or remote databases, run migrations, or modify persistence/query layers.",
                ],
            )
        },
        platforms={
            "web": ScopeConfig(profiles=["visual/web"]),
            "flutter": ScopeConfig(profiles=["visual/flutter"]),
            "swiftui": ScopeConfig(profiles=["visual/swiftui"]),
            "compose": ScopeConfig(profiles=["visual/compose"]),
            "react-native": ScopeConfig(profiles=["visual/react-native"]),
            "docs": ScopeConfig(profiles=["visual/docs"]),
        },
        path=None,
    )


def find_config(start: Path, filename: str = CONFIG_FILENAME) -> Path | None:
    current = start.resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        path = candidate / filename
        if path.exists():
            return path
    return None


def load_config(path: Path | None) -> AppConfig:
    config = default_config()
    if path is None:
        return config

    raw = tomllib.loads(path.read_text(encoding="utf-8"))

    project_section = raw.get("project", {})
    if project_section:
        config.project = ProjectConfig(
            name=project_section.get("name", ""),
            instructions=_string_list(project_section.get("instructions"), field_name="project.instructions"),
        )

    toolkit_section = raw.get("toolkit", {})
    if toolkit_section:
        config.toolkit = ToolkitConfig(
            controller=toolkit_section.get("controller", config.toolkit.controller),
            specialist=toolkit_section.get("specialist", config.toolkit.specialist),
            output_dir=toolkit_section.get("output_dir", config.toolkit.output_dir),
            protect_git=_bool(toolkit_section.get("protect_git", config.toolkit.protect_git), field_name="toolkit.protect_git"),
            ignore=_string_list(toolkit_section.get("ignore"), field_name="toolkit.ignore")
            or config.toolkit.ignore,
        )

    adapters_section = raw.get("adapters", {})
    for name, section in adapters_section.items():
        command = section.get("command")
        if not isinstance(command, str) or not command:
            raise ValueError(f"adapters.{name}.command must be a non-empty string")
        args = _string_list(section.get("args"), field_name=f"adapters.{name}.args")
        prompt_mode = _choice(
            section.get("prompt_mode"),
            field_name=f"adapters.{name}.prompt_mode",
            choices={"argv", "stdin"},
            default="argv",
        )
        config.adapters[name] = AdapterConfig(command=command, args=args, prompt_mode=prompt_mode)

    roles_section = raw.get("roles", {})
    for name, section in roles_section.items():
        config.roles[name] = _load_scope(
            section,
            base=config.roles.get(name),
            field_prefix=f"roles.{name}",
        )

    platforms_section = raw.get("platforms", {})
    for name, section in platforms_section.items():
        config.platforms[name] = _load_scope(
            section,
            base=config.platforms.get(name),
            field_prefix=f"platforms.{name}",
        )

    config.path = path
    return config
