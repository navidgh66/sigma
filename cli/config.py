"""Load, validate, and write sigma.config.yml."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml

from cli.paths import (
    CONFIG_FILENAME,
    DOMAINS,
    LOCAL_CONFIG_FILENAME,
    project_root,
)

DEFAULT_MODELS = ["claude", "gemini", "gpt"]
DEFAULT_TOOLS: List[str] = []

DEFAULT_COMMANDS = [
    "/research",
    "/propose",
    "/blueprint",
    "/spec",
    "/tasks",
    "/implement-task",
    "/verify",
    "/loop",
]


@dataclass
class LoopConfig:
    max_cycles: int = 20
    worktrees: bool = True
    maker_checker_separation: bool = True


@dataclass
class SigmaConfig:
    name: str = "my-project"
    harness: str = "claude-code"
    models: List[str] = field(default_factory=lambda: list(DEFAULT_MODELS))
    tools: List[str] = field(default_factory=lambda: list(DEFAULT_TOOLS))
    domains: List[str] = field(default_factory=lambda: list(DOMAINS))
    commands: List[str] = field(default_factory=lambda: list(DEFAULT_COMMANDS))
    loop: LoopConfig = field(default_factory=LoopConfig)

    def validate(self) -> List[str]:
        """Return a list of human-readable validation errors (empty if valid)."""
        errors: List[str] = []
        unknown = [d for d in self.domains if d not in DOMAINS]
        if unknown:
            errors.append(f"unknown domain(s): {', '.join(unknown)}")
        if not self.domains:
            errors.append("at least one domain must be enabled")
        if self.loop.max_cycles < 1:
            errors.append("loop.max_cycles must be >= 1")
        return errors

    def to_dict(self) -> dict:
        return {
            "profile": {"name": self.name, "harness": self.harness},
            "research": {"models": self.models, "tools": self.tools},
            "domains": self.domains,
            "commands": self.commands,
            "loop": {
                "max_cycles": self.loop.max_cycles,
                "worktrees": self.loop.worktrees,
                "maker_checker_separation": self.loop.maker_checker_separation,
            },
        }


def _from_dict(data: dict) -> SigmaConfig:
    data = data or {}
    profile = data.get("profile", {}) or {}
    research = data.get("research", {}) or {}
    loop_raw = data.get("loop", {}) or {}
    loop = LoopConfig(
        max_cycles=int(loop_raw.get("max_cycles", 20)),
        worktrees=bool(loop_raw.get("worktrees", True)),
        maker_checker_separation=bool(loop_raw.get("maker_checker_separation", True)),
    )
    return SigmaConfig(
        name=profile.get("name", "my-project"),
        harness=profile.get("harness", "claude-code"),
        models=list(research.get("models", DEFAULT_MODELS)),
        tools=list(research.get("tools", DEFAULT_TOOLS)),
        domains=list(data.get("domains", list(DOMAINS))),
        commands=list(data.get("commands", DEFAULT_COMMANDS)),
        loop=loop,
    )


def config_path(root: Optional[Path] = None) -> Path:
    return project_root(root) / CONFIG_FILENAME


def load_config(root: Optional[Path] = None) -> SigmaConfig:
    """Load config, merging the local override file if present."""
    base_path = config_path(root)
    data: dict = {}
    if base_path.exists():
        data = yaml.safe_load(base_path.read_text()) or {}

    local_path = project_root(root) / LOCAL_CONFIG_FILENAME
    if local_path.exists():
        local = yaml.safe_load(local_path.read_text()) or {}
        data = _deep_merge(data, local)

    return _from_dict(data)


def write_config(cfg: SigmaConfig, root: Optional[Path] = None) -> Path:
    """Write config to sigma.config.yml. Returns the path written."""
    path = config_path(root)
    path.write_text(
        yaml.safe_dump(cfg.to_dict(), sort_keys=False, default_flow_style=False)
    )
    return path


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning a new dict."""
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
