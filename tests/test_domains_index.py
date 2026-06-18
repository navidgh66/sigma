"""Tests for cli.domains_index — pure index over the domain context-engines."""

from __future__ import annotations

from cli.domains_index import (
    LOGIC_EVALUATOR,
    resolve_all,
    resolve_domain,
    validate_domains,
)
from cli.paths import DOMAINS


# --------------------------- against the real repo --------------------------- #
def test_all_real_domains_are_well_formed():
    # The shipped context-engines must all resolve cleanly.
    problems = validate_domains()
    assert problems == [], f"context-engine problems: {problems}"


def test_resolve_all_covers_every_known_domain():
    resolved = {c.domain for c in resolve_all()}
    assert resolved == set(DOMAINS)


def test_resolve_real_domain_has_files():
    ctx = resolve_domain("nlp")
    assert ctx.exists
    assert ctx.implementers  # non-empty
    assert ctx.verifiers
    assert ctx.has_logic_evaluator
    assert LOGIC_EVALUATOR in ctx.verifiers


# --------------------------- against a synthetic tree --------------------------- #
def _fake_home(tmp_path, domain, *, impl=True, verf=True, logic=True):
    root = tmp_path / "context-engines" / domain
    if impl:
        (root / "implementers").mkdir(parents=True)
        (root / "implementers" / "thing.md").write_text("# impl")
    if verf:
        (root / "verifiers").mkdir(parents=True)
        (root / "verifiers" / "checks.md").write_text("# verf")
        if logic:
            (root / "verifiers" / LOGIC_EVALUATOR).write_text("# logic")
    return tmp_path


def test_validate_flags_missing_logic_evaluator(tmp_path):
    # Only build the first known domain, missing its logic-evaluator.
    home = _fake_home(tmp_path, DOMAINS[0], logic=False)
    problems = validate_domains(home=home)
    assert any(f"missing verifiers/{LOGIC_EVALUATOR}" in p for p in problems)


def test_validate_flags_missing_dir(tmp_path):
    # Empty tree → every domain missing.
    problems = validate_domains(home=tmp_path)
    assert len(problems) == len(DOMAINS)
    assert all("missing context-engine dir" in p for p in problems)


def test_resolve_domain_absent(tmp_path):
    ctx = resolve_domain(DOMAINS[0], home=tmp_path)
    assert not ctx.exists
    assert ctx.implementers == []
    assert ctx.has_logic_evaluator is False
