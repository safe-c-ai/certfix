"""Output formatters for certfix."""

import hashlib
import json
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TextIO

from certfix import __version__
from certfix.models import CheckResult, FixResult, Severity, Violation


class OutputFormatter(ABC):
    """Base class for output formatters."""

    def __init__(self, stream: TextIO = sys.stdout) -> None:
        self.stream = stream

    @abstractmethod
    def format_violations(self, result: CheckResult) -> None:
        """Format and output check results."""
        pass

    @abstractmethod
    def format_fixes(self, fixes: list[FixResult]) -> None:
        """Format and output fix results."""
        pass


class TextFormatter(OutputFormatter):
    """Plain text output formatter."""

    def format_violations(self, result: CheckResult) -> None:
        """Format violations as text."""
        for v in result.violations:
            self.stream.write(f"{v.file_path}:{v.line}:{v.column}: [{v.rule_id}] {v.message}\n")
            if v.candidates:
                candidates = ", ".join(f"{c.rank}:{c.rule_id}" for c in v.candidates)
                self.stream.write(f"  candidates: {candidates}\n")
            if v.rule_selection:
                selection = v.rule_selection
                self.stream.write(f"  selector: {selection.decision.value}")
                if selection.selected_rule_id:
                    self.stream.write(f" {selection.selected_rule_id}")
                if selection.selected_rank is not None:
                    self.stream.write(f" rank={selection.selected_rank}")
                if selection.evidence:
                    self.stream.write(f" - {selection.evidence}")
                self.stream.write("\n")

        self.stream.write(
            f"\nFound {result.total_violations} violations in {result.files_checked} files.\n"
        )

    def format_fixes(self, fixes: list[FixResult]) -> None:
        """Format fixes as unified diff."""
        for fix in fixes:
            if fix.success:
                self._write_fix_header(fix)
                self.stream.write(fix.to_diff())
                self.stream.write("\n")
                self._write_validation_summary(fix)
            else:
                self.stream.write(
                    f"# Failed to fix {fix.violation.rule_id} "
                    f"at {fix.violation.file_path}:{fix.violation.line}\n"
                )
                if fix.final_status:
                    self.stream.write(f"# Status: {fix.final_status.value}\n")
                if fix.error_message:
                    self.stream.write(f"# Error: {fix.error_message}\n")
                self._write_validation_summary(fix)

    def _write_fix_header(self, fix: FixResult) -> None:
        """Write a compact success header before a fix diff."""
        if fix.final_status:
            self.stream.write(
                f"# Fixed {fix.violation.rule_id} at "
                f"{fix.violation.file_path}:{fix.violation.line} "
                f"({fix.final_status.value})\n"
            )

    def _write_validation_summary(self, fix: FixResult) -> None:
        """Write Stage 5/6/7 validation details when available."""
        if (
            fix.compile_result is None
            and fix.violation_removal_result is None
            and fix.semantic_result is None
        ):
            return

        self.stream.write("# Validation:\n")
        if fix.compile_result:
            status = "pass" if fix.compile_result.ok else "fail"
            detail = " ".join(fix.compile_result.command)
            if fix.compile_result.timed_out:
                detail = f"{detail} timed out"
            elif fix.compile_result.returncode is not None:
                detail = f"{detail} exited {fix.compile_result.returncode}"
            self.stream.write(f"#   compile: {status} ({detail})\n")
        if fix.violation_removal_result:
            status = "pass" if fix.violation_removal_result.removed else "fail"
            remaining = len(fix.violation_removal_result.remaining_violations)
            method = fix.violation_removal_result.method
            self.stream.write(
                "#   violation_removal: "
                f"{status} target={fix.violation_removal_result.target_rule_id} "
                f"remaining={remaining} method={method}\n"
            )
        if fix.semantic_result:
            semantic = fix.semantic_result
            values = [
                f"preserved={_format_optional_bool(semantic.semantic_preserved)}",
                f"target_removed={_format_optional_bool(semantic.target_violation_removed)}",
                f"new_regression={_format_optional_bool(semantic.new_regression)}",
            ]
            suffix = f" - {semantic.reason}" if semantic.reason else ""
            self.stream.write(
                f"#   semantic: {semantic.verdict.value} ({', '.join(values)}){suffix}\n"
            )


class JsonFormatter(OutputFormatter):
    """JSON output formatter."""

    def format_violations(self, result: CheckResult) -> None:
        """Format violations as JSON."""
        output = {
            "tool": "certfix",
            "tool_version": __version__,
            "schema_version": "1",
            "files": self._group_by_file(result.violations),
            "summary": {
                "total_violations": result.total_violations,
                "files_checked": result.files_checked,
            },
        }
        json.dump(output, self.stream, indent=2)
        self.stream.write("\n")

    def format_fixes(self, fixes: list[FixResult]) -> None:
        """Format fixes as JSON."""
        output = {
            "tool": "certfix",
            "tool_version": __version__,
            "fixes": [
                {
                    "rule_id": f.violation.rule_id,
                    "file": f.violation.file_path,
                    "line": f.violation.line,
                    "success": f.success,
                    "diff": f.to_diff() if f.success else None,
                    "error": f.error_message,
                    "status": f.final_status.value if f.final_status else None,
                    "source": f.source,
                    "retry_count": f.retry_count,
                    "retry": f.retry_metadata or None,
                    "validation": _fix_validation_to_dict(f),
                    "timings": f.timings or None,
                }
                for f in fixes
            ],
        }
        json.dump(output, self.stream, indent=2)
        self.stream.write("\n")

    def _group_by_file(self, violations: list[Violation]) -> list[dict[str, object]]:
        """Group violations by file."""
        files: dict[str, list[dict[str, str | int]]] = {}
        for v in violations:
            if v.file_path not in files:
                files[v.file_path] = []
            files[v.file_path].append(v.to_dict())

        return [{"path": path, "violations": vs} for path, vs in files.items()]


class SarifFormatter(OutputFormatter):
    """SARIF 2.1.0 output formatter for GitHub Code Scanning integration."""

    _SCHEMA = (
        "https://raw.githubusercontent.com/oasis-tcs/sarif-spec"
        "/main/sarif-2.1/schema/sarif-schema-2.1.0.json"
    )
    _HELP_URI_BASE = "https://wiki.sei.cmu.edu/confluence/display/c/"
    _INFO_URI = "https://github.com/safe-c-ai/certfix"

    def format_violations(self, result: CheckResult) -> None:
        """Format violations as SARIF 2.1.0."""
        rules, rule_index = self._build_rules(result.violations)
        results = [self._violation_to_result(v, rule_index) for v in result.violations]
        sarif = self._build_sarif(results, rules)
        json.dump(sarif, self.stream, indent=2)
        self.stream.write("\n")

    def format_fixes(self, fixes: list[FixResult]) -> None:
        """Format fix results as SARIF 2.1.0 with properties bag."""
        violations = [f.violation for f in fixes]
        rules, rule_index = self._build_rules(violations)
        results = []
        for f in fixes:
            r = self._violation_to_result(f.violation, rule_index)
            props: dict[str, object] = dict(r.get("properties", {}))
            props["certfix/fixAvailable"] = f.success
            if not f.success and f.error_message:
                props["certfix/fixError"] = f.error_message
            if f.final_status:
                props["certfix/finalStatus"] = f.final_status.value
            validation = _fix_validation_to_dict(f)
            if validation is not None:
                props["certfix/validation"] = validation
                _add_validation_summary_properties(props, f)
            r["properties"] = props
            results.append(r)
        sarif = self._build_sarif(results, rules)
        json.dump(sarif, self.stream, indent=2)
        self.stream.write("\n")

    def _build_sarif(
        self, results: list[dict[str, object]], rules: list[dict[str, object]]
    ) -> dict[str, object]:
        """Build the top-level SARIF envelope."""
        return {
            "$schema": self._SCHEMA,
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "certfix",
                            "version": __version__,
                            "informationUri": self._INFO_URI,
                            "rules": rules,
                        }
                    },
                    "results": results,
                }
            ],
        }

    def _build_rules(
        self, violations: list[Violation]
    ) -> tuple[list[dict[str, object]], dict[str, int]]:
        """Build deduplicated rules array and rule_id->index mapping.

        Returns (rules_list, rule_index_dict). Rules are sorted by rule_id.
        For defaultConfiguration.level, the most severe level among violations
        with the same rule_id is used (ERROR > WARNING > INFO).
        """
        severity_rank = {Severity.INFO: 0, Severity.WARNING: 1, Severity.ERROR: 2}
        rule_max_severity: dict[str, Severity] = {}
        rule_messages: dict[str, str] = {}

        for v in violations:
            prev = rule_max_severity.get(v.rule_id)
            if prev is None or severity_rank[v.severity] > severity_rank[prev]:
                rule_max_severity[v.rule_id] = v.severity
            if v.rule_id not in rule_messages:
                rule_messages[v.rule_id] = v.message

        sorted_ids = sorted(rule_max_severity.keys())
        rule_index: dict[str, int] = {}
        rules: list[dict[str, object]] = []

        for idx, rule_id in enumerate(sorted_ids):
            rule_index[rule_id] = idx
            short_desc = self._extract_short_description(rule_messages[rule_id], rule_id)
            rules.append(
                {
                    "id": rule_id,
                    "shortDescription": {"text": short_desc},
                    "helpUri": f"{self._HELP_URI_BASE}{rule_id}",
                    "defaultConfiguration": {
                        "level": self._severity_to_level(rule_max_severity[rule_id])
                    },
                }
            )

        return rules, rule_index

    def _violation_to_result(self, v: Violation, rule_index: dict[str, int]) -> dict[str, object]:
        """Convert a single Violation to a SARIF result object."""
        result = {
            "ruleId": v.rule_id,
            "level": self._severity_to_level(v.severity),
            "message": {"text": v.message},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": self._normalize_path(v.file_path)},
                        "region": {
                            "startLine": v.line,
                            "startColumn": v.column,
                        },
                    }
                }
            ],
            "partialFingerprints": {"primaryLocationLineHash": self._fingerprint(v)},
        }
        properties = _violation_properties(v)
        if properties:
            result["properties"] = properties
        return result

    def _fingerprint(self, v: Violation) -> str:
        """Compute a stable fingerprint for a violation.

        Hash: sha256(rule_id + normalized_path + source_line_text).
        Falls back to str(line) when code_snippet is None.
        """
        source = v.code_snippet if v.code_snippet is not None else str(v.line)
        normalized = self._normalize_path(v.file_path)
        data = f"{v.rule_id}:{normalized}:{source}"
        return hashlib.sha256(data.encode()).hexdigest()

    @staticmethod
    def _severity_to_level(severity: Severity) -> str:
        """Map Severity enum to SARIF level string."""
        mapping = {
            Severity.ERROR: "error",
            Severity.WARNING: "warning",
            Severity.INFO: "note",
        }
        return mapping[severity]

    @staticmethod
    def _extract_short_description(message: str, rule_id: str) -> str:
        """Extract short description by removing 'CERT-C {rule_id}: ' prefix."""
        prefix = f"CERT-C {rule_id}: "
        if message.startswith(prefix):
            return message[len(prefix) :]
        return message

    @staticmethod
    def _normalize_path(file_path: str) -> str:
        """Normalize file path to relative URI with forward slashes.

        Searches parent directories for .git to find repo root.
        Falls back to CWD-relative path.
        """
        p = Path(file_path)
        # Convert to absolute for reliable relativization
        if not p.is_absolute():
            p = Path.cwd() / p
        p = p.resolve()

        # Find repo root by searching for .git
        root = None
        candidate = p.parent
        for _ in range(len(candidate.parts)):
            if (candidate / ".git").exists():
                root = candidate
                break
            parent = candidate.parent
            if parent == candidate:
                break
            candidate = parent

        if root is None:
            root = Path.cwd().resolve()

        try:
            rel = p.relative_to(root)
        except ValueError:
            # Path not under root; use filename only
            rel = Path(p.name)

        return rel.as_posix()


def get_formatter(format_type: str, stream: TextIO = sys.stdout) -> OutputFormatter:
    """Get formatter by type."""
    formatters: dict[str, type[OutputFormatter]] = {
        "text": TextFormatter,
        "json": JsonFormatter,
        "sarif": SarifFormatter,
    }
    formatter_class = formatters.get(format_type, TextFormatter)
    return formatter_class(stream)


def _fix_validation_to_dict(fix: FixResult) -> dict[str, object] | None:
    """Convert optional v2 validation results to JSON-safe data."""
    if (
        fix.compile_result is None
        and fix.violation_removal_result is None
        and fix.semantic_result is None
        and fix.validator_result is None
    ):
        return None

    data: dict[str, object] = {}
    if fix.validator_result:
        data["validator"] = fix.validator_result.to_dict()
    if fix.compile_result:
        data["compile"] = {
            "ok": fix.compile_result.ok,
            "command": fix.compile_result.command,
            "returncode": fix.compile_result.returncode,
            "timed_out": fix.compile_result.timed_out,
            "stdout": fix.compile_result.stdout,
            "stderr": fix.compile_result.stderr,
        }
    if fix.violation_removal_result:
        data["violation_removal"] = {
            "removed": fix.violation_removal_result.removed,
            "target_rule_id": fix.violation_removal_result.target_rule_id,
            "method": fix.violation_removal_result.method,
            "confidence": fix.violation_removal_result.confidence,
            "reason": fix.violation_removal_result.reason,
            "remaining_evidence": fix.violation_removal_result.remaining_evidence,
            "parse_ok": fix.violation_removal_result.parse_ok,
            "post_fix_detected_rules": (fix.violation_removal_result.post_fix_detected_rules),
            "post_fix_detected_any": fix.violation_removal_result.post_fix_detected_any,
            "target_rule_detected": fix.violation_removal_result.target_rule_detected,
            "override_applied": fix.violation_removal_result.override_applied,
            "original_target_present": (fix.violation_removal_result.original_target_present),
            "original_target_confidence": (fix.violation_removal_result.original_target_confidence),
            "original_target_reason": (fix.violation_removal_result.original_target_reason),
            "original_target_evidence": (fix.violation_removal_result.original_target_evidence),
            "original_target_parse_ok": (fix.violation_removal_result.original_target_parse_ok),
            "non_target_audits": fix.violation_removal_result.non_target_audits,
            "non_target_introduced": (fix.violation_removal_result.non_target_introduced),
            "non_target_audit_blocking": (fix.violation_removal_result.non_target_audit_blocking),
            "remaining_violations": [
                violation.to_dict()
                for violation in fix.violation_removal_result.remaining_violations
            ],
        }
    if fix.semantic_result:
        data["semantic"] = {
            "verdict": fix.semantic_result.verdict.value,
            "semantic_preserved": fix.semantic_result.semantic_preserved,
            "target_violation_removed": fix.semantic_result.target_violation_removed,
            "new_regression": fix.semantic_result.new_regression,
            "reason": fix.semantic_result.reason,
        }
    return data


def _violation_properties(violation: Violation) -> dict[str, object]:
    """Build SARIF properties for rule-candidate metadata."""
    properties: dict[str, object] = {}
    if violation.candidates:
        properties["certfix/ruleCandidates"] = [
            {
                "ruleId": candidate.rule_id,
                "rank": candidate.rank,
                "description": candidate.description,
            }
            for candidate in violation.candidates
        ]
    if violation.rule_selection:
        selection = violation.rule_selection
        properties["certfix/ruleSelection"] = {
            "decision": selection.decision.value,
            "selectedRuleId": selection.selected_rule_id,
            "selectedRank": selection.selected_rank,
            "evidence": selection.evidence,
        }
    return properties


def _add_validation_summary_properties(
    properties: dict[str, object],
    fix: FixResult,
) -> None:
    """Add query-friendly validation fields to a SARIF properties bag."""
    if fix.compile_result:
        properties["certfix/compileOk"] = fix.compile_result.ok
    if fix.violation_removal_result:
        properties["certfix/violationRemoved"] = fix.violation_removal_result.removed
        properties["certfix/remainingViolationCount"] = len(
            fix.violation_removal_result.remaining_violations
        )
    if fix.semantic_result:
        properties["certfix/semanticVerdict"] = fix.semantic_result.verdict.value
        properties["certfix/semanticPreserved"] = fix.semantic_result.semantic_preserved
        properties["certfix/targetViolationRemoved"] = fix.semantic_result.target_violation_removed
        properties["certfix/newRegression"] = fix.semantic_result.new_regression


def _format_optional_bool(value: bool | None) -> str:
    """Format optional boolean gate values for text output."""
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "uncertain"
