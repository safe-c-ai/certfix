# Validation and Retry

certfix generates fixed-code candidates for review. It does not edit source
files in place, and a successful `certfix fix` result is not a proof of program
correctness.

This document explains how `certfix fix` validates a candidate, why a candidate
may be rejected, how validate-guided retry works, and how to read the validation
fields in `reports/fixes.json`.

For the broader pipeline overview, see [ARCHITECTURE.md](ARCHITECTURE.md). For
scope caveats, see [LIMITATIONS.md](LIMITATIONS.md).

## Validation Goals

Validation is a risk-reduction layer around LLM-generated code. The gates are
designed to reject common unsafe or incomplete candidates before they are
reported as successful.

The validation path is intentionally conservative:

- a passing candidate is still a review artifact;
- a failing candidate remains useful evidence for human review;
- an uncertain semantic result blocks success instead of being treated as pass;
- programmatic checks only block risky candidates and never upgrade a candidate
  from failed to passed.

The source file is not modified. Review `fixes/`, `patches/`, and
`reports/fixes.json` before using any generated change.

## Validation Gates

The release fix path validates a candidate through these gates. Some gates run
only after earlier checks succeed. This table is a user-facing map from gates to
failure categories, not a promise that every check runs for every failed
candidate.

| Gate | What it checks | Typical failure category |
| --- | --- | --- |
| Format | The model returned non-empty C code rather than prose, placeholders, or malformed output | `format_error` |
| Compile | The candidate parses with the configured C compiler command, and the local compile context is usable | `compile_error`, `compile_env_missing`, `unsupported_language` |
| Target violation removal | The selected CERT-C rule no longer appears to remain in the candidate | `violation_remains` |
| Semantic review | The configured reviewer did not identify a material semantic-preservation risk from the available code and rule context | `semantic_changed`, `over_deletion`, `manual_boundary`, `regression_introduced` |
| Programmatic regression checks | Known deterministic structural regression-risk patterns are absent | `programmatic_check_failed`, `regression_introduced` |

A candidate is reported as successful only when every enabled gate passes.
These gates reduce risk, but they do not prove semantic preservation, security
correctness, or build success in the user's target environment.

## Status Values

`reports/fixes.json` includes a top-level `status` field for each fix item. It
is the user-facing summary of the validation result.

| Status | Meaning |
| --- | --- |
| `fixed` | All enabled gates passed for the selected candidate |
| `compile_failed` | The fixed-code candidate did not compile under the configured compile check |
| `compile_env_missing` | The compile check could not run meaningfully because local headers or compile context were missing |
| `unsupported_language` | The input is outside the supported C path |
| `violation_remaining` | The target rule still appears to remain, or the target-removal check could not confirm removal |
| `semantic_risk` | Semantic review, programmatic checks, manual-boundary handling, or format validation blocked the candidate |
| `regression_risk` | Validation found evidence of a newly introduced serious issue |
| `model_error` | The model output was empty, placeholder-like, or not usable as C code |
| `unresolved` | The repair path did not produce an accepted candidate |

The status is intentionally coarse. For diagnosis, inspect
`validation.validator.category`, `validation.validator.details`, and any
gate-specific fields under `validation`.

## Reading `reports/fixes.json`

A fix item has this shape:

```json
{
  "rule_id": "MEM30-C",
  "file": "path/to/file.c",
  "line": 42,
  "success": false,
  "diff": null,
  "error": "compile_error",
  "status": "compile_failed",
  "source": "primary",
  "retry_count": 0,
  "retry": null,
  "validation": {
    "validator": {
      "auto_apply_ok": false,
      "category": "compile_error",
      "retryable": true,
      "details": "compiler stderr or validation detail",
      "format_ok": true,
      "compile_ok": false,
      "violation_removed": false,
      "semantic_ok": false,
      "regression_free": true,
      "programmatic_findings": [],
      "compiler_stderr": "..."
    }
  }
}
```

Important fields:

| Field | Meaning |
| --- | --- |
| `success` | Whether the selected candidate passed all enabled gates |
| `diff` | Unified diff for a successful candidate; `null` when no accepted candidate exists |
| `status` | Coarse final result, such as `fixed` or `semantic_risk` |
| `source` | Where the selected candidate came from, usually `primary` or `retry` |
| `retry_count` | Number of retry attempts used by the selected candidate |
| `retry` | Retry decision metadata, if retry was considered or selected |
| `validation.validator.category` | The precise validation category used for retry and reporting |
| `validation.validator.details` | Short diagnostic text for the selected category |
| `validation.compile` | Compiler command, return code, stdout, and stderr |
| `validation.violation_removal` | Target-rule and post-fix detection details |
| `validation.semantic` | Semantic review result, when present |

`auto_apply_ok` is an internal validation-field name. In certfix's public CLI
flow, it means "accepted as a successful fixed-code candidate"; it does not mean
the original source file was edited, and it should not be read as permission to
apply the change automatically.

## Retry Behavior

Validate-guided retry is enabled by bundled fix profiles that set
`fix.validate_guided_retry: true` and `fix.retry_max_attempts` greater than zero.
It is a second pass after the primary candidate fails validation. The bundled
Qwen3.6 release profile uses one retry attempt.

Retry is used only when:

1. the primary candidate failed validation;
2. the failure category is retryable;
3. `fix.validate_guided_retry` is enabled;
4. `fix.retry_max_attempts` is greater than zero.

The retry prompt includes:

- the original comment-stripped code;
- the previous fixed-code candidate;
- the target rule ID and title;
- the validation category and detail;
- compiler stderr when available;
- programmatic findings when available;
- semantic-review summary when available.

When any retry step is routed to an API provider, source code and validation
context may leave the local machine. Retry generation sends the comment-stripped
original code, the previous candidate, and validation diagnostics; retry
validation and post-fix detection can send the retry candidate and related
review context. Confirm your project data policy before using API-only or
hybrid profiles.

Retry output is validated again with the same release gates. If retry passes, it
becomes the selected candidate and `source` is `retry`. If retry fails, certfix
keeps the primary failure information and reports the item as not fixed.

## Retryable Categories

The release path treats these categories as retryable:

| Category | Why retry may help |
| --- | --- |
| `format_error` | The model may produce complete C code when asked again with stricter output instructions |
| `compile_error` | Compiler diagnostics can guide a smaller repair |
| `violation_remains` | The model can focus on the remaining target-rule operation |
| `programmatic_check_failed` | The model can remove the exact structural risk found by the checker |
| `semantic_changed` | The model can restore valid-input behavior while keeping the target fix |
| `regression_introduced` | The model can preserve the target fix while removing the newly introduced issue |
| `over_deletion` | The model can restore deleted behavior and attempt a narrower fix |

These categories are not automatically retried:

| Category | Why it is not automatically retried |
| --- | --- |
| `unsupported_language` | The input is outside the supported C workflow |
| `compile_env_missing` | The local compile context needs user configuration, such as include paths |
| `manual_boundary` | A policy, API, ownership, or behavior decision is not inferable from the snippet |

## Retry Metadata

When retry is considered, the `retry` object records the decision path.

Common fields:

| Field | Meaning |
| --- | --- |
| `selected_source` | `primary_pass`, `retry_pass`, or `primary_rejected` |
| `failure_category` | Primary validation category used to decide retry |
| `failure_detail` | Diagnostic detail passed to retry |
| `retryable` | Whether the primary failure was retryable |
| `retry_status` | Final status of the retry candidate, if generated |
| `retry_success` | Whether retry passed validation |
| `rule_addendum_id` | Rule-specific retry guidance ID, when used |
| `primary_status` | Primary candidate status when retry was selected |

Example:

```json
{
  "selected_source": "retry_pass",
  "failure_category": "compile_error",
  "failure_detail": "expected ';' before return",
  "retryable": true,
  "retry_status": "fixed",
  "retry_success": true,
  "rule_addendum_id": "qwen36_retry_rule_addenda_v1",
  "primary_status": "compile_failed"
}
```

## Programmatic Checks

Programmatic checks are deterministic structural checks for known semantic-risk
patterns. They are intentionally narrow. A finding blocks success, but a lack of
findings does not prove that the candidate is correct.

Examples of risk patterns include:

- visible output literal changes for rules where output preservation is a known
  risk;
- replacing an assignment-in-condition with a comparison and losing a state
  update;
- materializing a side effect that was inside `sizeof`;
- changing repeated atomic loads into a single cached value;
- copying an old allocation size after aligned allocation without an obvious
  clamp;
- shifting command argument shape while replacing shell-based execution.

Programmatic findings appear under:

```text
validation.validator.programmatic_findings
```

Each finding includes:

| Field | Meaning |
| --- | --- |
| `check_id` | Stable checker identifier |
| `rule_id` | Target rule associated with the check |
| `verdict` | Usually `fail` |
| `reason` | Short reason for blocking the candidate |
| `evidence` | Small structured evidence payload |

## Compile Environment Issues

`compile_env_missing` is different from `compile_error`.

- `compile_error` means the configured compile check ran and the candidate did
  not compile.
- `compile_env_missing` means certfix could not fairly judge the candidate with
  the current local compile context, often because project headers or include
  paths were missing.

If you see `compile_env_missing`, update `.certfix.yaml` rather than treating
the candidate as necessarily wrong:

```yaml
validation:
  compile:
    include_paths:
      - "include/"
```

For configuration details, see [CONFIGURATION.md](CONFIGURATION.md).

## Manual Boundary

`manual_boundary` means certfix found a decision boundary that should not be
resolved automatically. This is different from an ordinary model mistake.

Common causes:

- the code snippet does not define whether a boundary input is valid;
- the correct ownership or lifetime policy is project-specific;
- several plausible repairs preserve different public contracts;
- a local API contract is not visible in the analyzed file.

When this happens, inspect the generated candidate and report, then decide the
policy outside certfix.

## Practical Review Flow

When a fix fails validation:

1. Open `reports/fixes.json`.
2. Find the item for the file and rule.
3. Check `status`.
4. Check `validation.validator.category` and `details`.
5. If `compile_failed` or `compile_env_missing`, inspect `validation.compile`.
6. If `violation_remaining`, inspect `validation.violation_removal`.
7. If `semantic_risk` or `regression_risk`, inspect
   `validation.validator.semantic_check_result` and
   `validation.validator.programmatic_findings`.
8. If `retry` is present, check whether `selected_source` is `retry_pass` or
   `primary_rejected`.
9. Review any generated fixed-code candidate and patch manually.

Use certfix output as a focused review aid, not as an automatic source rewrite.
