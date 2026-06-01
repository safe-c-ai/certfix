"""Configuration management for certfix."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_ROLE_MODEL_CONFIG_KEYS = {
    "backend",
    "profile",
    "path",
    "model_dir",
    "lora_path",
    "adapter_path",
    "threads",
    "n_threads",
    "timeout",
    "n_ctx",
    "n_gpu_layers",
    "chat_completion",
    "max_tokens",
    "temperature",
    "qwen36_rule_id_strategy",
    "qwen36_selector_candidate_k",
    "qwen36_selector_permutations",
    "api",
}


@dataclass
class ApiConfig:
    """API backend configuration."""

    base_url: str = ""
    model: str = ""
    api_key_env: str = "CERTFIX_API_KEY"
    timeout: int = 120
    max_tokens: int = 4096
    temperature: float = 0.1
    retry_attempts: int = 3
    retry_initial_delay: float = 2.0
    retry_max_delay: float = 30.0
    extra_body: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelConfig:
    """Model configuration."""

    backend: str = "api"
    path: str | None = None
    threads: int | None = None
    timeout: int = 300
    api: ApiConfig = field(default_factory=ApiConfig)


@dataclass
class DetectionModelConfig:
    """Detection model configuration."""

    backend: str = "local_llama_server"
    path: str | None = None
    n_threads: int | None = None
    timeout: int = 300
    n_ctx: int = 8192
    n_gpu_layers: int | None = None
    prompt_profile: str | None = None
    rule_catalog_path: str | None = None
    custom_profiles: dict[str, dict[str, Any]] | None = None
    batch_size: int = 3
    qwen36_rule_id_strategy: str = "batch_top1"
    qwen36_selector_candidate_k: int = 2
    qwen36_selector_permutations: int = 3
    include_dirs: list[str] = field(default_factory=list)
    api: ApiConfig = field(default_factory=ApiConfig)


@dataclass
class RoleModelConfig:
    """Named model role configuration."""

    backend: str = ""
    profile: str | None = None
    path: str | None = None
    model_dir: str | None = None
    lora_path: str | None = None
    adapter_path: str | None = None
    threads: int | None = None
    n_threads: int | None = None
    timeout: int | None = None
    n_ctx: int | None = None
    n_gpu_layers: int | None = None
    chat_completion: bool | None = None
    max_tokens: int | None = None
    temperature: float | None = None
    api: ApiConfig = field(default_factory=ApiConfig)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class CompileValidationConfig:
    """Compile validation gate configuration."""

    enabled: bool = True
    command: str = "gcc"
    args: list[str] = field(default_factory=lambda: ["-fsyntax-only"])
    include_paths: list[str] = field(default_factory=list)
    timeout: int = 30


@dataclass
class ViolationRemovalValidationConfig:
    """Violation removal validation gate configuration."""

    enabled: bool = True
    detector_role: str = "qwen36_local"
    method: str = "non_target_advisory"
    max_tokens: int = 512
    override_denylist: list[str] = field(default_factory=lambda: ["SIG34-C", "STR31-C"])


@dataclass
class SemanticValidationConfig:
    """Semantic validation gate configuration."""

    enabled: bool = True
    reviewer_role: str = "qwen36_local"
    block_on_uncertain: bool = True


@dataclass
class ValidationConfig:
    """Validation gates for repair output."""

    compile: CompileValidationConfig = field(default_factory=CompileValidationConfig)
    violation_removal: ViolationRemovalValidationConfig = field(
        default_factory=ViolationRemovalValidationConfig
    )
    semantic: SemanticValidationConfig = field(default_factory=SemanticValidationConfig)


@dataclass
class CheckConfig:
    """Check command configuration."""

    rules: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)


@dataclass
class FixConfig:
    """Fix command configuration."""

    simple_repairer_role: str | None = None
    simple_repair_profile: str = "certfix_simple_structured_v0"
    simple_max_tokens: int = 4096
    validate_guided_retry: bool = False
    retry_max_attempts: int = 1
    retry_max_tokens: int = 4096
    retry_rule_addenda_v1: bool = True
    retry_rule_addenda_rule_ids: list[str] = field(
        default_factory=lambda: ["ARR37-C", "CON31-C", "POS48-C", "SIG30-C", "ENV33-C"]
    )


@dataclass
class PipelineOverrideConfig:
    """Optional per-step role overrides for advanced model routing."""

    detection: str | None = None
    rule_selection: str | None = None
    rule_candidate_generation: str | None = None
    rule_selector_voting: str | None = None
    fix_generation: str | None = None
    post_fix_detection: str | None = None
    retry_generation: str | None = None
    retry_post_fix_detection: str | None = None
    retry_semantic_check: str | None = None
    retry_violation_audit: str | None = None
    semantic_check: str | None = None
    violation_audit: str | None = None


@dataclass
class PipelineConfig:
    """Pipeline routing configuration."""

    overrides: PipelineOverrideConfig = field(default_factory=PipelineOverrideConfig)


@dataclass
class Config:
    """Main configuration."""

    model: ModelConfig = field(default_factory=ModelConfig)
    detection: DetectionModelConfig = field(default_factory=DetectionModelConfig)
    models: dict[str, RoleModelConfig] = field(default_factory=dict)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    check: CheckConfig = field(default_factory=CheckConfig)
    fix: FixConfig = field(default_factory=FixConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)

    def step_role(self, step: str, default: str | None = None) -> str | None:
        """Return the configured role for a pipeline step."""
        return getattr(self.pipeline.overrides, step, None) or default

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        """Load configuration from file."""
        if path is None:
            path = Path(".certfix.yaml")

        if not path.exists():
            return cls()

        with open(path) as f:
            data: dict[str, Any] = yaml.safe_load(f) or {}

        model_data = data.get("model", {})
        detection_data = data.get("detection", {})
        check_data = data.get("check", {})
        fix_data = data.get("fix", {})

        return cls(
            model=_load_model_config(model_data),
            detection=_load_detection_model_config(detection_data),
            models=_load_role_model_configs(data.get("models", {})),
            validation=_load_validation_config(data.get("validation", {})),
            pipeline=_load_pipeline_config(data.get("pipeline", {})),
            check=CheckConfig(
                rules=check_data.get("rules", []),
                exclude=check_data.get("exclude", []),
            ),
            fix=FixConfig(
                simple_repairer_role=fix_data.get("simple_repairer_role"),
                simple_repair_profile=fix_data.get(
                    "simple_repair_profile", "certfix_simple_structured_v0"
                ),
                simple_max_tokens=fix_data.get("simple_max_tokens", 4096),
                validate_guided_retry=fix_data.get("validate_guided_retry", False),
                retry_max_attempts=fix_data.get("retry_max_attempts", 1),
                retry_max_tokens=fix_data.get("retry_max_tokens", 4096),
                retry_rule_addenda_v1=fix_data.get("retry_rule_addenda_v1", True),
                retry_rule_addenda_rule_ids=fix_data.get(
                    "retry_rule_addenda_rule_ids",
                    ["ARR37-C", "CON31-C", "POS48-C", "SIG30-C", "ENV33-C"],
                ),
            ),
        )


def _load_api_config(data: dict[str, Any]) -> ApiConfig:
    return ApiConfig(
        base_url=data.get("base_url", ""),
        model=data.get("model", ""),
        api_key_env=data.get("api_key_env", "CERTFIX_API_KEY"),
        timeout=data.get("timeout", 120),
        max_tokens=data.get("max_tokens", 4096),
        temperature=data.get("temperature", 0.1),
        retry_attempts=data.get("retry_attempts", 3),
        retry_initial_delay=data.get("retry_initial_delay", 2.0),
        retry_max_delay=data.get("retry_max_delay", 30.0),
        extra_body=data.get("extra_body", {}),
    )


def _load_model_config(data: dict[str, Any]) -> ModelConfig:
    return ModelConfig(
        backend=data.get("backend", "api"),
        path=data.get("path"),
        threads=data.get("threads"),
        timeout=data.get("timeout", 300),
        api=_load_api_config(data.get("api", {})),
    )


def _load_detection_model_config(data: dict[str, Any]) -> DetectionModelConfig:
    return DetectionModelConfig(
        backend=data.get("backend", "local_llama_server"),
        path=data.get("path"),
        n_threads=data.get("n_threads"),
        timeout=data.get("timeout", 300),
        n_ctx=data.get("n_ctx", 8192),
        n_gpu_layers=data.get("n_gpu_layers"),
        prompt_profile=data.get("prompt_profile"),
        rule_catalog_path=data.get("rule_catalog_path"),
        custom_profiles=data.get("custom_profiles"),
        batch_size=data.get("batch_size", 3),
        qwen36_rule_id_strategy=data.get("qwen36_rule_id_strategy", "batch_top1"),
        qwen36_selector_candidate_k=data.get("qwen36_selector_candidate_k", 2),
        qwen36_selector_permutations=data.get("qwen36_selector_permutations", 3),
        include_dirs=data.get("include_dirs", []),
        api=_load_api_config(data.get("api", {})),
    )


def _load_role_model_configs(data: dict[str, Any]) -> dict[str, RoleModelConfig]:
    configs: dict[str, RoleModelConfig] = {}
    for role_name, role_data in data.items():
        if isinstance(role_data, dict):
            configs[role_name] = _load_role_model_config(role_data)
    return configs


def _load_role_model_config(data: dict[str, Any]) -> RoleModelConfig:
    extra = {key: value for key, value in data.items() if key not in _ROLE_MODEL_CONFIG_KEYS}
    return RoleModelConfig(
        backend=data.get("backend", ""),
        profile=data.get("profile"),
        path=data.get("path"),
        model_dir=data.get("model_dir"),
        lora_path=data.get("lora_path"),
        adapter_path=data.get("adapter_path"),
        threads=data.get("threads"),
        n_threads=data.get("n_threads"),
        timeout=data.get("timeout"),
        n_ctx=data.get("n_ctx"),
        n_gpu_layers=data.get("n_gpu_layers"),
        chat_completion=data.get("chat_completion"),
        max_tokens=data.get("max_tokens"),
        temperature=data.get("temperature"),
        api=_load_api_config(data.get("api", {})),
        extra=extra,
    )


def _load_validation_config(data: dict[str, Any]) -> ValidationConfig:
    compile_data = data.get("compile", {})
    removal_data = data.get("violation_removal", {})
    semantic_data = data.get("semantic", {})
    return ValidationConfig(
        compile=CompileValidationConfig(
            enabled=compile_data.get("enabled", True),
            command=compile_data.get("command", "gcc"),
            args=compile_data.get("args", ["-fsyntax-only"]),
            include_paths=compile_data.get("include_paths", []),
            timeout=compile_data.get("timeout", 30),
        ),
        violation_removal=ViolationRemovalValidationConfig(
            enabled=removal_data.get("enabled", True),
            detector_role=removal_data.get("detector_role", "qwen36_local"),
            method=removal_data.get("method", "non_target_advisory"),
            max_tokens=removal_data.get("max_tokens", 512),
            override_denylist=removal_data.get(
                "override_denylist",
                ["SIG34-C", "STR31-C"],
            ),
        ),
        semantic=SemanticValidationConfig(
            enabled=semantic_data.get("enabled", True),
            reviewer_role=semantic_data.get("reviewer_role", "qwen36_local"),
            block_on_uncertain=semantic_data.get("block_on_uncertain", True),
        ),
    )


def _load_pipeline_config(data: dict[str, Any]) -> PipelineConfig:
    overrides_data = data.get("overrides", {})
    return PipelineConfig(
        overrides=PipelineOverrideConfig(
            detection=overrides_data.get("detection"),
            rule_selection=overrides_data.get("rule_selection"),
            rule_candidate_generation=overrides_data.get("rule_candidate_generation"),
            rule_selector_voting=overrides_data.get("rule_selector_voting"),
            fix_generation=overrides_data.get("fix_generation"),
            post_fix_detection=overrides_data.get("post_fix_detection"),
            retry_generation=overrides_data.get("retry_generation"),
            retry_post_fix_detection=overrides_data.get("retry_post_fix_detection"),
            retry_semantic_check=overrides_data.get("retry_semantic_check"),
            retry_violation_audit=overrides_data.get("retry_violation_audit"),
            semantic_check=overrides_data.get("semantic_check"),
            violation_audit=overrides_data.get("violation_audit"),
        )
    )
