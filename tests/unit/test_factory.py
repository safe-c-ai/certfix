"""Tests for inference backend factory."""

import pytest

from certfix.config import (
    ApiConfig,
    Config,
    DetectionModelConfig,
    ModelConfig,
    PipelineConfig,
    PipelineOverrideConfig,
    RoleModelConfig,
)
from certfix.exceptions import ConfigError
from certfix.inference.factory import (
    create_detection_backend,
    create_fix_backend,
    create_role_backend,
)


class TestCreateDetectionBackend:
    """Tests for create_detection_backend."""

    def test_api(self) -> None:
        """api backend should create ApiBackend."""
        cfg = Config(
            detection=DetectionModelConfig(
                backend="api",
                api=ApiConfig(
                    base_url="https://api.example.com/v1",
                    model="test-model",
                    api_key_env="TEST_KEY",
                    extra_body={"provider": {"order": ["DeepInfra"]}},
                ),
            ),
        )
        backend = create_detection_backend(cfg)

        from certfix.inference.api import ApiBackend

        assert isinstance(backend, ApiBackend)
        assert backend.base_url == "https://api.example.com/v1"
        assert backend.model == "test-model"
        assert backend._extra_body == {"provider": {"order": ["DeepInfra"]}}

    def test_api_uses_rule_selection_step_override(self) -> None:
        """Qwen3.6 API detection can route Rule ID prompts to another role."""
        cfg = Config(
            detection=DetectionModelConfig(
                backend="api",
                prompt_profile="qwen36_certfix_check_v1",
                api=ApiConfig(
                    base_url="https://api.example.com/v1",
                    model="detector",
                ),
            ),
            models={
                "gemini_selector": RoleModelConfig(
                    backend="api",
                    api=ApiConfig(
                        base_url="https://openrouter.ai/api/v1",
                        model="google/gemini-3-flash-preview",
                    ),
                )
            },
            pipeline=PipelineConfig(
                overrides=PipelineOverrideConfig(rule_selection="gemini_selector")
            ),
        )
        backend = create_detection_backend(cfg)

        from certfix.inference.api import ApiBackend

        assert isinstance(backend, ApiBackend)
        assert isinstance(backend._rule_selection_backend, ApiBackend)
        assert backend._rule_selection_backend.model == "google/gemini-3-flash-preview"
        assert backend._rule_candidate_backend is backend._rule_selection_backend
        assert backend._rule_selector_backend is backend._rule_selection_backend

    def test_api_can_split_rule_candidate_and_selector_overrides(self) -> None:
        """Qwen3.6 API detection can split candidate generation and selector voting."""
        cfg = Config(
            detection=DetectionModelConfig(
                backend="api",
                prompt_profile="qwen36_certfix_check_v1",
                api=ApiConfig(
                    base_url="https://api.example.com/v1",
                    model="detector",
                ),
            ),
            models={
                "local_candidates": RoleModelConfig(
                    backend="api",
                    api=ApiConfig(
                        base_url="http://127.0.0.1:8080/v1",
                        model="qwen-local",
                        api_key_env="",
                    ),
                ),
                "gemini_selector": RoleModelConfig(
                    backend="api",
                    api=ApiConfig(
                        base_url="https://openrouter.ai/api/v1",
                        model="google/gemini-3-flash-preview",
                    ),
                ),
            },
            pipeline=PipelineConfig(
                overrides=PipelineOverrideConfig(
                    rule_candidate_generation="local_candidates",
                    rule_selector_voting="gemini_selector",
                )
            ),
        )
        backend = create_detection_backend(cfg)

        from certfix.inference.api import ApiBackend

        assert isinstance(backend, ApiBackend)
        assert isinstance(backend._rule_candidate_backend, ApiBackend)
        assert isinstance(backend._rule_selector_backend, ApiBackend)
        assert backend._rule_candidate_backend.model == "qwen-local"
        assert backend._rule_selector_backend.model == "google/gemini-3-flash-preview"

    def test_local_llama_server_detection_uses_nothink_prefill(self) -> None:
        """Local Qwen3.6 server detection should use llama.cpp no-think prefill."""
        cfg = Config(
            detection=DetectionModelConfig(
                backend="local_llama_server",
                prompt_profile="qwen36_certfix_check_v1",
                api=ApiConfig(
                    base_url="http://127.0.0.1:8952/v1",
                    model="qwen-local",
                    api_key_env="",
                ),
            )
        )
        backend = create_detection_backend(cfg)

        from certfix.inference.api import ApiBackend

        assert isinstance(backend, ApiBackend)
        assert backend._use_nothink_prefill is True

    def test_api_forwards_prompt_profile(self) -> None:
        """prompt_profile should be forwarded to ApiBackend."""
        cfg = Config(
            detection=DetectionModelConfig(
                backend="api",
                prompt_profile="deepseek",
                api=ApiConfig(
                    base_url="https://api.example.com/v1",
                    model="test",
                ),
            ),
        )
        backend = create_detection_backend(cfg)

        from certfix.inference.api import ApiBackend

        assert isinstance(backend, ApiBackend)
        assert backend._prompt_profile == "deepseek"

    def test_custom_profiles_forwarded(self) -> None:
        """custom_profiles should be parsed and forwarded."""
        cfg = Config(
            detection=DetectionModelConfig(
                backend="api",
                api=ApiConfig(base_url="https://api.example.com/v1", model="detector"),
                custom_profiles={
                    "my-model": {
                        "example_ratio": "safe_heavy",
                        "instruction_emphasis": "violation",
                        "example_order": "safe_first",
                    }
                },
            ),
        )
        backend = create_detection_backend(cfg)

        from certfix.inference.api import ApiBackend

        assert isinstance(backend, ApiBackend)
        assert backend._custom_profiles is not None
        assert "my-model" in backend._custom_profiles

    def test_unknown_raises(self) -> None:
        """Unknown backend should raise ConfigError."""
        cfg = Config(detection=DetectionModelConfig(backend="invalid"))

        with pytest.raises(ConfigError, match="Unknown detection backend"):
            create_detection_backend(cfg)


class TestCreateFixBackend:
    """Tests for create_fix_backend."""

    def test_api(self) -> None:
        """api backend should create ApiBackend."""
        cfg = Config(
            model=ModelConfig(
                backend="api",
                api=ApiConfig(
                    base_url="https://api.example.com/v1",
                    model="fix-model",
                ),
            ),
        )
        backend = create_fix_backend(cfg)

        from certfix.inference.api import ApiBackend

        assert isinstance(backend, ApiBackend)
        assert backend.model == "fix-model"

    def test_unknown_raises(self) -> None:
        """Unknown backend should raise ConfigError."""
        cfg = Config(model=ModelConfig(backend="invalid"))

        with pytest.raises(ConfigError, match="Unknown fix backend"):
            create_fix_backend(cfg)

    def test_api_timeout_override(self) -> None:
        """CLI timeout override should be applied to API backend."""
        cfg = Config(
            model=ModelConfig(
                backend="api",
                api=ApiConfig(
                    base_url="https://api.example.com/v1",
                    model="m",
                    api_key_env="TEST_API_KEY",
                    timeout=60,
                ),
            ),
        )
        backend = create_fix_backend(cfg, timeout=300)

        from certfix.inference.api import ApiBackend

        assert isinstance(backend, ApiBackend)
        assert backend.timeout == 300

    def test_fix_generation_step_override(self) -> None:
        """create_fix_backend should ignore step overrides; direct repair uses role backends."""
        cfg = Config(
            model=ModelConfig(
                backend="api",
                api=ApiConfig(base_url="https://api.example.com/v1", model="fallback"),
            ),
            models={
                "gemini_api": RoleModelConfig(
                    backend="api",
                    api=ApiConfig(
                        base_url="https://openrouter.ai/api/v1",
                        model="google/gemini-3-flash-preview",
                    ),
                ),
            },
            pipeline=PipelineConfig(
                overrides=PipelineOverrideConfig(fix_generation="gemini_api")
            ),
        )

        backend = create_fix_backend(cfg)

        from certfix.inference.api import ApiBackend

        assert isinstance(backend, ApiBackend)
        assert backend.model == "fallback"


class TestCreateRoleBackend:
    """Tests for create_role_backend."""

    def test_api_role(self) -> None:
        """api role should create ApiBackend."""
        role = RoleModelConfig(
            backend="api",
            profile="remote-selector",
            max_tokens=1024,
            temperature=0.2,
            api=ApiConfig(
                base_url="https://api.example.com/v1",
                model="selector-model",
                api_key_env="SELECTOR_KEY",
            ),
        )

        backend = create_role_backend(role)

        from certfix.inference.api import ApiBackend

        assert isinstance(backend, ApiBackend)
        assert backend.base_url == "https://api.example.com/v1"
        assert backend.model == "selector-model"
        assert backend.api_key_env == "SELECTOR_KEY"
        assert backend.max_tokens == 1024
        assert backend.temperature == 0.2
        assert backend._prompt_profile == "remote-selector"

    def test_local_llama_server_role(self) -> None:
        """local_llama_server role should use the no-auth API-compatible backend."""
        role = RoleModelConfig(
            backend="local_llama_server",
            profile="qwen36_27b_semantic",
            max_tokens=1024,
            temperature=0.1,
            api=ApiConfig(
                base_url="http://127.0.0.1:8080/v1",
                model="unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL",
                api_key_env="",
            ),
        )

        backend = create_role_backend(role)

        from certfix.inference.api import ApiBackend

        assert isinstance(backend, ApiBackend)
        assert backend.base_url == "http://127.0.0.1:8080/v1"
        assert backend.model == "unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q4_K_XL"
        assert backend.api_key_env == ""
        assert backend._use_nothink_prefill is True

    def test_unknown_role_backend_raises(self) -> None:
        """Unsupported role backend should raise ConfigError."""
        role = RoleModelConfig(backend="unsupported")

        with pytest.raises(ConfigError, match="Unsupported role backend"):
            create_role_backend(role)
