"""Pure diagnostic probes for `sigma doctor` and `sigma onboard`.

Each probe returns a `Check` (status + detail + optional fix). Probes are pure:
they never print and never mutate state. A `fix` is a `(description, callable)`
pair — the engine surfaces it, but the *caller* (doctor/onboard) decides whether
and when to run it, always confirm-gated. External lookups (`shutil.which`, the
interpreter version, importability, rtk status) are injected so the whole engine
is testable with fakes and never spawns a real subprocess.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from cli import secrets
from cli.config import load_config
from cli.events import read_events
from cli.paths import sigma_home

OK = "ok"
WARN = "warn"
FAIL = "fail"

Fix = Tuple[str, Callable[[], bool]]

# Model CLIs sigma can fan out to during research, keyed by sigma model name with
# the actual executable to probe on PATH (gpt is driven via the Codex CLI).
_MODEL_EXES = {"claude": "claude", "gemini": "gemini", "gpt": "codex"}
# How to authenticate each, shown as guidance (never auto-run).
_AUTH_HINT = {
    "gemini": "gemini  (sign in with Google / GEMINI_API_KEY)",
    "gpt": "codex login  (uses your ChatGPT subscription)",
    "claude": "claude  (already authed if you're running it)",
}


@dataclass
class Check:
    name: str
    status: str
    detail: str
    fix: Optional[Fix] = None

    @property
    def fixable(self) -> bool:
        return self.fix is not None


# --------------------------------------------------------------------------- #
# individual probes
# --------------------------------------------------------------------------- #
def check_python(version: Optional[tuple] = None) -> Check:
    version = version or sys.version_info[:3]
    if version[:2] >= (3, 9):
        return Check("python", OK, f"Python {version[0]}.{version[1]} (>=3.9)")
    return Check(
        "python", FAIL,
        f"Python {version[0]}.{version[1]} too old — sigma targets 3.9+",
    )


def check_deps(probe: Optional[Callable[[str], bool]] = None) -> Check:
    probe = probe or (lambda mod: importlib.util.find_spec(mod) is not None)
    required = ["yaml", "rich"]
    missing = [m for m in required if not probe(m)]
    if not missing:
        return Check("deps", OK, "pyyaml + rich present")
    pretty = {"yaml": "pyyaml", "rich": "rich"}
    pkgs = " ".join(pretty[m] for m in missing)
    return Check(
        "deps", FAIL, f"missing: {pkgs}",
        fix=(f"pip install {pkgs}", lambda: _pip_install(pkgs)),
    )


def check_models(which: Optional[Callable] = None) -> Check:
    which = which or shutil.which
    present = [m for m, exe in _MODEL_EXES.items() if which(exe)]
    if not present:
        return Check("models", WARN, "no model CLIs found (research degrades gracefully)")
    return Check("models", OK, f"model CLIs: {', '.join(present)}")


def check_model_auth(which: Optional[Callable] = None) -> Check:
    which = which or shutil.which
    present = [m for m, exe in _MODEL_EXES.items() if which(exe)]
    if not present:
        return Check("model-auth", WARN, "no model CLIs to authenticate")
    hints = "; ".join(f"{m}: `{_AUTH_HINT[m]}`" for m in present)
    return Check("model-auth", OK, f"present CLIs (auth as needed) — {hints}")


def check_secrets() -> Check:
    missing = secrets.missing_keys()
    if not missing:
        return Check("secrets", OK, "model API keys present")
    return Check(
        "secrets", WARN,
        f"no key for: {', '.join(missing)} (set via `sigma onboard`)",
    )


def check_vendored_skills(home: Optional[Path] = None) -> Check:
    home = home or sigma_home()
    vendor = home / "skills" / "vendor"
    if not vendor.exists() or not any(vendor.rglob("SKILL.md")):
        return Check(
            "vendored-skills", FAIL, "skills/vendor/ missing or empty",
            fix=("re-vendor bundled skills", lambda: False),
        )
    count = len(list(vendor.rglob("SKILL.md")))
    return Check("vendored-skills", OK, f"{count} bundled skill(s) present")


def check_plugin(home: Optional[Path] = None) -> Check:
    import json

    home = home or sigma_home()
    manifest = home / ".claude-plugin" / "plugin.json"
    if not manifest.exists():
        return Check("plugin", WARN, "no .claude-plugin/plugin.json (CLI still works)")
    try:
        data = json.loads(manifest.read_text())
    except (json.JSONDecodeError, ValueError) as exc:
        return Check("plugin", FAIL, f"plugin.json invalid: {exc}")
    if "name" not in data:
        return Check("plugin", FAIL, "plugin.json missing 'name'")
    return Check("plugin", OK, f"plugin manifest ok ({data['name']})")


def check_config(root: Optional[Path] = None) -> Check:
    cfg_file = (root or Path.cwd()) / "sigma.config.yml"
    if not cfg_file.exists():
        return Check("config", WARN, "no sigma.config.yml here (run `sigma init`)")
    try:
        cfg = load_config(root=root)
    except Exception as exc:  # noqa: BLE001 - surface any parse error as a check
        return Check("config", FAIL, f"config unreadable: {exc}")
    errors = cfg.validate()
    if errors:
        return Check("config", FAIL, "; ".join(errors))
    return Check("config", OK, f"config valid ({', '.join(cfg.domains)})")


def check_workspaces(root: Optional[Path] = None) -> Check:
    specs = (root or Path.cwd()) / "sigma" / "specs"
    if not specs.exists():
        return Check("workspaces", OK, "no spec workspaces yet")
    corrupt: List[str] = []
    raw_lines = 0
    for ws in specs.iterdir():
        ev_file = ws / "events.jsonl"
        if not ev_file.exists():
            continue
        lines = [ln for ln in ev_file.read_text().splitlines() if ln.strip()]
        raw_lines += len(lines)
        parsed = read_events(ws)
        if len(parsed) < len(lines):
            corrupt.append(ws.name)
    if corrupt:
        return Check("workspaces", WARN, f"corrupt events in: {', '.join(corrupt)}")
    return Check("workspaces", OK, f"{raw_lines} event(s) across workspaces")


def check_rtk(status_fn: Optional[Callable[[], Dict]] = None) -> Check:
    """RTK token-saver: installed? hook active for Claude? `rtk gain` works?"""
    if status_fn is None:
        from cli.rtk import rtk_status

        status_fn = rtk_status
    st = status_fn()
    # The fixer is confirm-gated at the doctor layer; here we auto-approve since
    # the user already said yes to applying this specific fix.
    def _fix() -> bool:
        from cli.rtk import setup_rtk

        return setup_rtk(status_fn=status_fn, confirm=lambda _msg: True)

    if not st.get("installed"):
        return Check(
            "rtk", WARN, "RTK not installed (optional 60-90% token saver)",
            fix=("install RTK + activate for Claude (rtk init -g)", _fix),
        )
    if not st.get("gain_ok"):
        return Check(
            "rtk", WARN,
            "an `rtk` is on PATH but `rtk gain` failed — possible name collision",
        )
    if not st.get("hook_active"):
        return Check(
            "rtk", WARN, "RTK installed but not activated for Claude",
            fix=("activate RTK for Claude (rtk init -g)", _fix),
        )
    return Check("rtk", OK, "RTK installed + activated for Claude")


def check_caveman(status_fn: Optional[Callable[[], Dict]] = None) -> Check:
    """Caveman terse-output mode: plugin installed? SessionStart hook active?"""
    if status_fn is None:
        from cli.caveman import caveman_status

        status_fn = caveman_status
    st = status_fn()

    def _fix() -> bool:
        from cli.caveman import setup_caveman

        return setup_caveman(status_fn=status_fn, confirm=lambda _msg: True)

    if not st.get("claude_cli"):
        return Check("caveman", WARN, "no `claude` CLI — can't install the caveman plugin")
    if not st.get("installed"):
        return Check(
            "caveman", WARN, "caveman not installed (optional ~75% token saver)",
            fix=("install caveman plugin for Claude", _fix),
        )
    if not st.get("hook_active"):
        return Check(
            "caveman", WARN, "caveman installed but its session hook is not active",
            fix=("re-install caveman to register its hook", _fix),
        )
    return Check("caveman", OK, "caveman installed + active for Claude")


# --------------------------------------------------------------------------- #
# aggregate
# --------------------------------------------------------------------------- #
def run_all(
    home: Optional[Path] = None,
    root: Optional[Path] = None,
    which: Optional[Callable] = None,
    rtk_status_fn: Optional[Callable] = None,
    caveman_status_fn: Optional[Callable] = None,
) -> List[Check]:
    """Run every probe and return the results in display order."""
    return [
        check_python(),
        check_deps(),
        check_models(which=which),
        check_model_auth(which=which),
        check_secrets(),
        check_vendored_skills(home=home),
        check_plugin(home=home),
        check_config(root=root),
        check_workspaces(root=root),
        check_rtk(status_fn=rtk_status_fn),
        check_caveman(status_fn=caveman_status_fn),
    ]


def _pip_install(pkgs: str) -> bool:
    import subprocess

    argv = [sys.executable, "-m", "pip", "install", *pkgs.split()]
    return subprocess.call(argv) == 0
