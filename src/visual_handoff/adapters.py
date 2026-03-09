from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from typing import Mapping

from visual_handoff.config import AdapterConfig


@dataclass(slots=True)
class AdapterResult:
    exit_code: int
    stdout: str
    stderr: str


PROMPT_PLACEHOLDER = "{prompt}"


class SubprocessAdapter:
    def __init__(self, config: AdapterConfig) -> None:
        self.config = config

    def _render_args(self, prompt: str) -> tuple[list[str], bool]:
        rendered: list[str] = []
        used_placeholder = False
        for arg in self.config.args:
            if PROMPT_PLACEHOLDER in arg:
                used_placeholder = True
                rendered.append(arg.replace(PROMPT_PLACEHOLDER, prompt))
            else:
                rendered.append(arg)
        return rendered, used_placeholder

    def run(self, prompt: str, *, cwd: Path, env: Mapping[str, str] | None = None) -> AdapterResult:
        if shutil.which(self.config.command) is None:
            raise FileNotFoundError(f"Adapter command not found on PATH: {self.config.command}")

        args, used_placeholder = self._render_args(prompt)
        if self.config.prompt_mode == "argv" and not used_placeholder:
            args = [*args, prompt]

        process = subprocess.run(
            [self.config.command, *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
            env=dict(env) if env is not None else None,
            input=prompt if self.config.prompt_mode == "stdin" else None,
        )
        return AdapterResult(
            exit_code=process.returncode,
            stdout=process.stdout,
            stderr=process.stderr,
        )


def build_adapter(name: str, config: AdapterConfig) -> SubprocessAdapter:
    return SubprocessAdapter(config)
