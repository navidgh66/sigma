"""`sigma onboard` — the friendly first-run setup (a real TTY, unlike curl|sh).

Shows the logo, runs the health checks, lets you pick domains + capture model API
keys (hidden input → ~/.sigma/.env, never the committed config), prints sign-in
guidance, and offers to install + activate RTK. Idempotent — safe to re-run.

All interactive inputs (domain text, secret entry, confirm, spawn) are injected,
so the orchestration is fully testable without a real terminal or any install.
"""

from __future__ import annotations

from getpass import getpass
from typing import Callable, List, Optional

from cli import caveman as caveman_mod
from cli import checks as checks_mod
from cli import graphify as graphify_mod
from cli import render, rtk, secrets
from cli import session_hook as session_hook_mod
from cli import statusline as statusline_mod
from cli.config import SigmaConfig, write_config
from cli.paths import DOMAINS


def parse_domain_selection(raw: str, available: List[str]) -> List[str]:
    """Map a '1,3' style selection onto available domains. Empty → all."""
    raw = raw.strip()
    if not raw:
        return list(available)
    chosen: List[str] = []
    for token in raw.split(","):
        token = token.strip()
        if not token.isdigit():
            continue
        idx = int(token) - 1
        if 0 <= idx < len(available) and available[idx] not in chosen:
            chosen.append(available[idx])
    return chosen


def run_onboard(
    name: Optional[str] = None,
    domains: Optional[List[str]] = None,
    domain_input: Optional[Callable[[], str]] = None,
    secret_input: Optional[Callable[[str], str]] = None,
    confirm: Optional[Callable[[str], bool]] = None,
    rtk_status_fn: Optional[Callable] = None,
    caveman_status_fn: Optional[Callable] = None,
    statusline_status_fn: Optional[Callable] = None,
    graphify_status_fn: Optional[Callable] = None,
    spawn: Optional[Callable] = None,
    which: Optional[Callable] = None,
    run_all: Optional[Callable] = None,
    use_rich: bool = True,
) -> None:
    """Interactive setup. Writes sigma.config.yml + ~/.sigma/.env; offers RTK."""
    domains = domains if domains is not None else list(DOMAINS)
    domain_input = domain_input or (lambda: input("Domains (e.g. 1,3 — blank = all): "))
    secret_input = secret_input or (lambda key: getpass(f"  {key} (blank to skip): "))
    confirm = confirm or render.confirm
    run_all = run_all or checks_mod.run_all

    render.print_logo(use_rich=use_rich)

    # 1. Health snapshot.
    results = run_all(which=which) if which is not None else run_all()
    if results:
        render.print_checks(results, use_rich=use_rich)

    # 2. Domain selection.
    for i, d in enumerate(domains, 1):
        print(f"  {i}. {d}")
    chosen = parse_domain_selection(domain_input(), domains)

    # 3. Config (written once, atomically — secrets never go here).
    cfg = SigmaConfig(name=name or "my-project", domains=chosen)
    write_config(cfg)
    print(f"✓ wrote sigma.config.yml ({', '.join(chosen)})")

    # 4. Secrets → ~/.sigma/.env (chmod 600), only if user provides them.
    for key in secrets.missing_keys():
        value = secret_input(key)
        if value:
            secrets.write_key(key, value)
            print(f"  ✓ stored {key} in ~/.sigma/.env (chmod 600)")

    # 5. Sign-in guidance for model CLIs (detect + show command, never auto-run).
    auth = checks_mod.check_model_auth(which=which) if which is not None else checks_mod.check_model_auth()
    if auth.detail:
        print(f"  ℹ {auth.detail}")

    # 6. RTK — confirm-gated install + activate (touches global settings.json).
    changed = rtk.setup_rtk(
        status_fn=rtk_status_fn, confirm=confirm, which=which, spawn=spawn
    )
    if changed:
        print("  ✓ RTK set up — restart Claude Code for it to take effect")

    # 7. Caveman — confirm-gated terse-output mode (also touches global state).
    cave_changed = caveman_mod.setup_caveman(
        status_fn=caveman_status_fn, confirm=confirm, which=which, spawn=spawn
    )
    if cave_changed:
        print("  ✓ caveman set up — restart Claude Code for it to take effect")

    # 8. ccstatusline — confirm-gated status line (writes settings.json statusLine).
    sl_changed = statusline_mod.setup_statusline(
        status_fn=statusline_status_fn, confirm=confirm, which=which
    )
    if sl_changed:
        print("  ✓ ccstatusline configured — restart Claude Code for it to take effect")

    # 9. graphify — confirm-gated install of the codebase knowledge-graph engine
    #    that `sigma learn` shells out to (isolated 3.10+ env; sigma stays 3.9).
    graph_changed = graphify_mod.setup_graphify(
        status_fn=graphify_status_fn, confirm=confirm, which=which, spawn=spawn
    )
    if graph_changed:
        print("  ✓ graphify installed — `sigma learn` will build a knowledge graph")

    # 10. SessionStart hook — confirm-gated. Surfaces this repo's learn artifacts
    #     (ARCHITECTURE.md / tour) at the start of every Claude Code session.
    hook_changed = session_hook_mod.setup_session_hook(confirm=confirm)
    if hook_changed:
        print("  ✓ session hook added — new sessions will read this repo's learn artifacts")
        print("    (run `sigma learn` to build them if you haven't yet)")

    print("\n✓ onboarding complete. Try:  sigma research \"your topic\"")
