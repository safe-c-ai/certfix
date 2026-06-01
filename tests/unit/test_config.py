"""Tests for configuration loading."""

from pathlib import Path

from certfix.config import Config


def test_load_missing_file_uses_release_defaults(tmp_path: Path) -> None:
    """Missing config should use the release detection backend default."""
    cfg = Config.load(tmp_path / "missing.yaml")

    assert cfg.model.backend == "api"
    assert cfg.detection.backend == "local_llama_server"
    assert cfg.models == {}
    assert cfg.validation.compile.enabled is True
    assert cfg.validation.semantic.block_on_uncertain is True
    assert cfg.fix.simple_repair_profile == "certfix_simple_structured_v0"
    assert cfg.fix.validate_guided_retry is False


def test_load_model_and_detection_config(tmp_path: Path) -> None:
    """Current model/detection keys should load."""
    config_path = tmp_path / ".certfix.yaml"
    config_path.write_text(
        """
model:
  backend: api
  api:
    base_url: https://api.example.com/v1
    model: fix-model
detection:
  backend: local_llama_server
  prompt_profile: qwen36_certfix_check_v1
  batch_size: 1
  qwen36_rule_id_strategy: sequential_top2_p3
""",
        encoding="utf-8",
    )

    cfg = Config.load(config_path)

    assert cfg.model.api.base_url == "https://api.example.com/v1"
    assert cfg.model.api.model == "fix-model"
    assert cfg.detection.backend == "local_llama_server"
    assert cfg.detection.prompt_profile == "qwen36_certfix_check_v1"
    assert cfg.detection.batch_size == 1
    assert cfg.detection.qwen36_rule_id_strategy == "sequential_top2_p3"


def test_load_role_based_model_config(tmp_path: Path) -> None:
    """Current role-based model settings should load."""
    config_path = tmp_path / ".certfix.yaml"
    config_path.write_text(
        """
models:
  qwen36_local:
    backend: local_llama_server
    profile: qwen36_27b_release
    custom_runtime_flag: keep-me
    api:
      base_url: http://127.0.0.1:8952/v1
      model: qwen-local
      api_key_env: ""
  gemini_api:
    backend: api
    profile: gemini_3_flash_preview
    max_tokens: 4096
    api:
      base_url: http://127.0.0.1:8952/v1
      model: qwen-local
      api_key_env: ""
""",
        encoding="utf-8",
    )

    cfg = Config.load(config_path)

    qwen36 = cfg.models["qwen36_local"]
    gemini = cfg.models["gemini_api"]
    assert qwen36.profile == "qwen36_27b_release"
    assert qwen36.backend == "local_llama_server"
    assert qwen36.api.base_url == "http://127.0.0.1:8952/v1"
    assert qwen36.extra == {"custom_runtime_flag": "keep-me"}
    assert gemini.backend == "api"
    assert gemini.api.base_url == "http://127.0.0.1:8952/v1"
    assert gemini.api.model == "qwen-local"
    assert cfg.model.backend == "api"


def test_load_validation_config(tmp_path: Path) -> None:
    """Validation gate settings should load for planned apply blocking behavior."""
    config_path = tmp_path / ".certfix.yaml"
    config_path.write_text(
        """
validation:
  compile:
    enabled: true
    command: clang
    args: ["-fsyntax-only", "-Wall"]
    include_paths: ["tests/support", "third_party/include"]
    timeout: 45
  violation_removal:
    enabled: true
    detector_role: qwen36_local
    method: target_only_override
    max_tokens: 384
    override_denylist: ["SIG34-C"]
  semantic:
    enabled: true
    reviewer_role: qwen36_local
    block_on_uncertain: true
""",
        encoding="utf-8",
    )

    cfg = Config.load(config_path)

    assert cfg.validation.compile.command == "clang"
    assert cfg.validation.compile.args == ["-fsyntax-only", "-Wall"]
    assert cfg.validation.compile.include_paths == ["tests/support", "third_party/include"]
    assert cfg.validation.compile.timeout == 45
    assert cfg.validation.violation_removal.detector_role == "qwen36_local"
    assert cfg.validation.violation_removal.method == "target_only_override"
    assert cfg.validation.violation_removal.max_tokens == 384
    assert cfg.validation.violation_removal.override_denylist == ["SIG34-C"]
    assert cfg.validation.semantic.reviewer_role == "qwen36_local"
    assert cfg.validation.semantic.block_on_uncertain is True


def test_load_pipeline_step_overrides(tmp_path: Path) -> None:
    """Pipeline step overrides should load advanced per-step role routing."""
    config_path = tmp_path / ".certfix.yaml"
    config_path.write_text(
        """
pipeline:
  overrides:
    detection: qwen36_local
    rule_selection: codex_low
    rule_candidate_generation: qwen36_local
    rule_selector_voting: gemini_api
    fix_generation: gemini_api
    post_fix_detection: qwen36_local
    retry_generation: codex_low
    retry_post_fix_detection: gemini_api
    retry_semantic_check: gemini_api
    retry_violation_audit: gemini_api
    semantic_check: gemini_api
    violation_audit: gemini_api
""",
        encoding="utf-8",
    )

    cfg = Config.load(config_path)

    assert cfg.step_role("detection") == "qwen36_local"
    assert cfg.step_role("rule_selection") == "codex_low"
    assert cfg.step_role("rule_candidate_generation") == "qwen36_local"
    assert cfg.step_role("rule_selector_voting") == "gemini_api"
    assert cfg.step_role("fix_generation") == "gemini_api"
    assert cfg.step_role("post_fix_detection") == "qwen36_local"
    assert cfg.step_role("retry_generation") == "codex_low"
    assert cfg.step_role("retry_post_fix_detection") == "gemini_api"
    assert cfg.step_role("retry_semantic_check") == "gemini_api"
    assert cfg.step_role("retry_violation_audit") == "gemini_api"
    assert cfg.step_role("semantic_check") == "gemini_api"
    assert cfg.step_role("violation_audit") == "gemini_api"
    assert cfg.step_role("missing", "fallback") == "fallback"


def test_load_api_extra_body(tmp_path: Path) -> None:
    """API configs should keep provider-specific request body options."""
    config_path = tmp_path / ".certfix.yaml"
    config_path.write_text(
        """
detection:
  backend: api
  api:
    base_url: https://openrouter.ai/api/v1
    model: deepseek/deepseek-v4-flash
    api_key_env: OPENROUTER_API_KEY
    extra_body:
      provider:
        order: ["DeepInfra"]
        allow_fallbacks: false
models:
  reviewer:
    backend: api
    api:
      base_url: https://openrouter.ai/api/v1
      model: deepseek/deepseek-v4-flash
      api_key_env: OPENROUTER_API_KEY
      extra_body:
        provider:
          order: ["DeepInfra"]
          allow_fallbacks: false
""",
        encoding="utf-8",
    )

    cfg = Config.load(config_path)

    expected = {"provider": {"order": ["DeepInfra"], "allow_fallbacks": False}}
    assert cfg.detection.api.extra_body == expected
    assert cfg.models["reviewer"].api.extra_body == expected


def test_load_api_retry_options(tmp_path: Path) -> None:
    """API configs should allow transient-error retry tuning."""
    config_path = tmp_path / ".certfix.yaml"
    config_path.write_text(
        """
detection:
  backend: api
  api:
    base_url: https://openrouter.ai/api/v1
    model: deepseek/deepseek-v4-flash
    retry_attempts: 5
    retry_initial_delay: 3.0
    retry_max_delay: 45.0
""",
        encoding="utf-8",
    )

    cfg = Config.load(config_path)

    assert cfg.detection.api.retry_attempts == 5
    assert cfg.detection.api.retry_initial_delay == 3.0
    assert cfg.detection.api.retry_max_delay == 45.0


def test_load_simple_fix_prompt_profile(tmp_path: Path) -> None:
    """Simple mode should allow model/task-specific repair prompt selection."""
    config_path = tmp_path / ".certfix.yaml"
    config_path.write_text(
        """
fix:
  simple_repairer_role: qwen36_local
  simple_repair_profile: qwen36_27b_zs_fix_code_only_v1
  simple_max_tokens: 8192
  validate_guided_retry: true
  retry_max_attempts: 1
  retry_max_tokens: 4096
  retry_rule_addenda_v1: true
  retry_rule_addenda_rule_ids: ["ARR37-C", "CON31-C"]
""",
        encoding="utf-8",
    )

    cfg = Config.load(config_path)

    assert cfg.fix.simple_repairer_role == "qwen36_local"
    assert cfg.fix.simple_repair_profile == "qwen36_27b_zs_fix_code_only_v1"
    assert cfg.fix.simple_max_tokens == 8192
    assert cfg.fix.validate_guided_retry is True
    assert cfg.fix.retry_max_attempts == 1
    assert cfg.fix.retry_max_tokens == 4096
    assert cfg.fix.retry_rule_addenda_v1 is True
    assert cfg.fix.retry_rule_addenda_rule_ids == ["ARR37-C", "CON31-C"]
