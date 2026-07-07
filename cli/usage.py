"""Thin wrapper around ccusage for Claude Code token/cache/cost visibility.

Distinct from cli/cost.py, which tracks sigma's OWN heavy-op token estimates
(review/loop/research) in sigma/costs.jsonl — this module reports Anthropic's
real session usage data, sourced from ccusage (https://ccusage.com), a mature
local-only CLI that already parses Claude Code's JSONL transcript tree.

Mirrors cli/statusline.py exactly: node-runtime detection and argv building are
pure/injectable so tests never touch the network or spawn a real process. No
new sigma-side flags — every arg after `usage` passes through to ccusage
unmodified.
"""

from __future__ import annotations

import shutil
from typing import Callable, List, Optional

MISSING_NODE_MESSAGE = (
    "npx not found — install Node.js to use 'sigma usage' (wraps ccusage: "
    "https://ccusage.com)"
)


def node_runtime_available(which: Optional[Callable] = None) -> bool:
    """True if `npx` or `bunx` is on PATH (needed to run ccusage)."""
    which = which or shutil.which
    return which("npx") is not None or which("bunx") is not None


def build_argv(passthrough_args: List[str]) -> List[str]:
    """Prepend the ccusage invocation to whatever args the user passed after
    `sigma usage`. Pure — no I/O, no mutation of the input list.
    """
    return ["npx", "-y", "ccusage@latest", *passthrough_args]
