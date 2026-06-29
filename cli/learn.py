"""`sigma learn` — learn a codebase, persist durable understanding artifacts.

Drives the AgentRunner (the single execution chokepoint) to produce two artifacts
that survive the session:

  - ARCHITECTURE.md       — an onboarding architecture map (CLAUDE.md-style)
  - .tours/<slug>.tour    — a CodeTour JSON walkthrough anchored to real files

graphify is NOT imported (it needs Python 3.10+; sigma stays on 3.9). Instead,
`sigma learn` SHELLS OUT to a standalone `graphify` binary — when present, it
builds an incremental knowledge graph and injects graphify's GRAPH_REPORT.md into
the agent prompt, grounding both artifacts in extracted structure (god-nodes,
communities, call/import edges). The build is best-effort and the injection is
fail-safe: graphify absent or a build failure degrades to a plain agent read
(byte-identical prompt), never a crash. See cli/graphify.py. The bundled
`code-tour` + `codebase-onboarding` skills are injected so the agent follows their
conventions (and they also work standalone in Claude Code).

Output parsing, prompt building, and validation are pure/injectable so the whole
flow is testable without spawning a real agent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from cli.codetour import validate_tour
from cli.graphify import build_extract_argv, graphify_status, report_block
from cli.paths import slugify
from cli.runner import AgentRunner, write_artifact
from cli.skill_map import vendor_dir

# Sentinel that separates the architecture map from the tour JSON block in the
# agent's output. The agent is instructed to emit exactly this structure.
ARCH_HEADER = "=== ARCHITECTURE.md ==="
TOUR_HEADER = "=== TOUR.json ==="

# Bundled skills that teach the agent the two artifact formats.
LEARN_SKILLS = ["codebase-onboarding", "code-tour"]

LEARN_INSTRUCTIONS = """Learn this codebase and produce TWO artifacts in one reply.

{persona_line}Read the project under: {root}

Emit your reply in EXACTLY this structure, nothing before or after:

{arch_header}
<a Markdown architecture map: purpose, entry points, module layout, data flow,
key conventions, and where a newcomer should start. Be concrete and specific to
THIS repo — name real files and directories.>

{tour_header}
<a single JSON object in the Microsoft CodeTour format: an object with "title"
(string) and "steps" (array). Each step has "description" (Markdown) and, when it
anchors to code, "file" (a path RELATIVE to the project root) plus EITHER "line"
(1-based) OR "pattern" (a substring that appears on the target line). Anchor every
code step to a file that really exists. Output ONLY the JSON object here — no code
fence, no commentary.>
"""


@dataclass
class LearnResult:
    ok: bool
    architecture_path: Optional[Path] = None
    tour_path: Optional[Path] = None
    tour_problems: List[str] = field(default_factory=list)
    error: Optional[str] = None
    prompt: str = ""
    graph_built: bool = False
    graph_note: Optional[str] = None


def build_learn_prompt(
    root: Path,
    persona: Optional[str],
    vendor: Optional[Path] = None,
    graph_block: str = "",
) -> str:
    """Build the learn prompt, injecting the bundled learn skills.

    `graph_block` (graphify's GRAPH_REPORT.md, when present) is prepended to the
    task body so the agent grounds its map in extracted structure. An empty block
    leaves the prompt byte-identical to the no-graph case (fail-safe).
    """
    persona_line = f"Target audience / persona: {persona}\n\n" if persona else ""
    body = LEARN_INSTRUCTIONS.format(
        persona_line=persona_line,
        root=root,
        arch_header=ARCH_HEADER,
        tour_header=TOUR_HEADER,
    )
    if graph_block:
        body = f"{graph_block}\n\n{body}"
    vendor = vendor or vendor_dir()
    return _inject_learn_skills(body, vendor)


def _inject_learn_skills(prompt: str, vendor: Path) -> str:
    """Prepend the learn skills' bodies. They live top-level under skills/vendor/.

    LEARN_SKILLS aren't pipeline stages, so we read them directly from
    skills/vendor/<slug>/SKILL.md rather than through skill_map's stage mapping.
    """
    blocks: List[str] = []
    for slug in LEARN_SKILLS:
        f = vendor / slug / "SKILL.md"
        if f.exists():
            # Header must NOT start with '-' — a leading dash makes the agent CLI
            # parse the prompt as an option flag (claude -p reads it positionally).
            blocks.append(f"### skill: {slug}\n{f.read_text()}")
    if not blocks:
        return prompt
    return "\n\n".join(blocks) + f"\n\n### task\n{prompt}"


def split_output(output: str) -> tuple:
    """Split agent output into (architecture_md, tour_json_str).

    Returns (arch_text, tour_text); either may be empty if its header is absent.
    Tolerant of a fenced ```json block around the tour.
    """
    arch_text = ""
    tour_text = ""
    if ARCH_HEADER in output:
        after_arch = output.split(ARCH_HEADER, 1)[1]
        if TOUR_HEADER in after_arch:
            arch_text, tour_text = after_arch.split(TOUR_HEADER, 1)
        else:
            arch_text = after_arch
    elif TOUR_HEADER in output:
        tour_text = output.split(TOUR_HEADER, 1)[1]
    return arch_text.strip(), _strip_fence(tour_text.strip())


def _strip_fence(text: str) -> str:
    """Remove a surrounding ```json ... ``` fence if the agent added one."""
    if text.startswith("```"):
        # Drop the first fence line and a trailing fence.
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def run_learn(
    root: Path,
    persona: Optional[str] = None,
    topic: Optional[str] = None,
    agent: Optional[AgentRunner] = None,
    vendor: Optional[Path] = None,
    dry_run: bool = False,
    build_graph: bool = True,
    graph_runner: Optional[Callable[[List[str], Path], int]] = None,
    which: Optional[Callable] = None,
) -> LearnResult:
    """Drive the agent to learn `root`, then write + validate the artifacts.

    When `build_graph` is set and graphify is installed, build (or incrementally
    refresh) the repo's knowledge graph first, then inject graphify's report into
    the prompt. Both steps are fail-safe — graphify absent, or a build that errors,
    degrades to a plain agent read (the prompt is byte-identical to the no-graph
    case). `graph_runner`/`which` are injectable so tests never spawn graphify.
    """
    root = root.resolve()

    graph_built, graph_note = _maybe_build_graph(
        root, build_graph, graph_runner, which, dry_run
    )
    graph_block = report_block(root)
    prompt = build_learn_prompt(root, persona, vendor=vendor, graph_block=graph_block)

    if dry_run:
        return LearnResult(ok=True, prompt=prompt, graph_built=graph_built, graph_note=graph_note)

    agent = agent or AgentRunner()
    result = agent.run(prompt, cwd=root)
    if not result.ok:
        return LearnResult(
            ok=False, error=result.error or "agent run failed", prompt=prompt,
            graph_built=graph_built, graph_note=graph_note,
        )

    arch_text, tour_text = split_output(result.output)
    if not arch_text and not tour_text:
        return LearnResult(
            ok=False,
            error="agent output had neither an ARCHITECTURE.md nor a TOUR.json section",
            prompt=prompt,
            graph_built=graph_built,
            graph_note=graph_note,
        )

    arch_path: Optional[Path] = None
    if arch_text:
        arch_path = write_artifact(root / "ARCHITECTURE.md", arch_text + "\n")

    tour_path: Optional[Path] = None
    problems: List[str] = []
    if tour_text:
        tour_path, problems = _write_tour(root, tour_text, topic)

    # Refresh the static CLAUDE.local.md pointer so the artifacts surface in every
    # session even without the SessionStart hook. Best-effort — a failed write is
    # never fatal (same fail-safe discipline as the graphify build above).
    _refresh_local_pointer(root)

    return LearnResult(
        ok=True,
        architecture_path=arch_path,
        tour_path=tour_path,
        tour_problems=problems,
        prompt=prompt,
        graph_built=graph_built,
        graph_note=graph_note,
    )


def _maybe_build_graph(
    root: Path,
    build_graph: bool,
    graph_runner: Optional[Callable[[List[str], Path], int]],
    which: Optional[Callable],
    dry_run: bool,
) -> tuple:
    """Best-effort graphify extract. Returns (built?, note).

    Fail-safe: skipped when disabled, on a dry run, or when graphify isn't
    installed; a non-zero/raising run yields (False, note) but never propagates.
    """
    if not build_graph or dry_run:
        return False, None
    if not graphify_status(which=which).get("installed"):
        return False, "graphify not installed — run without a knowledge graph (sigma onboard installs it)"

    runner = graph_runner or _default_graph_runner
    argv = build_extract_argv(root)
    try:
        code = runner(argv, root)
    except OSError as exc:
        return False, f"graphify extract failed to start: {exc}"
    if code != 0:
        return False, f"graphify extract exited {code} — proceeding without a fresh graph"
    return True, None


def _default_graph_runner(argv: List[str], cwd: Path) -> int:
    """Run graphify extract with cwd=root; return its exit code (never raises here)."""
    import subprocess

    try:
        proc = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, timeout=1800)
        return proc.returncode
    except subprocess.SubprocessError as exc:  # timeout etc. — treat as a soft failure
        raise OSError(str(exc)) from exc


def _refresh_local_pointer(root: Path) -> None:
    """Upsert the learn-artifact pointer into CLAUDE.local.md (best-effort)."""
    try:
        from cli.claude_local import write_block
        from cli.session_context import build_pointer

        write_block(root, build_pointer(root))
    except Exception:  # noqa: BLE001 — the static fallback must never break learn
        pass


def _write_tour(root: Path, tour_text: str, topic: Optional[str]) -> tuple:
    """Parse, validate, and write the .tour file. Returns (path|None, problems)."""
    try:
        data = json.loads(tour_text)
    except (json.JSONDecodeError, ValueError) as exc:
        return None, [f"tour JSON did not parse: {exc}"]

    problems = validate_tour(data, root)
    title = data.get("title") if isinstance(data, dict) else None
    slug = slugify(topic or (title if isinstance(title, str) else "") or "codebase")
    tours_dir = root / ".tours"
    path = tours_dir / f"{slug}.tour"
    # Persist even with anchor problems — the caller surfaces them; a tour that
    # mostly anchors is more useful than none, and the problems list is the signal.
    write_artifact(path, json.dumps(data, indent=2) + "\n")
    return path, problems
