"""Tests for release programmatic semantic-risk checks."""

from certfix.core.programmatic_checks import run_programmatic_checks


def test_release_v1_excludes_same_resource_early_return() -> None:
    findings = run_programmatic_checks(
        original_code="void f(lock_t *a, lock_t *b) { lock(a); lock(b); }",
        fixed_code="void f(lock_t *a, lock_t *b) { if (a == b) return; lock(a); lock(b); }",
        rule_id="POS51-C",
    )

    assert [finding.check_id for finding in findings] == []


def test_exp44_sizeof_side_effect_materialized_blocks() -> None:
    findings = run_programmatic_checks(
        original_code="void f(int i) { size_t n = sizeof(i++); }",
        fixed_code="void f(int i) { i++; size_t n = sizeof(i); }",
        rule_id="EXP44-C",
    )

    assert [finding.check_id for finding in findings] == [
        "exp44_sizeof_side_effect_materialized"
    ]
    assert findings[0].rule_id == "EXP44-C"
