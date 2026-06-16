#!/usr/bin/env python3
"""sigma — personal AI workflow toolkit CLI.

Skeleton entry point. Wraps Claude Code with the sigma pipeline and the
multi-model research phase. See docs/2026-06-16-sigma-design.md.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

__version__ = "0.1.0"

PIPELINE = [
    ("research", "Multi-model parallel research → research.md"),
    ("propose", "Synthesize research → 2-3 approaches"),
    ("blueprint", "Chosen approach → architecture.md"),
    ("spec", "Detailed spec.md"),
    ("tasks", "Domain-routed task breakdown"),
    ("implement-task", "Implement one task with domain context"),
    ("verify", "Independent domain verification"),
    ("loop", "Autonomous discover→implement→verify→ratchet"),
]

DOMAINS = [
    "classic-ml", "deep-learning", "nlp", "rl", "data-analysis",
    "data-engineering", "ai-agent-engineering", "mlops", "llm-engineering",
]


def cmd_init(_: argparse.Namespace) -> int:
    """Scaffold sigma.config.yml in the current project (interactive later)."""
    print("sigma init — TODO: interactive domain selection, write sigma.config.yml")
    print("Available domains:")
    for d in DOMAINS:
        print(f"  - {d}")
    return 0


def cmd_research(args: argparse.Namespace) -> int:
    """Spawn Claude/Gemini/GPT researchers in parallel, aggregate to research.md."""
    models = args.models.split(",") if args.models else ["claude", "gemini", "gpt"]
    print(f"sigma research — topic={args.topic!r} models={models}")
    print("TODO: subprocess fan-out (claude -p / gemini / openai), aggregate, write research.md")
    return 0


def cmd_pipeline_stub(args: argparse.Namespace) -> int:
    print(f"sigma {args._name} — TODO: drive Claude Code with commands/{args._name}.md")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sigma", description="Personal AI workflow toolkit.")
    p.add_argument("--version", action="version", version=f"sigma {__version__}")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("init", help="Scaffold sigma.config.yml for this project").set_defaults(func=cmd_init)

    pr = sub.add_parser("research", help="Multi-model research")
    pr.add_argument("topic")
    pr.add_argument("--models", help="comma list: claude,gemini,gpt")
    pr.set_defaults(func=cmd_research)

    for name, desc in PIPELINE:
        if name == "research":
            continue
        sp = sub.add_parser(name, help=desc)
        sp.set_defaults(func=cmd_pipeline_stub, _name=name)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not getattr(args, "command", None):
        build_parser().print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
