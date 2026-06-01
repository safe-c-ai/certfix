"""Prompt profile definitions for model-specific prompt optimization."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from typing import Any

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum

    class StrEnum(str, Enum):  # type: ignore[no-redef]
        """Backport of StrEnum for Python 3.10."""

        pass


from certfix.exceptions import ConfigError

logger = logging.getLogger(__name__)


class ExampleRatio(StrEnum):
    """Ratio of violation to safe examples in few-shot prompts."""

    VIO_HEAVY = "vio_heavy"  # 7:2
    SAFE_HEAVY = "safe_heavy"  # 2:7


class InstructionEmphasis(StrEnum):
    """Emphasis direction in instruction text."""

    VIOLATION = "violation"
    SAFE = "safe"


class ExampleOrder(StrEnum):
    """Order of few-shot examples."""

    VIOLATION_FIRST = "violation_first"
    SAFE_FIRST = "safe_first"


class RepairOutputMode(StrEnum):
    """Expected output format for a repair prompt profile."""

    STRUCTURED = "structured"
    CODE_ONLY = "code_only"


@dataclass(frozen=True)
class PromptProfile:
    """Configuration for model-specific prompt construction."""

    name: str
    example_ratio: ExampleRatio
    instruction_emphasis: InstructionEmphasis
    example_order: ExampleOrder
    d1_optimization: bool = False
    d1_bias: bool = False


@dataclass(frozen=True)
class RepairPromptProfile:
    """Configuration for model/task-specific repair prompt construction."""

    name: str
    output_mode: RepairOutputMode
    template: str
    default_max_tokens: int = 4096
    temperature: float = 0.1


# Built-in profiles derived from factor separation experiments
BUILTIN_PROFILES: dict[str, PromptProfile] = {
    "default": PromptProfile(
        name="default",
        example_ratio=ExampleRatio.VIO_HEAVY,
        instruction_emphasis=InstructionEmphasis.VIOLATION,
        example_order=ExampleOrder.VIOLATION_FIRST,
    ),
    "glm": PromptProfile(
        name="glm",
        example_ratio=ExampleRatio.SAFE_HEAVY,
        instruction_emphasis=InstructionEmphasis.VIOLATION,
        example_order=ExampleOrder.SAFE_FIRST,
    ),
    "deepseek": PromptProfile(
        name="deepseek",
        example_ratio=ExampleRatio.SAFE_HEAVY,
        instruction_emphasis=InstructionEmphasis.VIOLATION,
        example_order=ExampleOrder.VIOLATION_FIRST,
        d1_optimization=True,
        d1_bias=True,
    ),
    "qwen-large": PromptProfile(
        name="qwen-large",
        example_ratio=ExampleRatio.SAFE_HEAVY,
        instruction_emphasis=InstructionEmphasis.VIOLATION,
        example_order=ExampleOrder.VIOLATION_FIRST,
    ),
    "qwen-coder": PromptProfile(
        name="qwen-coder",
        example_ratio=ExampleRatio.VIO_HEAVY,
        instruction_emphasis=InstructionEmphasis.VIOLATION,
        example_order=ExampleOrder.VIOLATION_FIRST,
    ),
    "ministral": PromptProfile(
        name="ministral",
        example_ratio=ExampleRatio.VIO_HEAVY,
        instruction_emphasis=InstructionEmphasis.SAFE,
        example_order=ExampleOrder.VIOLATION_FIRST,
    ),
    "devstral": PromptProfile(
        name="devstral",
        example_ratio=ExampleRatio.VIO_HEAVY,
        instruction_emphasis=InstructionEmphasis.VIOLATION,
        example_order=ExampleOrder.SAFE_FIRST,
    ),
}

QWEN36_CODE_ONLY_FIX_TEMPLATE = """The following C code has a {rule_label} violation.
Output only the corrected C code.

Requirements:
- Output only C code (no explanations, bullet points, or Markdown code blocks)
- Do not add extra text
- Preserve the original structure as much as possible, make minimal changes
- Keep ALL original #include headers
- Add any missing headers required by your fix

## Code
```c
{code}
```"""

QWEN36_FULL_FILE_FIX_TEMPLATE = """The following complete C source file has a
{rule_label} violation.
Output only the complete corrected C source file.

Requirements:
- Output only C code (no explanations, bullet points, or Markdown code blocks)
- Do not add extra text
- Output the full source file, not a snippet, function body, or patch
- Preserve the original structure as much as possible, make minimal changes
- Keep ALL original #include headers
- Preserve unrelated declarations, function signatures, and unrelated functions
- Add any missing headers required by your fix

## Code
```c
{code}
```"""

QWEN36_COMPLETE_REPAIR_V2_TEMPLATE = """/no_think
You are repairing C code for {rule_label}.

Known violation:
The shown code contains the target CERT-C rule violation.

Repair requirements:
- Fix every visible instance of this rule violation, not just the first one.
- Do not return unchanged code unless the shown code is already compliant.
- Preserve all function signatures, externally visible declarations, state updates,
  side effects, cleanup paths, and error paths.
- Do not delete logic, replace bodies with stubs, or hide the violation by bypassing code.
- Do not add long explanatory comments; output clean production C code.
- Avoid introducing new C11 syntax errors, buffer overflows, leaks, races,
  invalid pointer comparisons, dangling pointers, or unchecked arithmetic.
- Prefer a local, standard remediation for the target rule.

C code:
```c
{code}
```

Return only the complete corrected C code. No markdown."""

QWEN36_COMPLETE_REPAIR_RULE_GUIDED_V1_TEMPLATE = """/no_think
You are repairing C code for {rule_label}.

Known violation:
{violation_explanation}

{rule_specific_guidance}

Repair requirements:
- Fix every visible instance of this rule violation, not just the first one.
- Do not return unchanged code unless the shown code is already compliant.
- Preserve externally visible behavior for valid inputs; when a narrow signature
  change is required to make the rule enforceable, update all visible call
  sites consistently.
- Preserve state updates, side effects, cleanup paths, and error paths.
- Do not delete logic, replace bodies with stubs, or hide the violation by bypassing code.
- Avoid introducing new C11 syntax errors, buffer overflows, leaks, races,
  invalid pointer comparisons, dangling pointers, or unchecked arithmetic.
- Prefer a local, standard remediation for the target rule.

C code:
```c
{code}
```

Return only the complete corrected C code. No markdown."""

REPAIR_RULE_SPECIFIC_GUIDANCE: dict[str, str] = {
    "INT30-C": """Rule-specific guidance:
- Prevent unsigned wraparound before it occurs; do not rely only on checking
  the result after arithmetic.
- For addition, check `UINT_MAX - a < b`; for multiplication, check
  `a != 0 && b > UINT_MAX / a`; adapt to the actual unsigned type.
- Preserve valid-input results and existing error handling.
- Apply the check to every visible arithmetic expression that can wrap,
  including size calculations.""",
    "INT32-C": """Rule-specific guidance:
- Prevent signed overflow in every intermediate expression, not just in the
  final cast.
- Widen operands to `int64_t` or wider before addition, subtraction,
  multiplication, scaling, divisor scaling, accumulation, and derivative/error
  calculations, or use explicit range checks before the operation.
- Watch for subtractions that overflow before widening; cast both operands to a
  wider signed type first.
- Check bounds before converting back to the narrower signed type and preserve
  valid-input results.""",
}

SIMPLE_STRUCTURED_REPAIR_TEMPLATE = """You are a focused CERT-C repair model for C source code.

Analyze the complete input file for concrete CERT-C violations. This is the
simple repair path: prefer one clear, local repair over broad refactoring. If
the code is safe, ambiguous, too large, or requires whole-program reasoning,
do not invent a fix.

{rule_filter}

Return exactly one of these forms.

If no concrete violation exists:
DECISION: NO_VIOLATIONS

If a concrete violation exists and can be fixed safely:
DECISION: APPLY_FIX
RULE: <CERT-C rule id>
LINE: <1-based line number>
EVIDENCE: <one-line concrete evidence>
Then output one fenced C code block containing the complete fixed C source file.

If the case is ambiguous or unsafe to fix in simple mode:
DECISION: UNRESOLVED
EVIDENCE: <one-line reason>

Preserve observable behavior, side effects, API contracts, ownership, resource
lifetime, and return values. Do not delete behavior to make a warning disappear.
The fixed source must make a substantive code change. If you cannot produce a
real change, return UNRESOLVED instead of echoing the original source.

For MEM30-C use-after-free, preserve the intended use by moving the use before
freeing the object, or by otherwise ensuring the freed pointer is never accessed.

Input file:
```c
{code}
```

Decision:"""

BUILTIN_REPAIR_PROFILES: dict[str, RepairPromptProfile] = {
    "certfix_simple_structured_v0": RepairPromptProfile(
        name="certfix_simple_structured_v0",
        output_mode=RepairOutputMode.STRUCTURED,
        template=SIMPLE_STRUCTURED_REPAIR_TEMPLATE,
    ),
    "qwen36_27b_zs_fix_code_only_v1": RepairPromptProfile(
        name="qwen36_27b_zs_fix_code_only_v1",
        output_mode=RepairOutputMode.CODE_ONLY,
        template=QWEN36_CODE_ONLY_FIX_TEMPLATE,
    ),
    "qwen36_27b_zs_fix_full_file_v2": RepairPromptProfile(
        name="qwen36_27b_zs_fix_full_file_v2",
        output_mode=RepairOutputMode.CODE_ONLY,
        template=QWEN36_FULL_FILE_FIX_TEMPLATE,
        temperature=0.0,
    ),
    "qwen36_27b_complete_repair_v2": RepairPromptProfile(
        name="qwen36_27b_complete_repair_v2",
        output_mode=RepairOutputMode.CODE_ONLY,
        template=QWEN36_COMPLETE_REPAIR_V2_TEMPLATE,
        temperature=0.0,
    ),
    "qwen36_27b_complete_repair_rule_guided_v1": RepairPromptProfile(
        name="qwen36_27b_complete_repair_rule_guided_v1",
        output_mode=RepairOutputMode.CODE_ONLY,
        template=QWEN36_COMPLETE_REPAIR_RULE_GUIDED_V1_TEMPLATE,
        temperature=0.0,
    ),
}

# Model name substring → profile name mapping (longer substrings checked first)
MODEL_TO_PROFILE: dict[str, str] = {
    "glm-4-9b": "glm",
    "glm-4": "glm",
    "glm": "glm",
    "deepseek-v3": "deepseek",
    "deepseek-coder": "deepseek",
    "deepseek": "deepseek",
    "qwen3-235b": "qwen-large",
    "qwen3-coder": "qwen-coder",
    "qwen-coder": "qwen-coder",
    "ministral": "ministral",
    "devstral": "devstral",
}


def resolve_profile(
    model_name: str,
    explicit_profile: str | None = None,
    custom_profiles: dict[str, PromptProfile] | None = None,
) -> PromptProfile:
    """Resolve the prompt profile to use.

    Priority: explicit > custom match > auto-detect from model name > default.

    Args:
        model_name: Model name for auto-detection.
        explicit_profile: Explicitly requested profile name.
        custom_profiles: User-defined custom profiles.

    Returns:
        Resolved PromptProfile.

    Raises:
        ConfigError: If explicit profile name is not found.
    """
    all_custom = custom_profiles or {}

    if explicit_profile:
        if explicit_profile in BUILTIN_PROFILES:
            logger.info("Using built-in prompt profile: %s", explicit_profile)
            return BUILTIN_PROFILES[explicit_profile]
        if explicit_profile in all_custom:
            logger.info("Using custom prompt profile: %s", explicit_profile)
            return all_custom[explicit_profile]
        raise ConfigError(
            f"Unknown prompt profile: {explicit_profile!r}. "
            f"Available: {sorted(list(BUILTIN_PROFILES) + list(all_custom))}"
        )

    # Auto-detect from model name (longer substrings first for specificity)
    if model_name:
        model_lower = model_name.lower()
        sorted_keys = sorted(MODEL_TO_PROFILE, key=len, reverse=True)
        for substr in sorted_keys:
            if substr in model_lower:
                profile_name = MODEL_TO_PROFILE[substr]
                logger.info(
                    "Auto-detected prompt profile %r for model %r",
                    profile_name,
                    model_name,
                )
                return BUILTIN_PROFILES[profile_name]

    logger.info("Using default prompt profile")
    return BUILTIN_PROFILES["default"]


def resolve_repair_profile(profile_name: str | None = None) -> RepairPromptProfile:
    """Resolve a built-in repair prompt profile by name."""
    selected = profile_name or "certfix_simple_structured_v0"
    try:
        return BUILTIN_REPAIR_PROFILES[selected]
    except KeyError as e:
        raise ConfigError(
            f"Unknown repair prompt profile: {selected!r}. "
            f"Available: {sorted(BUILTIN_REPAIR_PROFILES)}"
        ) from e


def get_repair_rule_specific_guidance(rule_id: str | None) -> str:
    """Return release-enabled rule-specific repair guidance for a CERT-C rule."""
    if not rule_id:
        return ""
    return REPAIR_RULE_SPECIFIC_GUIDANCE.get(rule_id, "")


def load_custom_profiles(
    config_data: dict[str, Any] | None,
) -> dict[str, PromptProfile]:
    """Load custom profiles from config data.

    Args:
        config_data: Dict mapping profile names to factor settings.

    Returns:
        Dict of profile name to PromptProfile.

    Raises:
        ConfigError: If a custom profile name collides with a built-in,
            or if factor values are invalid.
    """
    if not config_data:
        return {}

    profiles: dict[str, PromptProfile] = {}
    for name, factors in config_data.items():
        if name in BUILTIN_PROFILES:
            raise ConfigError(
                f"Custom profile {name!r} conflicts with built-in profile. Choose a different name."
            )
        try:
            profiles[name] = PromptProfile(
                name=name,
                example_ratio=ExampleRatio(factors.get("example_ratio", "vio_heavy")),
                instruction_emphasis=InstructionEmphasis(
                    factors.get("instruction_emphasis", "violation")
                ),
                example_order=ExampleOrder(factors.get("example_order", "violation_first")),
                d1_optimization=bool(factors.get("d1_optimization", False)),
                d1_bias=bool(factors.get("d1_bias", False)),
            )
        except ValueError as e:
            raise ConfigError(f"Invalid factor value in custom profile {name!r}: {e}") from e

    return profiles
