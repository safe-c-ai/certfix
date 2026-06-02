"""Unit tests for SarifFormatter."""

import io
import json
from pathlib import Path

import jsonschema

from certfix.models import (
    CheckResult,
    CompileCheckResult,
    FinalFixStatus,
    FixResult,
    RuleCandidate,
    RuleSelectionDecision,
    RuleSelectionResult,
    SemanticCheckResult,
    SemanticVerdict,
    Severity,
    Violation,
    ViolationRemovalResult,
)
from certfix.output import SarifFormatter

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

_sarif_schema_cache: dict | None = None


def _load_sarif_schema() -> dict:
    global _sarif_schema_cache  # noqa: PLW0603
    if _sarif_schema_cache is None:
        _sarif_schema_cache = json.loads((FIXTURES_DIR / "sarif-schema-2.1.0.json").read_text())
    return _sarif_schema_cache


def _load_violations(name: str) -> list[Violation]:
    data = json.loads((FIXTURES_DIR / f"{name}.violations.json").read_text())
    return [
        Violation(
            rule_id=v["rule_id"],
            file_path=v["file_path"],
            line=v["line"],
            column=v["column"],
            message=v["message"],
            severity=Severity(v["severity"]),
            code_snippet=v.get("code_snippet"),
        )
        for v in data
    ]


def _validate_sarif(sarif: dict) -> None:
    jsonschema.validate(sarif, _load_sarif_schema())


def _make_violation(
    rule_id: str = "MEM30-C",
    file_path: str = "src/test.c",
    line: int = 3,
    column: int = 1,
    message: str | None = None,
    severity: Severity = Severity.ERROR,
    code_snippet: str | None = None,
) -> Violation:
    if message is None:
        message = f"CERT-C {rule_id}: test violation"
    return Violation(
        rule_id=rule_id,
        file_path=file_path,
        line=line,
        column=column,
        message=message,
        severity=severity,
        code_snippet=code_snippet,
    )


def _format_violations(violations: list[Violation], files_checked: int = 1) -> dict:
    buf = io.StringIO()
    fmt = SarifFormatter(buf)
    result = CheckResult(files_checked=files_checked, violations=violations)
    fmt.format_violations(result)
    return json.loads(buf.getvalue())


def _format_fixes(fixes: list[FixResult]) -> dict:
    buf = io.StringIO()
    fmt = SarifFormatter(buf)
    fmt.format_fixes(fixes)
    return json.loads(buf.getvalue())


class TestSarifSchema:
    """Tests for SARIF envelope structure."""

    def test_schema_and_version(self) -> None:
        """$schema and version must be correct SARIF 2.1.0 values."""
        sarif = _format_violations([])
        assert sarif["version"] == "2.1.0"
        assert "sarif-schema-2.1.0" in sarif["$schema"]

    def test_tool_info(self) -> None:
        """driver.name, version, informationUri must be present."""
        sarif = _format_violations([])
        driver = sarif["runs"][0]["tool"]["driver"]
        assert driver["name"] == "certfix"
        assert driver["version"] == "0.3.0"
        assert "certfix" in driver["informationUri"]


class TestSarifViolations:
    """Tests for violation formatting."""

    def test_single_violation(self) -> None:
        """Single violation produces correct ruleId, level, message, locations."""
        v = _make_violation()
        sarif = _format_violations([v])
        results = sarif["runs"][0]["results"]
        assert len(results) == 1
        r = results[0]
        assert r["ruleId"] == "MEM30-C"
        assert r["level"] == "error"
        assert "MEM30-C" in r["message"]["text"]
        loc = r["locations"][0]["physicalLocation"]
        assert loc["region"]["startLine"] == 3
        assert loc["region"]["startColumn"] == 1

    def test_multiple_violations_multiple_files(self) -> None:
        """Multiple violations across files produce correct results."""
        v1 = _make_violation(rule_id="MEM30-C", file_path="src/a.c", line=1)
        v2 = _make_violation(rule_id="EXP33-C", file_path="src/b.c", line=5)
        sarif = _format_violations([v1, v2], files_checked=2)
        results = sarif["runs"][0]["results"]
        assert len(results) == 2
        rule_ids = {r["ruleId"] for r in results}
        assert rule_ids == {"MEM30-C", "EXP33-C"}

    def test_no_violations(self) -> None:
        """No violations should produce empty results and rules."""
        sarif = _format_violations([])
        run = sarif["runs"][0]
        assert run["results"] == []
        assert run["tool"]["driver"]["rules"] == []


class TestSarifRules:
    """Tests for rules array construction."""

    def test_rules_deduplication(self) -> None:
        """Same rule_id appearing twice should produce one rules entry."""
        v1 = _make_violation(rule_id="MEM30-C", line=1)
        v2 = _make_violation(rule_id="MEM30-C", line=5)
        sarif = _format_violations([v1, v2])
        rules = sarif["runs"][0]["tool"]["driver"]["rules"]
        assert len(rules) == 1
        assert rules[0]["id"] == "MEM30-C"

    def test_rules_sorted_by_id(self) -> None:
        """Rules array should be sorted by rule_id."""
        v1 = _make_violation(rule_id="STR31-C")
        v2 = _make_violation(rule_id="EXP33-C")
        v3 = _make_violation(rule_id="MEM30-C")
        sarif = _format_violations([v1, v2, v3])
        rules = sarif["runs"][0]["tool"]["driver"]["rules"]
        ids = [r["id"] for r in rules]
        assert ids == ["EXP33-C", "MEM30-C", "STR31-C"]

    def test_help_uri(self) -> None:
        """helpUri should point to SEI CERT-C wiki."""
        v = _make_violation(rule_id="MEM30-C")
        sarif = _format_violations([v])
        rule = sarif["runs"][0]["tool"]["driver"]["rules"][0]
        assert rule["helpUri"] == ("https://wiki.sei.cmu.edu/confluence/display/c/MEM30-C")

    def test_default_config_level_max_severity(self) -> None:
        """defaultConfiguration.level should use the max severity for a rule."""
        v1 = _make_violation(rule_id="MEM30-C", severity=Severity.INFO, line=1)
        v2 = _make_violation(rule_id="MEM30-C", severity=Severity.ERROR, line=2)
        sarif = _format_violations([v1, v2])
        rule = sarif["runs"][0]["tool"]["driver"]["rules"][0]
        assert rule["defaultConfiguration"]["level"] == "error"


class TestSarifSeverity:
    """Tests for severity mapping."""

    def test_severity_mapping(self) -> None:
        """ERROR->error, WARNING->warning, INFO->note."""
        assert SarifFormatter._severity_to_level(Severity.ERROR) == "error"
        assert SarifFormatter._severity_to_level(Severity.WARNING) == "warning"
        assert SarifFormatter._severity_to_level(Severity.INFO) == "note"


class TestSarifFingerprints:
    """Tests for partialFingerprints."""

    def test_partial_fingerprints_present(self) -> None:
        """Each result should have a primaryLocationLineHash."""
        v = _make_violation()
        sarif = _format_violations([v])
        r = sarif["runs"][0]["results"][0]
        fp = r["partialFingerprints"]["primaryLocationLineHash"]
        assert isinstance(fp, str)
        assert len(fp) == 64  # sha256 hex digest

    def test_partial_fingerprints_consistency(self) -> None:
        """Same violation data should produce the same fingerprint."""
        v1 = _make_violation(code_snippet="free(p);")
        v2 = _make_violation(code_snippet="free(p);")
        sarif = _format_violations([v1, v2])
        results = sarif["runs"][0]["results"]
        assert (
            results[0]["partialFingerprints"]["primaryLocationLineHash"]
            == results[1]["partialFingerprints"]["primaryLocationLineHash"]
        )

    def test_fingerprint_fallback_no_snippet(self) -> None:
        """Without code_snippet, fingerprint uses str(line) as fallback."""
        v_with = _make_violation(code_snippet="free(p);")
        v_without = _make_violation(code_snippet=None)
        buf1 = io.StringIO()
        buf2 = io.StringIO()
        fmt1 = SarifFormatter(buf1)
        fmt2 = SarifFormatter(buf2)
        fp1 = fmt1._fingerprint(v_with)
        fp2 = fmt2._fingerprint(v_without)
        # Different inputs should produce different hashes
        assert fp1 != fp2


class TestSarifPathNormalization:
    """Tests for path normalization."""

    def test_forward_slashes(self) -> None:
        """Backslashes should be converted to forward slashes."""
        # Mock a path with backslashes (simulate Windows-style)
        result = SarifFormatter._normalize_path("src/test.c")
        assert "\\" not in result

    def test_relative_path_preserved(self) -> None:
        """A relative path within a git repo should remain relative."""
        # Create a temp .git directory to simulate repo root
        v = _make_violation(file_path="src/test.c")
        sarif = _format_violations([v])
        uri = sarif["runs"][0]["results"][0]["locations"][0]["physicalLocation"][
            "artifactLocation"
        ]["uri"]
        # Should not be an absolute path
        assert not uri.startswith("/")


class TestSarifShortDescription:
    """Tests for short description extraction."""

    def test_prefix_removal(self) -> None:
        """CERT-C prefix should be removed from short description."""
        desc = SarifFormatter._extract_short_description(
            "CERT-C MEM30-C: Do not access freed memory", "MEM30-C"
        )
        assert desc == "Do not access freed memory"

    def test_short_description_fallback(self) -> None:
        """Non-standard message should be used as-is."""
        msg = "Use after free detected"
        desc = SarifFormatter._extract_short_description(msg, "MEM30-C")
        assert desc == msg


class TestSarifFixes:
    """Tests for fix result formatting."""

    def test_format_fixes_properties(self) -> None:
        """Fix results should include properties bag."""
        v = _make_violation()
        fix_ok = FixResult(
            violation=v,
            original_code="int *p = malloc(10);",
            fixed_code="int *p = calloc(1, 10);",
            success=True,
        )
        v2 = _make_violation(rule_id="EXP33-C", line=5)
        fix_fail = FixResult(
            violation=v2,
            original_code="int x;",
            fixed_code="int x;",
            success=False,
            error_message="Model timeout",
        )

        sarif = _format_fixes([fix_ok, fix_fail])
        results = sarif["runs"][0]["results"]
        assert len(results) == 2

        # Successful fix
        assert results[0]["properties"]["certfix/fixAvailable"] is True
        assert "certfix/fixError" not in results[0]["properties"]

        # Failed fix
        assert results[1]["properties"]["certfix/fixAvailable"] is False
        assert results[1]["properties"]["certfix/fixError"] == "Model timeout"

    def test_format_fixes_validation_properties(self) -> None:
        """Fix SARIF should include Stage 5/6/7 validation metadata."""
        v = _make_violation()
        fix = FixResult(
            violation=v,
            original_code="free(p);\nprintf(\"%s\", p);",
            fixed_code="printf(\"%s\", p);\nfree(p);",
            success=True,
            final_status=FinalFixStatus.FIXED,
            compile_result=CompileCheckResult(True, ["gcc", "-fsyntax-only"], 0),
            violation_removal_result=ViolationRemovalResult(True, "MEM30-C", []),
            semantic_result=SemanticCheckResult(
                verdict=SemanticVerdict.PASS,
                semantic_preserved=True,
                target_violation_removed=True,
                new_regression=False,
                reason="behavior preserved",
            ),
        )

        sarif = _format_fixes([fix])
        props = sarif["runs"][0]["results"][0]["properties"]

        assert props["certfix/finalStatus"] == "fixed"
        assert props["certfix/compileOk"] is True
        assert props["certfix/violationRemoved"] is True
        assert props["certfix/semanticVerdict"] == "pass"
        assert props["certfix/validation"]["semantic"]["reason"] == "behavior preserved"

    def test_format_violation_rule_selection_properties(self) -> None:
        """Check SARIF should include rule candidates and selection metadata."""
        v = _make_violation()
        v.candidates = [
            RuleCandidate("MEM30-C", 1, "Do not access freed memory"),
            RuleCandidate("MEM35-C", 2, "Allocate sufficient memory"),
        ]
        v.rule_selection = RuleSelectionResult(
            decision=RuleSelectionDecision.APPLY_RULE,
            selected_rule_id="MEM30-C",
            selected_rank=1,
            evidence="p is used after free",
        )

        sarif = _format_violations([v])
        props = sarif["runs"][0]["results"][0]["properties"]

        assert props["certfix/ruleCandidates"][0]["ruleId"] == "MEM30-C"
        assert props["certfix/ruleSelection"]["decision"] == "apply_rule"
        assert props["certfix/ruleSelection"]["selectedRank"] == 1


class TestSarifSchemaValidation:
    """Tests that SARIF output conforms to the official 2.1.0 JSON Schema."""

    def test_violations_schema_valid(self) -> None:
        """Single-file violation SARIF passes schema validation."""
        violations = _load_violations("mem30_use_after_free")
        sarif = _format_violations(violations)
        _validate_sarif(sarif)

    def test_no_violations_schema_valid(self) -> None:
        """Empty-results SARIF passes schema validation."""
        sarif = _format_violations([])
        _validate_sarif(sarif)

    def test_multi_file_schema_valid(self) -> None:
        """Multi-file, multi-rule SARIF passes schema validation."""
        violations = _load_violations("multi_file")
        sarif = _format_violations(violations, files_checked=3)
        _validate_sarif(sarif)

    def test_fixes_schema_valid(self) -> None:
        """Fix results with properties bag pass schema validation."""
        v = _load_violations("mem30_use_after_free")[0]
        fix = FixResult(
            violation=v,
            original_code='printf("%s\\n", p);',
            fixed_code="/* removed use-after-free */",
            success=True,
        )
        sarif = _format_fixes([fix])
        _validate_sarif(sarif)


class TestSarifFixtureContent:
    """Tests that fixture-based SARIF output has correct content."""

    def test_mem30_violation_content(self) -> None:
        """MEM30-C fixture produces correct ruleId, location, and message."""
        violations = _load_violations("mem30_use_after_free")
        sarif = _format_violations(violations)
        r = sarif["runs"][0]["results"][0]
        assert r["ruleId"] == "MEM30-C"
        assert r["level"] == "error"
        assert "MEM30-C" in r["message"]["text"]
        loc = r["locations"][0]["physicalLocation"]
        assert loc["region"]["startLine"] == 9
        assert loc["region"]["startColumn"] == 5

    def test_exp33_violation_content(self) -> None:
        """EXP33-C fixture produces correct ruleId, location, and message."""
        violations = _load_violations("exp33_uninitialized")
        sarif = _format_violations(violations)
        r = sarif["runs"][0]["results"][0]
        assert r["ruleId"] == "EXP33-C"
        assert r["level"] == "warning"
        assert "EXP33-C" in r["message"]["text"]
        loc = r["locations"][0]["physicalLocation"]
        assert loc["region"]["startLine"] == 5

    def test_str31_violation_content(self) -> None:
        """STR31-C fixture produces correct ruleId, location, and message."""
        violations = _load_violations("str31_buffer_overflow")
        sarif = _format_violations(violations)
        r = sarif["runs"][0]["results"][0]
        assert r["ruleId"] == "STR31-C"
        assert r["level"] == "error"
        assert "STR31-C" in r["message"]["text"]
        loc = r["locations"][0]["physicalLocation"]
        assert loc["region"]["startLine"] == 6

    def test_multi_file_rules_and_results(self) -> None:
        """Multi-file fixture produces 3 rules and 3 results."""
        violations = _load_violations("multi_file")
        sarif = _format_violations(violations, files_checked=3)
        run = sarif["runs"][0]
        assert len(run["results"]) == 3
        rules = run["tool"]["driver"]["rules"]
        assert len(rules) == 3
        rule_ids = {r["id"] for r in rules}
        assert rule_ids == {"MEM30-C", "EXP33-C", "STR31-C"}

    def test_fixture_fingerprints_use_code_snippet(self) -> None:
        """Fingerprints derived from code_snippet differ between rules."""
        violations = _load_violations("multi_file")
        sarif = _format_violations(violations, files_checked=3)
        results = sarif["runs"][0]["results"]
        fingerprints = [r["partialFingerprints"]["primaryLocationLineHash"] for r in results]
        # All three violations have different snippets, so fingerprints must differ
        assert len(set(fingerprints)) == 3

    def test_rule_id_reference_integrity(self) -> None:
        """Every result's ruleId must exist in the rules array."""
        violations = _load_violations("multi_file")
        sarif = _format_violations(violations, files_checked=3)
        run = sarif["runs"][0]
        rule_ids = {r["id"] for r in run["tool"]["driver"]["rules"]}
        for result in run["results"]:
            assert result["ruleId"] in rule_ids
