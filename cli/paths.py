"""Filesystem paths for sigma: install root, project root, spec directories."""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path
from typing import Optional

# Domains shipped by sigma. Single source of truth.
DOMAINS = (
    "classic-ml",
    "deep-learning",
    "nlp",
    "rl",
    "data-analysis",
    "data-engineering",
    "ai-agent-engineering",
    "mlops",
    "llm-engineering",
)

CONFIG_FILENAME = "sigma.config.yml"
LOCAL_CONFIG_FILENAME = "sigma.config.local.yml"


def sigma_home() -> Path:
    """Where sigma itself is installed (the cloned repo).

    Resolves from SIGMA_HOME env var, else the parent of this file's package.
    """
    env = os.environ.get("SIGMA_HOME")
    if env:
        return Path(env).expanduser().resolve()
    # cli/paths.py -> cli/ -> repo root
    return Path(__file__).resolve().parent.parent


def project_root(start: Optional[Path] = None) -> Path:
    """Find the current project root.

    Walk up from `start` (cwd by default) looking for sigma.config.yml or a
    .git directory. Fall back to cwd if neither is found.
    """
    cur = (start or Path.cwd()).resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / CONFIG_FILENAME).exists():
            return candidate
        if (candidate / ".git").exists():
            return candidate
    return cur


def slugify(text: str) -> str:
    """Turn an arbitrary string into a filesystem-safe slug."""
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "untitled"


def specs_dir(root: Optional[Path] = None) -> Path:
    """Directory holding all spec workspaces for a project."""
    return project_root(root) / "sigma" / "specs"


def spec_workspace(topic: str, root: Optional[Path] = None, today: Optional[date] = None) -> Path:
    """Path for a single feature's spec workspace: sigma/specs/{date}-{slug}/."""
    day = (today or date.today()).isoformat()
    return specs_dir(root) / f"{day}-{slugify(topic)}"
