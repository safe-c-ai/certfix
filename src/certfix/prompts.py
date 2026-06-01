"""Prompt templates for LLM inference."""

from __future__ import annotations

from typing import Any

from certfix.prompt_profiles import (
    ExampleOrder,
    ExampleRatio,
    InstructionEmphasis,
    PromptProfile,
    RepairOutputMode,
    RepairPromptProfile,
    get_repair_rule_specific_guidance,
    resolve_repair_profile,
)

DETECTION_PROMPT = """You are a security expert analyzing C code for CERT-C violations.

Analyze the following C code and identify any CERT-C security violations.

For each violation found, output in this exact format:
VIOLATION: <rule_id> at line <line_number>: <description>

If no violations are found, output:
NO_VIOLATIONS

Code:
```c
{code}
```

Analysis:"""

FIX_PROMPT = """You are a security expert fixing CERT-C violations in C code.

The following C code has a {rule_id} violation at line {line}:
{description}

Original code:
```c
{code}
```

Provide the fixed code that resolves this violation while preserving the original functionality.
Output only the fixed code block, no explanations.

Fixed code:
```c
"""

FIX_WITH_CANDIDATES_PROMPT = (
    "You are a security expert analyzing and fixing CERT-C violations in C code.\n"
    """

A detection model flagged the following code as potentially violating one of these CERT-C rules:
{candidates}

IMPORTANT: The detection model has a high false positive rate. Many flagged codes are actually safe.
Your first task is to determine whether a real violation exists.

Step 1: Examine the code for concrete evidence of a violation.
- Identify the specific line(s) and operation(s) that would cause the violation.
- If you cannot find concrete evidence for ANY of the candidate rules, the code is safe.

Step 2: Output your decision in this EXACT format:

If NO violation exists:
DECISION: NO_VIOLATIONS

If a violation exists:
DECISION: APPLY_RULE
RULE: <rule_id>
EVIDENCE: <one-line description of the specific violation>
```c
<fixed code>
```

Code to analyze:
```c
{code}
```

Decision:"""
)

SELECTED_RULE_FIX_PROMPT = """You are fixing a confirmed CERT-C violation in C code.

Target rule:
{rule_id}

Rule selection evidence:
{evidence}

Stage 2 candidate list:
{candidates}

Original code:
```c
{code}
```

Generate a corrected version of the code that removes the target violation while preserving
the original behavior, side effects, API contracts, ownership, resource lifetime, and return
values. Do not delete behavior to make the violation disappear.

Output only the complete fixed C code in a single code fence:
```c
"""

RULE_SELECTION_PROMPT = """You are selecting the most likely CERT-C rule for a flagged C code chunk.

The detection pipeline produced these candidate rules:
{candidates}

Select exactly one candidate only if the code contains concrete evidence for it.
If none of the candidates are supported by the code, reject the finding.

Output exactly one of these forms:

DECISION: APPLY_RULE
RULE: <rule_id from candidates>
EVIDENCE: <one-line concrete evidence>

DECISION: NO_VIOLATIONS

DECISION: UNRESOLVED
EVIDENCE: <why the candidates are insufficient>

Code:
```c
{code}
```

Decision:"""

SEMANTIC_CHECK_PROMPT = """/no_think
You are reviewing whether a generated C fix preserved behavior.
Return the final five-line verdict only. Do not include analysis, reasoning,
notes, quoted output, or markdown.

Target CERT-C rule:
{rule_id}

Original code:
```c
{original_code}
```

Fixed code:
```c
{fixed_code}
```

Review observable behavior, side effects, API contracts, ownership, resource lifetime,
return values, and newly introduced correctness or security risks.

Respond with exactly five lines. Replace each value with one literal token from
the allowed values. Do not copy option lists or placeholder text.

Allowed values:
- VERDICT: PASS, FAIL, or UNCERTAIN
- SEMANTIC_PRESERVED: YES, NO, or UNCERTAIN
- TARGET_VIOLATION_REMOVED: YES, NO, or UNCERTAIN
- NEW_REGRESSION: YES, NO, or UNCERTAIN
- REASON: one short sentence without angle brackets

The five output keys must be exactly:
VERDICT:
SEMANTIC_PRESERVED:
TARGET_VIOLATION_REMOVED:
NEW_REGRESSION:
REASON:

Place the selected value after each colon.

Decision:"""

SEMANTIC_CHECK_GRAMMAR = (
    'root ::= "VERDICT: " verdict "\\n" '
    '"SEMANTIC_PRESERVED: " tri "\\n" '
    '"TARGET_VIOLATION_REMOVED: " tri "\\n" '
    '"NEW_REGRESSION: " tri "\\n" '
    '"REASON: " reason\n'
    'verdict ::= "PASS" | "FAIL" | "UNCERTAIN"\n'
    'tri ::= "YES" | "NO" | "UNCERTAIN"\n'
    'reason ::= reason-char reason-char* "\\n"?\n'
    "reason-char ::= [^\\n]\n"
)

SEMANTIC_AUTO_APPLY_PROMPT = """/no_think
You are a conservative release gate for a generated C fix.
Return only one JSON object. Do not include markdown, prose, or analysis.

Target CERT-C rule:
{rule_id}

Original code:
```c
{original_code}
```

Fixed code:
```c
{fixed_code}
```

Review whether the fixed code preserves valid-input behavior, observable output,
state updates, return behavior, cleanup paths, resource ownership, and public API
contracts except for the narrow change required by the CERT-C rule. Also check
whether the target rule violation was removed and whether a new correctness,
resource, pointer, arithmetic, concurrency, signal, environment, or security
regression was introduced.

Use this exact JSON shape:
{{
  "parse_ok": true,
  "auto_apply_ok": true,
  "behavior_preserved": true,
  "material_behavior_delta": false,
  "uncertain_material_behavior": false,
  "fail_type": "none",
  "confidence": "high",
  "reason": "short reason"
}}

Rules:
- Set "auto_apply_ok" to false if behavior preservation is uncertain.
- Set "confidence" to "low" if the code pair cannot be judged from the snippet.
- Use "fail_type": "none" only when auto-apply is safe.
- Otherwise use a concise fail_type such as "output_change", "state_change",
  "cleanup_change", "resource_lifetime", "target_violation_remaining",
  "new_regression", "over_deletion", or "manual_boundary".
"""

VIOLATION_REMOVAL_AUDIT_PROMPT = """/no_think
You are a conservative CERT-C target violation removal gate.
Return only one JSON object. Do not include markdown, prose, or analysis.

Decide only whether the FIXED code still contains the TARGET CERT-C rule
violation. Do not judge unrelated CERT-C violations. Do not require a perfect
fix. A conservative stale pattern match is not enough; there must be semantic
target-rule evidence in the fixed code.

Target CERT-C rule:
{rule_id}

Target rule title:
{rule_title}

Target rule cue:
{rule_cue}

Fixed code:
```c
{fixed_code}
```

Use this exact JSON shape:
{{
  "parse_ok": true,
  "target_violation_removed": true,
  "confidence": "high",
  "reason": "one short sentence, no alternative conclusions",
  "remaining_evidence": ""
}}

Rules:
- If any target-rule violation remains semantically, set
  "target_violation_removed" to false.
- If the answer is uncertain, set "target_violation_removed" to false and
  "confidence" to "low".
- If "remaining_evidence" is non-empty, "target_violation_removed" must be false.
- Do not describe a rejected conclusion in "reason".
"""

ORIGINAL_TARGET_RULE_AUDIT_PROMPT = """/no_think
You are a conservative CERT-C target violation presence gate.
Return only one JSON object. Do not include markdown, prose, or analysis.

Decide only whether the ORIGINAL code contains the TARGET CERT-C rule violation.
Do not judge unrelated CERT-C violations.

Target CERT-C rule:
{rule_id}

Target rule title:
{rule_title}

Target rule cue:
{rule_cue}

Original code:
```c
{original_code}
```

Use this exact JSON shape:
{{
  "parse_ok": true,
  "target_rule_present": true,
  "confidence": "high",
  "reason": "one short sentence",
  "evidence": "specific target-rule construct, or empty string"
}}

Rules:
- If the target rule is not clearly present, set "target_rule_present" to false.
- If the answer is uncertain, set "target_rule_present" to false and
  "confidence" to "low".
- Low confidence blocks target-rule override.
"""

NON_TARGET_INTRODUCED_AUDIT_PROMPT = """/no_think
You are auditing a C repair candidate for a possible non-target CERT-C violation.
Return only one JSON object. Do not include markdown, prose, or analysis.

Task:
For the NON-TARGET rule below, decide whether the original code and fixed code
contain that rule violation.

Non-target rule:
{rule_id}

Non-target rule title:
{rule_title}

Selected repair target rule:
{target_rule_id}

Original code:
```c
{original_code}
```

Fixed code:
```c
{fixed_code}
```

Use this exact JSON shape:
{{
  "parse_ok": true,
  "original_violation_present": true,
  "fixed_violation_present": false,
  "classification": "detector_false_positive",
  "confidence": 0.95,
  "evidence": "short concrete evidence"
}}

Classification rules:
- "introduced_by_fix": original=false and fixed=true.
- "preexisting_or_unrelated": original=true and fixed=true.
- "detector_false_positive": fixed=false.
- "removed_by_fix": original=true and fixed=false.
- "uncertain": either judgment is uncertain or evidence is insufficient.

Rules:
- Judge only the non-target rule above.
- Do not substitute a different rule.
- Ignore comments.
- Use "uncertain" if the code pair is insufficient to judge.
- Low confidence or parse failure blocks release auto-apply.
"""

QWEN36_STAGE1_BALANCED_PRIOR_PROMPT = """/no_think
You are a C code auditor.

Task:
Classify each item as violation or safe. The input set may contain many examples
of both classes, so do not prefer safe by default.

Output violation when the shown code has a concrete defect in data flow, control
flow, object lifetime, bounds, initialization, declarations, arithmetic,
floating point, strings, input/output, preprocessing, concurrency, signals, or
environment use.

Output safe when the code is correct or the suspected issue is already guarded.

Output only valid JSON with this exact shape:
{"predictions":[{"id":"S001","label":"violation"}]}"""

QWEN36_RULE_TITLE_MATCH_PROMPT = """/no_think
You are a C code auditor.

Task:
Each item is already known to contain a violation. Select the rule ID by matching
the code to the rule title and category, not by broad topical similarity.

Rules:
- Direct code-to-title evidence beats generic risk wording.
- The selected rule should name the exact forbidden operation or missing check.
- If unsure between a broad rule and a precise rule, choose the precise rule
  only when the code proves its exact scope.
- Return one rule ID only.

Output only JSON with this shape:
{"predictions":[{"id":"S001","rule_id":"ARR30-C"}]}"""

QWEN36_RULE_TITLE_MATCH_EXCLUDE_PROMPT = """/no_think
You are a C code auditor.

Task:
The item is already known to contain a violation. Select exactly one CERT-C rule
ID by matching the code to the rule title and category, not by broad topical
similarity.

Rules:
- Direct code-to-title evidence beats generic risk wording.
- The selected rule should name the exact forbidden operation or missing check.
- Do not select any rule ID listed in excluded_rule_ids.
- Return one rule ID only.

Output only JSON with this shape:
{"rule_id":"ARR30-C"}"""


def build_qwen36_stage1_prompt(code: str) -> str:
    """Build the adopted Qwen3.6 Stage 1 binary detection prompt."""
    return build_qwen36_stage1_batch_prompt([{"id": "S001", "code": code}])


def build_qwen36_stage1_batch_prompt(items: list[dict[str, str]]) -> str:
    """Build the adopted Qwen3.6 Stage 1 prompt for one or more items."""
    import json

    return (
        f"{QWEN36_STAGE1_BALANCED_PRIOR_PROMPT}\n\n"
        "Classify every item below. Return one prediction per input id.\n\n"
        f"{json.dumps({'items': items}, ensure_ascii=False)}"
    )


def build_qwen36_rule_id_prompt(code: str, rule_catalog: str) -> str:
    """Build the adopted Qwen3.6 Rule ID prompt with title+cue catalog."""
    return build_qwen36_rule_id_batch_prompt(
        [{"id": "S001", "code": code}],
        rule_catalog,
    )


def build_qwen36_rule_id_batch_prompt(
    items: list[dict[str, str]],
    rule_catalog: str,
) -> str:
    """Build the adopted Qwen3.6 Rule ID prompt for one or more positive items."""
    rendered_items = "\n".join(
        f"Item {item['id']}:\n```c\n{item['code']}\n```" for item in items
    )
    return f"""{QWEN36_RULE_TITLE_MATCH_PROMPT}

Rule catalog:
{rule_catalog}

Items:
{rendered_items}

Return JSON only. Include one prediction for every item id."""


def build_qwen36_rule_id_exclude_prompt(
    code: str,
    rule_catalog: str,
    excluded_rule_ids: list[str],
    additional_candidate_cues: list[str] | None = None,
) -> str:
    """Build the sequential Qwen3.6 Rule ID prompt with excluded candidates."""
    import json

    payload = {
        "excluded_rule_ids": excluded_rule_ids,
        "code": code,
    }
    cue_block = ""
    if additional_candidate_cues:
        cue_block = (
            "\n\nAdditional easy-to-miss candidate cues:\n"
            + "\n".join(f"- {cue}" for cue in additional_candidate_cues)
        )
    return f"""{QWEN36_RULE_TITLE_MATCH_EXCLUDE_PROMPT}

Rule catalog:
{rule_catalog}
{cue_block}

Item:
{json.dumps(payload, ensure_ascii=False)}

Return JSON only."""


def build_simple_repair_prompt(
    code: str,
    rules: list[str] | None = None,
    profile_name: str | None = None,
) -> str:
    """Build the direct simple repair prompt for a repair profile."""
    profile = resolve_repair_profile(profile_name)
    return build_repair_prompt_from_profile(code, profile, rules)


def build_repair_prompt_from_profile(
    code: str,
    profile: RepairPromptProfile,
    rules: list[str] | None = None,
) -> str:
    """Build a repair prompt from a model/task-specific profile."""
    if profile.output_mode == RepairOutputMode.CODE_ONLY:
        rule_id = rules[0] if rules and len(rules) == 1 else None
        return profile.template.format(
            code=code,
            rule_label=_format_repair_rule_label(rules),
            violation_explanation="The shown code contains the target CERT-C rule violation.",
            rule_specific_guidance=get_repair_rule_specific_guidance(rule_id),
        )

    if rules:
        rule_filter = "Only consider these CERT-C rules: " + ", ".join(rules)
    else:
        rule_filter = "Consider all supported CERT-C rules."
    return profile.template.format(code=code, rule_filter=rule_filter)


def _format_repair_rule_label(rules: list[str] | None) -> str:
    if not rules:
        return "relevant CERT-C rule"
    if len(rules) == 1:
        return f"CERT-C rule {rules[0]}"
    return "CERT-C rule from this candidate set: " + ", ".join(rules)


RULES_CONTEXT = """CERT-C Rules Reference:
- EXP33-C: Do not read uninitialized memory
- EXP34-C: Do not dereference null pointers
- ARR30-C: Do not form or use out-of-bounds pointers or array subscripts
- ARR38-C: Guarantee that library functions do not form invalid pointers
- STR31-C: Guarantee that storage for strings has sufficient space
- STR32-C: Do not pass a non-null-terminated character sequence to a library function
- MEM30-C: Do not access freed memory
- MEM35-C: Allocate sufficient memory for an object
- INT30-C: Ensure that unsigned integer operations do not wrap
- INT32-C: Ensure that operations on signed integers do not result in overflow
"""

# --- Few-shot examples for profile-based prompt construction ---

VIOLATION_EXAMPLES: list[dict[str, str]] = [
    {
        "code": (
            "void f(void) {\n"
            "    char *p = (char *)malloc(10);\n"
            "    free(p);\n"
            '    printf("%s", p);\n'
            "}"
        ),
        "output": ("VIOLATION: MEM30-C at line 4: Accessing pointer 'p' after it has been freed"),
    },
    {
        "code": (
            "void g(void) {\n"
            "    char buf[10];\n"
            '    strcpy(buf, "this string is way too long for buf");\n'
            "}"
        ),
        "output": ("VIOLATION: STR31-C at line 3: String copy exceeds buffer size of 'buf'"),
    },
    {
        "code": ("int h(int *ptr) {\n    return *ptr + 1;\n}"),
        "output": ("VIOLATION: EXP34-C at line 2: Dereferencing 'ptr' without null check"),
    },
    {
        "code": ('void k(void) {\n    int x;\n    printf("%d", x);\n}'),
        "output": ("VIOLATION: EXP33-C at line 3: Reading uninitialized variable 'x'"),
    },
]

SAFE_EXAMPLES: list[dict[str, str]] = [
    {
        "code": (
            "void f(void) {\n"
            "    char *p = (char *)malloc(10);\n"
            "    if (p != NULL) {\n"
            '        snprintf(p, 10, "hello");\n'
            "        free(p);\n"
            "    }\n"
            "}"
        ),
        "output": "NO_VIOLATIONS",
    },
    {
        "code": (
            "int g(const int *ptr) {\n    if (ptr == NULL) return -1;\n    return *ptr + 1;\n}"
        ),
        "output": "NO_VIOLATIONS",
    },
    {
        "code": ('void h(void) {\n    char buf[64];\n    snprintf(buf, sizeof(buf), "safe");\n}'),
        "output": "NO_VIOLATIONS",
    },
    {
        "code": ('void k(void) {\n    int x = 0;\n    printf("%d", x);\n}'),
        "output": "NO_VIOLATIONS",
    },
]


def format_candidates(candidates: list) -> str:
    """Format RuleCandidate list for fix prompt."""
    lines = []
    for c in candidates:
        lines.append(f"{c.rank}. {c.rule_id}: {c.description}")
    return "\n".join(lines)


def build_fix_prompt(code: str, violation: Any, profile_name: str | None = None) -> str:
    """Build a fix-generation prompt for a violation."""
    rule_selection = getattr(violation, "rule_selection", None)
    candidates = getattr(violation, "candidates", None)
    if rule_selection is not None and getattr(rule_selection, "selected_rule_id", None):
        return SELECTED_RULE_FIX_PROMPT.format(
            rule_id=rule_selection.selected_rule_id,
            evidence=rule_selection.evidence or getattr(violation, "message", ""),
            candidates=format_candidates(candidates or []),
            code=code,
        )

    if candidates:
        return FIX_WITH_CANDIDATES_PROMPT.format(
            line=violation.line,
            candidates=format_candidates(candidates),
            code=code,
        )

    return FIX_PROMPT.format(
        rule_id=violation.rule_id,
        line=violation.line,
        description=violation.message,
        code=code,
    )


def build_detection_prompt(
    code: str,
    profile: PromptProfile,
    rules: list[str] | None = None,
) -> str:
    """Build a detection prompt based on profile factors.

    Args:
        code: C source code to analyze.
        profile: Prompt profile with factor settings.
        rules: Reserved for future rule filtering (currently unused).

    Returns:
        Complete prompt string.
    """
    parts: list[str] = []

    # 1. System instruction
    parts.append(_build_instruction(profile))

    # 2. Few-shot examples
    examples_text = _build_examples(profile)
    if examples_text:
        parts.append(examples_text)

    # 3. Output format instruction
    parts.append(
        "For each violation found, output in this exact format:\n"
        "VIOLATION: <rule_id> at line <line_number>: <description>\n\n"
        "If no violations are found, output:\n"
        "NO_VIOLATIONS"
    )

    # 4. Target code
    parts.append(f"Code to analyze:\n```c\n{code}\n```\n\nAnalysis:")

    return "\n\n".join(parts)


def _build_instruction(profile: PromptProfile) -> str:
    """Build instruction text based on emphasis and D1 factors."""
    base = "You are a security expert analyzing C code for CERT-C violations."

    if profile.d1_optimization:
        base += (
            "\n\nIMPORTANT: Focus on the most common and critical violation patterns. "
            "Be precise in your analysis — report only clear violations with high confidence."
        )
        if profile.d1_bias:
            base += (
                " When uncertain, lean toward reporting a potential violation "
                "rather than missing one."
            )

    if profile.instruction_emphasis == InstructionEmphasis.VIOLATION:
        base += (
            "\n\nCarefully examine the code for security violations. "
            "Pay close attention to memory management, pointer handling, "
            "buffer operations, and integer arithmetic."
        )
    else:  # SAFE
        base += (
            "\n\nAnalyze the code carefully. Many code snippets are safe and correct. "
            "Only report violations when you are confident the code is genuinely unsafe. "
            "Avoid false positives."
        )

    return base


def _build_examples(profile: PromptProfile) -> str:
    """Build few-shot examples based on ratio and order factors."""
    if profile.example_ratio == ExampleRatio.VIO_HEAVY:
        n_vio, n_safe = min(4, len(VIOLATION_EXAMPLES)), min(1, len(SAFE_EXAMPLES))
    else:  # SAFE_HEAVY
        n_vio, n_safe = min(1, len(VIOLATION_EXAMPLES)), min(4, len(SAFE_EXAMPLES))

    vio_examples = VIOLATION_EXAMPLES[:n_vio]
    safe_examples = SAFE_EXAMPLES[:n_safe]

    if profile.example_order == ExampleOrder.VIOLATION_FIRST:
        ordered = [("violation", e) for e in vio_examples] + [("safe", e) for e in safe_examples]
    else:  # SAFE_FIRST
        ordered = [("safe", e) for e in safe_examples] + [("violation", e) for e in vio_examples]

    if not ordered:
        return ""

    parts = ["Here are some examples:\n"]
    for i, (_kind, ex) in enumerate(ordered, 1):
        parts.append(f"Example {i}:\n```c\n{ex['code']}\n```\nOutput: {ex['output']}")

    return "\n\n".join(parts)
