"""Factory functions for creating inference backends."""

from __future__ import annotations

from certfix.config import Config, RoleModelConfig
from certfix.exceptions import ConfigError
from certfix.inference.base import InferenceBackend
from certfix.prompt_profiles import load_custom_profiles


def create_detection_backend(
    cfg: Config,
    threads: int | None = None,
    timeout: int | None = None,
) -> InferenceBackend:
    """Create a detection backend based on configuration.

    Args:
        cfg: Application configuration.
        threads: CLI override for CPU threads.
        timeout: CLI override for inference timeout.

    Returns:
        Configured inference backend for detection.

    Raises:
        ConfigError: If the backend type is unknown.
    """
    backend = cfg.detection.backend
    custom_profiles = load_custom_profiles(cfg.detection.custom_profiles)
    prompt_profile = cfg.detection.prompt_profile

    if backend in {"api", "local_llama_server"}:
        from certfix.inference.api import ApiBackend

        api = cfg.detection.api
        rule_selection_backend = _create_optional_step_backend(
            cfg,
            "rule_selection",
            threads=threads,
            timeout=timeout,
        )
        rule_candidate_backend = _create_optional_step_backend(
            cfg,
            "rule_candidate_generation",
            threads=threads,
            timeout=timeout,
        )
        rule_selector_backend = _create_optional_step_backend(
            cfg,
            "rule_selector_voting",
            threads=threads,
            timeout=timeout,
        )
        return ApiBackend(
            base_url=api.base_url,
            model=api.model,
            api_key_env=api.api_key_env,
            timeout=api.timeout,
            max_tokens=api.max_tokens,
            temperature=api.temperature,
            retry_attempts=api.retry_attempts,
            retry_initial_delay=api.retry_initial_delay,
            retry_max_delay=api.retry_max_delay,
            extra_body=api.extra_body,
            use_nothink_prefill=backend == "local_llama_server",
            prompt_profile=prompt_profile,
            custom_profiles=custom_profiles,
            rule_catalog_path=cfg.detection.rule_catalog_path,
            qwen36_rule_id_strategy=cfg.detection.qwen36_rule_id_strategy,
            qwen36_selector_candidate_k=cfg.detection.qwen36_selector_candidate_k,
            qwen36_selector_permutations=cfg.detection.qwen36_selector_permutations,
            rule_selection_backend=rule_selection_backend,
            rule_candidate_backend=rule_candidate_backend,
            rule_selector_backend=rule_selector_backend,
        )

    raise ConfigError(f"Unknown detection backend: {backend!r}")


def _create_optional_step_backend(
    cfg: Config,
    step: str,
    *,
    threads: int | None,
    timeout: int | None,
) -> InferenceBackend | None:
    role_name = cfg.step_role(step)
    if not role_name:
        return None
    role = cfg.models.get(role_name)
    if role is None:
        raise ConfigError(f"models.{role_name} is required for {step}")
    return create_role_backend(role, threads=threads, timeout=timeout)


def create_fix_backend(
    cfg: Config,
    threads: int | None = None,
    timeout: int | None = None,
) -> InferenceBackend:
    """Create a fix backend based on configuration.

    Args:
        cfg: Application configuration.
        threads: CLI override for CPU threads.
        timeout: CLI override for inference timeout.

    Returns:
        Configured inference backend for fix generation.

    Raises:
        ConfigError: If the backend type is unknown.
    """
    backend = cfg.model.backend

    if backend == "api":
        from certfix.inference.api import ApiBackend

        api = cfg.model.api
        return ApiBackend(
            base_url=api.base_url,
            model=api.model,
            api_key_env=api.api_key_env,
            timeout=timeout or api.timeout,
            max_tokens=api.max_tokens,
            temperature=api.temperature,
            retry_attempts=api.retry_attempts,
            retry_initial_delay=api.retry_initial_delay,
            retry_max_delay=api.retry_max_delay,
        )

    raise ConfigError(f"Unknown fix backend: {backend!r}")


def create_role_backend(
    role: RoleModelConfig,
    threads: int | None = None,
    timeout: int | None = None,
) -> InferenceBackend:
    """Create a text-generation backend from a role config."""
    if role.backend in {"api", "local_llama_server"}:
        from certfix.inference.api import ApiBackend

        return ApiBackend(
            base_url=role.api.base_url,
            model=role.api.model,
            api_key_env=role.api.api_key_env,
            timeout=timeout or role.api.timeout,
            max_tokens=role.max_tokens or role.api.max_tokens,
            temperature=role.temperature if role.temperature is not None else role.api.temperature,
            retry_attempts=role.api.retry_attempts,
            retry_initial_delay=role.api.retry_initial_delay,
            retry_max_delay=role.api.retry_max_delay,
            extra_body=role.api.extra_body,
            prompt_profile=role.profile,
            use_nothink_prefill=role.backend == "local_llama_server",
        )

    raise ConfigError(f"Unsupported role backend for text generation: {role.backend!r}")
