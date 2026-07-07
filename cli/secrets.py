"""Secret storage for sigma: API keys in ~/.sigma/.env, never the committed config.

Keys (Gemini, OpenAI) are written to a `.env` file inside the sigma install dir
with `chmod 600` (owner-only) and git-ignored. They are NEVER written to
`sigma.config.yml`, which is tracked in git. An ambient environment variable of
the same name also counts as "present", so users who already export their keys
don't get prompted.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Dict, List

from cli.paths import sigma_home

# The model API keys sigma knows how to use.
KNOWN_KEYS: List[str] = ["GEMINI_API_KEY", "OPENAI_API_KEY", "FIRECRAWL_API_KEY"]

ENV_FILENAME = ".env"
_OWNER_RW = 0o600


def env_path() -> Path:
    """Path to the sigma secret file (~/.sigma/.env in a normal install)."""
    return sigma_home() / ENV_FILENAME


def read_env() -> Dict[str, str]:
    """Parse the .env file into a dict. Missing file → empty dict."""
    path = env_path()
    if not path.exists():
        return {}
    out: Dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def write_key(name: str, value: str) -> Path:
    """Upsert a single key into the .env file, enforcing chmod 600.

    Preserves other keys, replaces an existing entry in place (no duplicates).
    """
    env = read_env()
    env[name] = value
    path = env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(f"{k}={v}\n" for k, v in env.items())
    path.write_text(body)
    # Enforce owner-only permissions on every write.
    path.chmod(_OWNER_RW)
    return path


def _is_present(name: str, env: Dict[str, str]) -> bool:
    # Ambient environment variable, or a value in the .env file.
    return bool(os.environ.get(name)) or bool(env.get(name))


def missing_keys() -> List[str]:
    """Return the KNOWN_KEYS that are neither in the env nor in ~/.sigma/.env."""
    env = read_env()
    return [k for k in KNOWN_KEYS if not _is_present(k, env)]


def chmod_is_secure() -> bool:
    """True if the .env exists and is owner-only (used by the doctor check)."""
    path = env_path()
    if not path.exists():
        return True  # nothing to secure
    return stat.S_IMODE(path.stat().st_mode) == _OWNER_RW
