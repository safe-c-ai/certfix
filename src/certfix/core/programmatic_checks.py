"""Conservative programmatic semantic-risk checks for fix auto-apply."""
# ruff: noqa: E501

from __future__ import annotations

import re
from collections.abc import Callable

from certfix.models import ProgrammaticFinding

CheckFn = Callable[[str, str, str], list[ProgrammaticFinding]]


def strip_comments(code: str) -> str:
    """Remove C comments for simple structural checks."""
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)
    return re.sub(r"//.*", "", code)


def string_literals(code: str) -> list[str]:
    return re.findall(r'"(?:\\.|[^"\\])*"', code)


def output_literals(code: str) -> list[str]:
    out: list[str] = []
    for match in re.finditer(
        r"\b(?:printf|fprintf|puts|fputs|perror)\s*\((.*?)\)",
        code,
        re.DOTALL,
    ):
        out.extend(string_literals(match.group(1)))
    return out


def has_output_call(code: str) -> bool:
    return bool(re.search(r"\b(?:printf|fprintf|puts|fputs|perror)\s*\(", code))


def condition_texts(code: str) -> list[str]:
    texts: list[str] = []
    for match in re.finditer(r"\bif\s*\(", code):
        pos = match.end()
        depth = 1
        i = pos
        while i < len(code) and depth:
            if code[i] == "(":
                depth += 1
            elif code[i] == ")":
                depth -= 1
            i += 1
        if depth == 0:
            texts.append(code[pos : i - 1])
    return texts


def assignment_in_condition_vars(code: str) -> set[str]:
    vars_found: set[str] = set()
    for cond in condition_texts(strip_comments(code)):
        for match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?!=)", cond):
            before = cond[max(0, match.start() - 2) : match.start()]
            if before.endswith(("!", "<", ">")):
                continue
            vars_found.add(match.group(1))
    return vars_found


def sizeof_operands(code: str) -> list[str]:
    operands: list[str] = []
    text = strip_comments(code)
    for match in re.finditer(r"\bsizeof\s*\(", text):
        pos = match.end()
        depth = 1
        i = pos
        while i < len(text) and depth:
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
            i += 1
        if depth == 0:
            operands.append(text[pos : i - 1])
    return operands


def sizeof_has_side_effect(code: str) -> bool:
    for operand in sizeof_operands(code):
        if re.search(
            r"\+\+|--|\b[A-Za-z_][A-Za-z0-9_]*\s*=\s*(?!=)|"
            r"\b[A-Za-z_][A-Za-z0-9_]*\s*\(",
            operand,
        ):
            return True
    return False


def atomic_load_args(code: str) -> list[str]:
    args: list[str] = []
    for match in re.finditer(r"\batomic_load(?:_explicit)?\s*\(([^),]+)", strip_comments(code)):
        args.append(re.sub(r"\s+", "", match.group(1)))
    return args


def check_visible_output_literal_change(
    original_code: str,
    fixed_code: str,
    rule_id: str,
) -> list[ProgrammaticFinding]:
    if rule_id not in {"CON35-C", "SIG30-C"}:
        return []
    original = strip_comments(original_code)
    fixed = strip_comments(fixed_code)
    if not (has_output_call(original) and has_output_call(fixed)):
        return []
    orig_lits = output_literals(original)
    fixed_lits = output_literals(fixed)
    if orig_lits and fixed_lits and orig_lits != fixed_lits:
        return [
            ProgrammaticFinding(
                "visible_output_literal_change",
                rule_id,
                "fail",
                "output string literals changed in a rule where output preservation is a known semantic risk",
                {"original_output_literals": orig_lits, "fixed_output_literals": fixed_lits},
            )
        ]
    return []


def check_same_resource_early_return(
    original_code: str,
    fixed_code: str,
    rule_id: str,
) -> list[ProgrammaticFinding]:
    if rule_id not in {"CON35-C", "POS51-C"}:
        return []
    original = strip_comments(original_code)
    fixed = strip_comments(fixed_code)
    resource = r"[A-Za-z_][A-Za-z0-9_]*(?:->\w+|\.\w+)?"
    pattern = (
        rf"\bif\s*\(\s*({resource})\s*==\s*({resource})\s*\)\s*"
        r"(?:\{\s*)?return(?:\s+[^;]+)?\s*;"
    )
    if re.search(pattern, fixed) and not re.search(pattern, original):
        return [
            ProgrammaticFinding(
                "same_resource_early_return_added",
                rule_id,
                "fail",
                "fix added a same-resource early return that was not present in the original",
                {"pattern": "if (x == y) return"},
            )
        ]
    return []


def check_pos51_raw_pointer_order(
    original_code: str,
    fixed_code: str,
    rule_id: str,
) -> list[ProgrammaticFinding]:
    if rule_id != "POS51-C":
        return []
    fixed = strip_comments(fixed_code)
    if "pthread_mutex_lock" not in fixed:
        return []
    if re.search(r"\bif\s*\([^)]*(?:->|\.)?(?:id|index|rank|order)\s*[<>]", fixed):
        return []
    if re.search(
        r"\bif\s*\([^)]*\b[A-Za-z_][A-Za-z0-9_]*\s*[<>]\s*"
        r"[A-Za-z_][A-Za-z0-9_]*\b[^)]*\)",
        fixed,
    ):
        return [
            ProgrammaticFinding(
                "pos51_raw_pointer_order",
                rule_id,
                "fail",
                "fix appears to order lock targets using raw relational comparison instead of a defined key",
                {"matched": "if (... a < b ...) with pthread_mutex_lock"},
            )
        ]
    return []


def check_assignment_side_effect_removed(
    original_code: str,
    fixed_code: str,
    rule_id: str,
) -> list[ProgrammaticFinding]:
    if rule_id != "EXP45-C":
        return []
    original = strip_comments(original_code)
    fixed = strip_comments(fixed_code)
    vars_found = assignment_in_condition_vars(original)
    findings: list[ProgrammaticFinding] = []
    for var in sorted(vars_found):
        assignment_anywhere = re.search(rf"\b{re.escape(var)}\s*=\s*(?!=)", fixed)
        comparison_in_condition = any(
            re.search(rf"\b{re.escape(var)}\s*==", cond) for cond in condition_texts(fixed)
        )
        if comparison_in_condition and not assignment_anywhere:
            findings.append(
                ProgrammaticFinding(
                    "exp45_assignment_replaced_by_comparison",
                    rule_id,
                    "fail",
                    "assignment in the original condition appears to be replaced by comparison, removing a state update",
                    {"variable": var},
                )
            )
    return findings


def check_sizeof_side_effect_materialized(
    original_code: str,
    fixed_code: str,
    rule_id: str,
) -> list[ProgrammaticFinding]:
    if rule_id != "EXP44-C":
        return []
    original = strip_comments(original_code)
    fixed = strip_comments(fixed_code)
    if not sizeof_has_side_effect(original):
        return []
    original_operands = sizeof_operands(original)
    findings: list[ProgrammaticFinding] = []
    if re.search(r"\+\+|--", fixed):
        findings.append(
            ProgrammaticFinding(
                "exp44_sizeof_side_effect_materialized",
                rule_id,
                "fail",
                "fix materialized an increment/decrement that sizeof did not evaluate in the original",
                {"original_sizeof_operands": original_operands},
            )
        )
    if re.search(r"\bsizeof\s*\(\s*\*\s*[A-Za-z_][A-Za-z0-9_]*\s*\)", fixed):
        findings.append(
            ProgrammaticFinding(
                "exp44_sizeof_pointer_to_pointee",
                rule_id,
                "fail",
                "fix appears to change sizeof(pointer expression) into sizeof(*pointer)",
                {"original_sizeof_operands": original_operands},
            )
        )
    return findings


def check_exp46_bitwise_update_changed(
    original_code: str,
    fixed_code: str,
    rule_id: str,
) -> list[ProgrammaticFinding]:
    if rule_id != "EXP46-C":
        return []
    original = strip_comments(original_code)
    fixed = strip_comments(fixed_code)
    findings: list[ProgrammaticFinding] = []
    if (
        re.search(r"\b[A-Za-z_][A-Za-z0-9_]*\s*\^=", original)
        and not re.search(r"\^=", fixed)
        and re.search(r"=\s*(?:0|1|true|false)\s*;", fixed, re.IGNORECASE)
    ):
        findings.append(
            ProgrammaticFinding(
                "exp46_toggle_update_replaced",
                rule_id,
                "fail",
                "bitwise toggle update appears to be replaced by a fixed boolean assignment",
                {"original_operator": "^="},
            )
        )
    if re.search(r"~\s*[A-Za-z_][A-Za-z0-9_]*", original) and re.search(
        r"!\s*[A-Za-z_][A-Za-z0-9_]*",
        fixed,
    ):
        findings.append(
            ProgrammaticFinding(
                "exp46_bitwise_complement_to_logical_not",
                rule_id,
                "fail",
                "bitwise complement appears to be replaced by logical negation",
                {"original_operator": "~", "fixed_operator": "!"},
            )
        )
    return findings


def check_env33_exec_argv_shift(
    original_code: str,
    fixed_code: str,
    rule_id: str,
) -> list[ProgrammaticFinding]:
    if rule_id != "ENV33-C":
        return []
    original = strip_comments(original_code)
    fixed = strip_comments(fixed_code)
    if "system" not in original or not re.search(r"\bexec[lvpe]*\s*\(", fixed):
        return []
    if re.search(
        r"\bexecv?p?\s*\(\s*[A-Za-z_][A-Za-z0-9_]*\s*,\s*(?:\([^)]*\)\s*)?argv\s*\)",
        fixed,
    ):
        return [
            ProgrammaticFinding(
                "env33_exec_argv_shift",
                rule_id,
                "fail",
                "exec-style replacement passes original argv directly and likely shifts argv[0]/arguments",
                {"matched": "exec*(prog, argv)"},
            )
        ]
    return []


def check_con40_atomic_freshness_changed(
    original_code: str,
    fixed_code: str,
    rule_id: str,
) -> list[ProgrammaticFinding]:
    if rule_id != "CON40-C":
        return []
    original_args = atomic_load_args(original_code)
    fixed_args = atomic_load_args(fixed_code)
    findings: list[ProgrammaticFinding] = []
    for arg in sorted(set(original_args)):
        if original_args.count(arg) >= 2 and fixed_args.count(arg) < original_args.count(arg):
            findings.append(
                ProgrammaticFinding(
                    "con40_atomic_freshness_collapsed",
                    rule_id,
                    "fail",
                    "fix reduced repeated atomic loads, which can remove an intended freshness check",
                    {
                        "atomic_arg": arg,
                        "original_count": original_args.count(arg),
                        "fixed_count": fixed_args.count(arg),
                    },
                )
            )
    return findings


def check_mem36_copy_size_mismatch(
    original_code: str,
    fixed_code: str,
    rule_id: str,
) -> list[ProgrammaticFinding]:
    if rule_id != "MEM36-C":
        return []
    fixed = strip_comments(fixed_code)
    if "memcpy" not in fixed or not re.search(r"\b(?:aligned_alloc|posix_memalign)\s*\(", fixed):
        return []
    memcpy_args = re.findall(r"\bmemcpy\s*\((.*?)\)\s*;", fixed, flags=re.DOTALL)
    findings: list[ProgrammaticFinding] = []
    for args in memcpy_args:
        if "min" in args or re.search(r"new_\w+|newSize|new_size", args):
            continue
        if re.search(r"\bold_\w+|oldSize|old_size|capacity|count|size", args):
            findings.append(
                ProgrammaticFinding(
                    "mem36_unclamped_memcpy_after_aligned_alloc",
                    rule_id,
                    "fail",
                    "aligned reallocation fix copies an old size/count without an obvious min/new-size clamp",
                    {"memcpy_args": re.sub(r"\s+", " ", args).strip()},
                )
            )
    return findings


CHECKS: dict[str, CheckFn] = {
    "visible_output_literal_change": check_visible_output_literal_change,
    "same_resource_early_return_added": check_same_resource_early_return,
    "pos51_raw_pointer_order": check_pos51_raw_pointer_order,
    "exp45_assignment_replaced_by_comparison": check_assignment_side_effect_removed,
    "exp44_sizeof_side_effect_materialized": check_sizeof_side_effect_materialized,
    "exp46_bitwise_update_changed": check_exp46_bitwise_update_changed,
    "env33_exec_argv_shift": check_env33_exec_argv_shift,
    "con40_atomic_freshness_collapsed": check_con40_atomic_freshness_changed,
    "mem36_unclamped_memcpy_after_aligned_alloc": check_mem36_copy_size_mismatch,
}

CHECK_PRESETS: dict[str, list[str]] = {
    "release_v1": [
        "visible_output_literal_change",
        "pos51_raw_pointer_order",
        "exp45_assignment_replaced_by_comparison",
        "exp44_sizeof_side_effect_materialized",
        "exp46_bitwise_update_changed",
        "env33_exec_argv_shift",
        "con40_atomic_freshness_collapsed",
        "mem36_unclamped_memcpy_after_aligned_alloc",
    ],
    "candidate_no_signal_v1": ["same_resource_early_return_added"],
}


def run_programmatic_checks(
    *,
    original_code: str,
    fixed_code: str,
    rule_id: str,
    preset: str = "release_v1",
) -> list[ProgrammaticFinding]:
    """Run a conservative programmatic check preset."""
    check_ids = CHECK_PRESETS[preset]
    findings: list[ProgrammaticFinding] = []
    for check_id in check_ids:
        findings.extend(CHECKS[check_id](original_code, fixed_code, rule_id))
    return findings
