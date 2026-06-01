"""Tests for build_detection_prompt and factor-based prompt construction."""

from certfix.prompt_profiles import (
    ExampleOrder,
    ExampleRatio,
    InstructionEmphasis,
    PromptProfile,
)
from certfix.prompts import (
    DETECTION_PROMPT,
    SAFE_EXAMPLES,
    VIOLATION_EXAMPLES,
    build_detection_prompt,
    build_simple_repair_prompt,
)


def _profile(**kwargs: object) -> PromptProfile:
    defaults = {
        "name": "test",
        "example_ratio": ExampleRatio.VIO_HEAVY,
        "instruction_emphasis": InstructionEmphasis.VIOLATION,
        "example_order": ExampleOrder.VIOLATION_FIRST,
        "d1_optimization": False,
        "d1_bias": False,
    }
    defaults.update(kwargs)
    return PromptProfile(**defaults)  # type: ignore[arg-type]


class TestBuildDetectionPrompt:
    """Tests for build_detection_prompt."""

    def test_contains_code(self) -> None:
        prompt = build_detection_prompt("int x;", _profile())
        assert "int x;" in prompt

    def test_contains_output_format(self) -> None:
        prompt = build_detection_prompt("int x;", _profile())
        assert "VIOLATION:" in prompt
        assert "NO_VIOLATIONS" in prompt

    def test_violation_emphasis_instruction(self) -> None:
        prompt = build_detection_prompt(
            "int x;",
            _profile(instruction_emphasis=InstructionEmphasis.VIOLATION),
        )
        assert "memory management" in prompt

    def test_safe_emphasis_instruction(self) -> None:
        prompt = build_detection_prompt(
            "int x;",
            _profile(instruction_emphasis=InstructionEmphasis.SAFE),
        )
        assert "false positives" in prompt.lower() or "Avoid false positives" in prompt

    def test_d1_optimization(self) -> None:
        prompt = build_detection_prompt(
            "int x;",
            _profile(d1_optimization=True),
        )
        assert "high confidence" in prompt

    def test_d1_bias(self) -> None:
        prompt = build_detection_prompt(
            "int x;",
            _profile(d1_optimization=True, d1_bias=True),
        )
        assert "lean toward" in prompt

    def test_d1_bias_without_optimization(self) -> None:
        """d1_bias without d1_optimization should not include bias text."""
        prompt = build_detection_prompt(
            "int x;",
            _profile(d1_optimization=False, d1_bias=True),
        )
        assert "lean toward" not in prompt

    def test_vio_heavy_has_more_violation_examples(self) -> None:
        prompt = build_detection_prompt(
            "int x;",
            _profile(example_ratio=ExampleRatio.VIO_HEAVY),
        )
        # VIO_HEAVY: 4 vio + 1 safe
        vio_count = sum(1 for e in VIOLATION_EXAMPLES[:4] if e["output"] in prompt)
        safe_count = sum(1 for e in SAFE_EXAMPLES[:1] if e["output"] in prompt)
        assert vio_count >= 3
        assert safe_count >= 1

    def test_safe_heavy_has_more_safe_examples(self) -> None:
        prompt = build_detection_prompt(
            "int x;",
            _profile(example_ratio=ExampleRatio.SAFE_HEAVY),
        )
        assert prompt.count("NO_VIOLATIONS") >= 4  # 4 safe examples + 1 format instruction

    def test_violation_first_order(self) -> None:
        prompt = build_detection_prompt(
            "int x;",
            _profile(
                example_order=ExampleOrder.VIOLATION_FIRST,
                example_ratio=ExampleRatio.VIO_HEAVY,
            ),
        )
        # First example should be a violation example
        first_ex_idx = prompt.find("Example 1:")
        no_vio_idx = prompt.find("NO_VIOLATIONS")
        vio_idx = prompt.find("VIOLATION: MEM30-C")
        assert vio_idx < no_vio_idx or no_vio_idx == -1 or (first_ex_idx < vio_idx < no_vio_idx)

    def test_safe_first_order(self) -> None:
        prompt = build_detection_prompt(
            "int x;",
            _profile(
                example_order=ExampleOrder.SAFE_FIRST,
                example_ratio=ExampleRatio.VIO_HEAVY,
            ),
        )
        # First example should be a safe example
        ex1_idx = prompt.find("Example 1:")
        first_no_vio = prompt.find("NO_VIOLATIONS", ex1_idx)
        first_vio = prompt.find("VIOLATION:", ex1_idx)
        # NO_VIOLATIONS should appear before VIOLATION in examples
        assert first_no_vio < first_vio

    def test_rules_param_accepted(self) -> None:
        """rules param should be accepted without error (future extension)."""
        prompt = build_detection_prompt(
            "int x;",
            _profile(),
            rules=["EXP33-C"],
        )
        assert "int x;" in prompt

    def test_backward_compat_detection_prompt_still_exists(self) -> None:
        """Original DETECTION_PROMPT template should still be importable."""
        assert "{code}" in DETECTION_PROMPT
        assert "VIOLATION:" in DETECTION_PROMPT


class TestBuildFixPrompt:
    """Tests for fix prompt construction."""

    def test_qwen36_code_only_simple_prompt_uses_seed_generator_format(self) -> None:
        prompt = build_simple_repair_prompt(
            "void f(void) { free(p); puts(p); }",
            rules=["MEM30-C"],
            profile_name="qwen36_27b_zs_fix_code_only_v1",
        )

        assert prompt.startswith("The following C code has a CERT-C rule MEM30-C violation")
        assert "Output only C code" in prompt
        assert "Keep ALL original #include headers" in prompt
        assert "DECISION:" not in prompt

    def test_qwen36_full_file_simple_prompt_requires_complete_source(self) -> None:
        prompt = build_simple_repair_prompt(
            "#include <stdio.h>\nvoid f(void) {}",
            rules=["MEM30-C"],
            profile_name="qwen36_27b_zs_fix_full_file_v2",
        )

        assert "complete C source file" in prompt
        assert "complete corrected C source file" in prompt
        assert "not a snippet, function body, or patch" in prompt
        assert "Preserve unrelated declarations" in prompt

    def test_qwen36_complete_repair_v2_prompt_uses_no_think(self) -> None:
        prompt = build_simple_repair_prompt(
            "void f(void) {}",
            rules=["MEM30-C"],
            profile_name="qwen36_27b_complete_repair_v2",
        )

        assert prompt.startswith("/no_think")
        assert "complete corrected C code" in prompt
        assert "Do not delete logic" in prompt

    def test_qwen36_rule_guided_repair_prompt_adds_enabled_rule_guidance(self) -> None:
        prompt = build_simple_repair_prompt(
            "unsigned a, b, c;\nc = a + b;",
            rules=["INT30-C"],
            profile_name="qwen36_27b_complete_repair_rule_guided_v1",
        )

        assert prompt.startswith("/no_think")
        assert "Prevent unsigned wraparound before it occurs" in prompt
        assert "Preserve externally visible behavior" in prompt
