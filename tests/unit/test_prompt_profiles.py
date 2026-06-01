"""Tests for prompt profile resolution and custom profile loading."""

import pytest

from certfix.exceptions import ConfigError
from certfix.prompt_profiles import (
    BUILTIN_PROFILES,
    BUILTIN_REPAIR_PROFILES,
    ExampleOrder,
    ExampleRatio,
    InstructionEmphasis,
    PromptProfile,
    RepairOutputMode,
    load_custom_profiles,
    resolve_profile,
    resolve_repair_profile,
)


class TestBuiltinProfiles:
    """Tests for built-in profile definitions."""

    def test_all_profiles_have_valid_enums(self) -> None:
        for name, profile in BUILTIN_PROFILES.items():
            assert isinstance(profile.example_ratio, ExampleRatio)
            assert isinstance(profile.instruction_emphasis, InstructionEmphasis)
            assert isinstance(profile.example_order, ExampleOrder)
            assert profile.name == name

    def test_default_profile_exists(self) -> None:
        assert "default" in BUILTIN_PROFILES

    def test_expected_profiles_exist(self) -> None:
        expected = {
            "default",
            "glm",
            "deepseek",
            "qwen-large",
            "qwen-coder",
            "ministral",
            "devstral",
        }
        assert expected == set(BUILTIN_PROFILES.keys())

    def test_deepseek_has_d1(self) -> None:
        ds = BUILTIN_PROFILES["deepseek"]
        assert ds.d1_optimization is True
        assert ds.d1_bias is True

    def test_default_no_d1(self) -> None:
        d = BUILTIN_PROFILES["default"]
        assert d.d1_optimization is False
        assert d.d1_bias is False

    def test_builtin_repair_profiles_exist(self) -> None:
        assert "certfix_simple_structured_v0" in BUILTIN_REPAIR_PROFILES
        assert "qwen36_27b_zs_fix_code_only_v1" in BUILTIN_REPAIR_PROFILES
        assert "qwen36_27b_zs_fix_full_file_v2" in BUILTIN_REPAIR_PROFILES
        assert (
            BUILTIN_REPAIR_PROFILES["qwen36_27b_zs_fix_code_only_v1"].output_mode
            == RepairOutputMode.CODE_ONLY
        )


class TestResolveProfile:
    """Tests for resolve_profile."""

    def test_explicit_builtin(self) -> None:
        result = resolve_profile("some-model", explicit_profile="glm")
        assert result.name == "glm"

    def test_explicit_custom(self) -> None:
        custom = {
            "my-profile": PromptProfile(
                name="my-profile",
                example_ratio=ExampleRatio.SAFE_HEAVY,
                instruction_emphasis=InstructionEmphasis.SAFE,
                example_order=ExampleOrder.SAFE_FIRST,
            )
        }
        result = resolve_profile("model", explicit_profile="my-profile", custom_profiles=custom)
        assert result.name == "my-profile"

    def test_explicit_unknown_raises(self) -> None:
        with pytest.raises(ConfigError, match="Unknown prompt profile"):
            resolve_profile("model", explicit_profile="nonexistent")

    def test_auto_detect_glm(self) -> None:
        result = resolve_profile("GLM-4-9B-Chat")
        assert result.name == "glm"

    def test_auto_detect_deepseek(self) -> None:
        result = resolve_profile("deepseek-v3-base")
        assert result.name == "deepseek"

    def test_auto_detect_qwen_coder(self) -> None:
        result = resolve_profile("Qwen3-Coder-30B")
        assert result.name == "qwen-coder"

    def test_auto_detect_qwen_large(self) -> None:
        result = resolve_profile("Qwen3-235B-Instruct")
        assert result.name == "qwen-large"

    def test_auto_detect_ministral(self) -> None:
        result = resolve_profile("Ministral-14B")
        assert result.name == "ministral"

    def test_auto_detect_devstral(self) -> None:
        result = resolve_profile("Devstral-Small-2506")
        assert result.name == "devstral"

    def test_unknown_model_returns_default(self) -> None:
        result = resolve_profile("totally-unknown-model")
        assert result.name == "default"

    def test_empty_model_returns_default(self) -> None:
        result = resolve_profile("")
        assert result.name == "default"

    def test_explicit_takes_priority_over_auto(self) -> None:
        result = resolve_profile("GLM-4-9B", explicit_profile="deepseek")
        assert result.name == "deepseek"

    def test_longer_substring_matches_first(self) -> None:
        """glm-4-9b should match before glm-4 or glm."""
        result = resolve_profile("glm-4-9b-chat")
        assert result.name == "glm"

    def test_resolve_repair_profile_default(self) -> None:
        result = resolve_repair_profile()
        assert result.name == "certfix_simple_structured_v0"

    def test_resolve_repair_profile_explicit(self) -> None:
        result = resolve_repair_profile("qwen36_27b_zs_fix_code_only_v1")
        assert result.output_mode == RepairOutputMode.CODE_ONLY

    def test_resolve_repair_profile_unknown_raises(self) -> None:
        with pytest.raises(ConfigError, match="Unknown repair prompt profile"):
            resolve_repair_profile("missing")


class TestLoadCustomProfiles:
    """Tests for load_custom_profiles."""

    def test_empty_returns_empty(self) -> None:
        assert load_custom_profiles(None) == {}
        assert load_custom_profiles({}) == {}

    def test_valid_custom_profile(self) -> None:
        data = {
            "my-model": {
                "example_ratio": "safe_heavy",
                "instruction_emphasis": "violation",
                "example_order": "safe_first",
                "d1_optimization": True,
                "d1_bias": False,
            }
        }
        result = load_custom_profiles(data)
        assert "my-model" in result
        p = result["my-model"]
        assert p.example_ratio == ExampleRatio.SAFE_HEAVY
        assert p.instruction_emphasis == InstructionEmphasis.VIOLATION
        assert p.example_order == ExampleOrder.SAFE_FIRST
        assert p.d1_optimization is True
        assert p.d1_bias is False

    def test_builtin_name_collision_raises(self) -> None:
        data = {
            "default": {
                "example_ratio": "vio_heavy",
                "instruction_emphasis": "violation",
                "example_order": "violation_first",
            }
        }
        with pytest.raises(ConfigError, match="conflicts with built-in"):
            load_custom_profiles(data)

    def test_invalid_enum_value_raises(self) -> None:
        data = {
            "bad": {
                "example_ratio": "invalid_value",
            }
        }
        with pytest.raises(ConfigError, match="Invalid factor value"):
            load_custom_profiles(data)

    def test_defaults_for_missing_fields(self) -> None:
        data = {"minimal": {}}
        result = load_custom_profiles(data)
        p = result["minimal"]
        assert p.example_ratio == ExampleRatio.VIO_HEAVY
        assert p.instruction_emphasis == InstructionEmphasis.VIOLATION
        assert p.example_order == ExampleOrder.VIOLATION_FIRST
        assert p.d1_optimization is False
