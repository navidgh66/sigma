from cli.docs_check import check_test_count_claims, check_version_parity
from cli.docs_check_run import run_docs_check


def test_version_parity_match_is_clean():
    assert check_version_parity('__version__ = "0.24.0"', '{"version": "0.24.0"}') == []


def test_version_parity_mismatch_is_high():
    findings = check_version_parity('__version__ = "0.24.0"', '{"version": "0.23.0"}')
    assert len(findings) == 1
    assert findings[0].severity == "HIGH"
    assert "0.24.0" in findings[0].message and "0.23.0" in findings[0].message


def test_version_parity_unparseable_is_high():
    findings = check_version_parity("no version here", '{"version": "0.23.0"}')
    assert len(findings) == 1
    assert "unverifiable" in findings[0].message


def test_count_claims_flags_badge_and_prose():
    text = (
        "[![Tests](https://img.shields.io/badge/tests-779%20passing-brightgreen.svg)](tests/)\n"
        "run all 866 pytest tests\n"
        "→ 232 passed\n"
    )
    findings = check_test_count_claims(text, "README.md", 900)
    assert len(findings) == 3
    assert all(f.severity == "HIGH" for f in findings)


def test_count_claims_matching_count_is_clean():
    assert check_test_count_claims("900 pytest tests, 900 passed", "CLAUDE.md", 900) == []


def test_count_claims_skip_when_count_unknown():
    # Never flag on absent evidence (the prune law).
    assert check_test_count_claims("866 pytest tests", "CLAUDE.md", None) == []


def test_count_claims_ignore_small_incidental_numbers():
    # "22 passed" in a subset-run example must not flag (3-digit floor).
    assert check_test_count_claims("subset: 22 passed", "docs/PLAYGROUND.md", 900) == []


def _scaffold(tmp_path, init_version="0.24.0", plugin_version="0.24.0"):
    (tmp_path / "cli").mkdir()
    (tmp_path / "cli" / "__init__.py").write_text(f'__version__ = "{init_version}"\n')
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / ".claude-plugin" / "plugin.json").write_text(
        f'{{"name": "sigma", "version": "{plugin_version}"}}\n'
    )


def test_run_docs_check_clean_tree_passes(tmp_path):
    _scaffold(tmp_path)
    (tmp_path / "README.md").write_text("badge: tests-900%20passing\n")
    res = run_docs_check(tmp_path, test_count_fn=lambda root: 900)
    assert res.ok
    assert res.findings == []
    assert res.gate.passed
    assert "README.md" in res.files_checked


def test_run_docs_check_fails_gate_on_drift(tmp_path):
    _scaffold(tmp_path, plugin_version="0.23.0")
    (tmp_path / "README.md").write_text("tests-779%20passing\n")
    res = run_docs_check(tmp_path, test_count_fn=lambda root: 900)
    assert res.ok
    assert not res.gate.passed
    files = {f.file for f in res.findings}
    assert ".claude-plugin/plugin.json" in files
    assert "README.md" in files


def test_run_docs_check_missing_version_file_errors(tmp_path):
    res = run_docs_check(tmp_path, test_count_fn=lambda root: 900)
    assert not res.ok
    assert "cli/__init__.py" in res.error


def test_run_docs_check_skips_missing_doc_surfaces(tmp_path):
    _scaffold(tmp_path)  # no README/CLAUDE/PLAYGROUND at all
    res = run_docs_check(tmp_path, test_count_fn=lambda root: 900)
    assert res.ok
    assert res.gate.passed
