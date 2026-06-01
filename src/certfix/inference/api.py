"""API inference backend (OpenAI-compatible)."""

from __future__ import annotations

import json
import os
import re
import time
from contextlib import suppress
from importlib import resources
from pathlib import Path
from typing import Any

from certfix.core.rule_selection_cards import (
    RuleCard,
    RuleSelectionVote,
    aggregate_rule_selection,
    build_rule_selector_prompt,
    load_rule_cards,
    parse_selector_json,
)
from certfix.exceptions import ConfigError, InferenceError
from certfix.inference.base import InferenceBackend
from certfix.inference.parsing import extract_fixed_code, parse_violations
from certfix.models import (
    RuleCandidate,
    RuleSelectionDecision,
    RuleSelectionResult,
    Severity,
    Violation,
)
from certfix.prompt_profiles import PromptProfile, resolve_profile
from certfix.prompts import (
    build_detection_prompt,
    build_fix_prompt,
    build_qwen36_rule_id_batch_prompt,
    build_qwen36_rule_id_exclude_prompt,
    build_qwen36_rule_id_prompt,
    build_qwen36_stage1_batch_prompt,
    build_qwen36_stage1_prompt,
)

QWEN36_CHECK_PROFILE = "qwen36_certfix_check_v1"
UNKNOWN_RULE_ID = "UNKNOWN-CERT-C"


class ApiBackend(InferenceBackend):
    """Inference backend using OpenAI-compatible API."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key_env: str = "CERTFIX_API_KEY",
        timeout: int = 120,
        max_tokens: int = 4096,
        temperature: float = 0.1,
        prompt_profile: str | None = None,
        custom_profiles: dict[str, PromptProfile] | None = None,
        rule_catalog_path: str | None = None,
        use_nothink_prefill: bool = False,
        extra_body: dict[str, Any] | None = None,
        retry_attempts: int = 3,
        retry_initial_delay: float = 2.0,
        retry_max_delay: float = 30.0,
        qwen36_rule_id_strategy: str = "batch_top1",
        qwen36_selector_candidate_k: int = 2,
        qwen36_selector_permutations: int = 3,
        rule_selection_backend: InferenceBackend | None = None,
        rule_candidate_backend: InferenceBackend | None = None,
        rule_selector_backend: InferenceBackend | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key_env = api_key_env
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._prompt_profile = prompt_profile
        self._custom_profiles = custom_profiles
        self._rule_catalog_path = rule_catalog_path
        self._extra_body = dict(extra_body or {})
        self._retry_attempts = max(0, retry_attempts)
        self._retry_initial_delay = max(0.0, retry_initial_delay)
        self._retry_max_delay = max(0.0, retry_max_delay)
        self._usage: dict[str, int] = {
            "api_requests": 0,
            "api_successes": 0,
            "api_retries": 0,
            "api_failures": 0,
            "usage_responses": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        self._rule_catalog_cache: tuple[str, set[str]] | None = None
        self._rule_cards_cache: dict[str, RuleCard] | None = None
        self._use_nothink_prefill = use_nothink_prefill
        self._qwen36_rule_id_strategy = qwen36_rule_id_strategy
        self._qwen36_selector_candidate_k = qwen36_selector_candidate_k
        self._qwen36_selector_permutations = qwen36_selector_permutations
        self._rule_selection_backend = rule_selection_backend
        self._rule_candidate_backend_explicit = rule_candidate_backend is not None
        self._rule_selector_backend_explicit = rule_selector_backend is not None
        self._rule_candidate_backend = rule_candidate_backend or rule_selection_backend
        self._rule_selector_backend = rule_selector_backend or rule_selection_backend
        self.line_aware_detection = prompt_profile != QWEN36_CHECK_PROFILE
        self._client: object | None = None

    def _get_api_key(self) -> str:
        """Get API key from environment variable.

        An empty api_key_env disables auth headers for local OpenAI-compatible
        servers such as llama.cpp.

        Raises:
            ConfigError: If the environment variable is not set.
        """
        if not self.api_key_env:
            return ""
        key = os.environ.get(self.api_key_env, "")
        if not key:
            raise ConfigError(f"API key not set. Set the {self.api_key_env} environment variable.")
        return key

    def _get_client(self) -> object:
        """Get or create httpx client (lazy initialization)."""
        if self._client is None:
            import httpx

            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def _chat_completion(
        self,
        prompt: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        """Send a chat completion request.

        Args:
            prompt: The user prompt.
            max_tokens: Override for max tokens.

        Returns:
            The assistant's response text.

        Raises:
            InferenceError: If the API request fails.
        """
        import httpx

        api_key = self._get_api_key()
        client: httpx.Client = self._get_client()  # type: ignore[assignment]

        url = f"{self.base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": self.temperature if temperature is None else temperature,
        }
        payload.update(self._extra_body)

        total_attempts = self._retry_attempts + 1
        for attempt in range(total_attempts):
            self._usage["api_requests"] += 1
            try:
                response = client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                self._usage["api_successes"] += 1
                break
            except httpx.HTTPStatusError as e:
                if not self._should_retry_status(e.response.status_code, attempt, total_attempts):
                    self._usage["api_failures"] += 1
                    raise InferenceError(
                        f"API request failed ({e.response.status_code}): {e.response.text}"
                    ) from e
                self._usage["api_retries"] += 1
                self._sleep_before_retry(e.response.headers.get("retry-after"), attempt)
            except httpx.HTTPError as e:
                if attempt >= total_attempts - 1:
                    self._usage["api_failures"] += 1
                    raise InferenceError(f"API request failed: {e}") from e
                self._usage["api_retries"] += 1
                self._sleep_before_retry(None, attempt)

        data = response.json()
        self._record_usage(data)
        return str(data["choices"][0]["message"]["content"])

    def _should_retry_status(self, status_code: int, attempt: int, total_attempts: int) -> bool:
        """Return whether a transient HTTP status should be retried."""
        if attempt >= total_attempts - 1:
            return False
        return status_code in {408, 409, 425, 429, 500, 502, 503, 504}

    def _sleep_before_retry(self, retry_after: str | None, attempt: int) -> None:
        """Sleep before a transient API retry."""
        delay = self._retry_initial_delay * (2**attempt)
        if retry_after:
            with suppress(ValueError):
                delay = max(delay, float(retry_after))
        if self._retry_max_delay:
            delay = min(delay, self._retry_max_delay)
        if delay > 0:
            time.sleep(delay)

    def _record_usage(self, data: dict[str, Any]) -> None:
        """Record OpenAI-compatible token usage when the provider returns it."""
        usage = data.get("usage")
        if not isinstance(usage, dict):
            return
        self._usage["usage_responses"] += 1
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage.get(key)
            if isinstance(value, int):
                self._usage[key] += value

    def get_usage_summary(self) -> dict[str, Any]:
        """Return cumulative API request and token usage for this backend."""
        summary: dict[str, Any] = dict(self._usage)
        if self._rule_selection_backend is not None:
            get_usage = getattr(self._rule_selection_backend, "get_usage_summary", None)
            if callable(get_usage):
                summary["rule_selection_backend"] = get_usage()
        if self._rule_candidate_backend_explicit and self._rule_candidate_backend is not None:
            get_usage = getattr(self._rule_candidate_backend, "get_usage_summary", None)
            if callable(get_usage):
                summary["rule_candidate_backend"] = get_usage()
        if self._rule_selector_backend_explicit and self._rule_selector_backend is not None:
            get_usage = getattr(self._rule_selector_backend, "get_usage_summary", None)
            if callable(get_usage):
                summary["rule_selector_backend"] = get_usage()
        return summary

    def close(self) -> None:
        """Close owned HTTP clients and step-override backends."""
        if self._client is not None:
            close = getattr(self._client, "close", None)
            if callable(close):
                close()
            self._client = None
        closed: set[int] = set()
        for backend in (
            self._rule_selection_backend,
            self._rule_candidate_backend,
            self._rule_selector_backend,
        ):
            if backend is None or id(backend) in closed:
                continue
            closed.add(id(backend))
            close = getattr(backend, "close", None)
            if callable(close):
                close()

    def _completion_with_nothink_prefill(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> str:
        """Use llama.cpp /completion with Qwen no-think assistant prefill."""
        import httpx

        client: httpx.Client = self._get_client()  # type: ignore[assignment]
        root_url = self.base_url.removesuffix("/v1")
        prompt = _strip_nothink_directive(prompt)
        formatted = (
            f"<|im_start|>user\n{prompt}<|im_end|>\n"
            f"<|im_start|>assistant\n<think>\n\n</think>\n"
        )
        payload = {
            "prompt": formatted,
            "n_predict": max_tokens,
            "temperature": temperature,
            "stop": ["<|im_end|>"],
            "cache_prompt": True,
        }

        try:
            response = client.post(f"{root_url}/completion", json=payload)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise InferenceError(
                f"API request failed ({e.response.status_code}): {e.response.text}"
            ) from e
        except httpx.HTTPError as e:
            raise InferenceError(f"API request failed: {e}") from e

        return str(response.json().get("content", "")).strip()

    def _complete_prompt(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> str:
        """Complete a structured prompt through the configured API surface."""
        if self._use_nothink_prefill:
            return self._completion_with_nothink_prefill(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        return self._chat_completion(
            _strip_nothink_directive(prompt),
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def detect(self, code: str, rules: list[str] | None = None) -> list[Violation]:
        """Detect violations using API."""
        if self._prompt_profile == QWEN36_CHECK_PROFILE:
            return self._detect_qwen36_two_stage(code, rules)

        profile = resolve_profile(self.model, self._prompt_profile, self._custom_profiles)
        prompt = build_detection_prompt(code, profile, rules)
        output = self.generate(prompt, max_tokens=2048, temperature=self.temperature)
        return parse_violations(output, rules)

    def _detect_qwen36_two_stage(
        self,
        code: str,
        rules: list[str] | None = None,
    ) -> list[Violation]:
        """Run the adopted Qwen3.6 Stage 1 + Rule ID prompt flow."""
        stage1_prompt = build_qwen36_stage1_prompt(code)
        stage1_output = self._complete_prompt(
            stage1_prompt,
            max_tokens=384,
            temperature=0.0,
        )
        label = _parse_stage1_label(stage1_output)
        if label != "violation":
            return []

        rule_catalog, valid_rules = self._load_rule_catalog()
        rule_prompt = build_qwen36_rule_id_prompt(code, rule_catalog)
        rule_output = self._complete_prompt(
            rule_prompt,
            max_tokens=128,
            temperature=0.0,
        )
        rule_id = _parse_rule_id(rule_output, valid_rules) or UNKNOWN_RULE_ID

        if rules and rule_id not in rules:
            return []

        return [
            Violation(
                rule_id=rule_id,
                file_path="",
                line=1,
                column=1,
                message=(
                    "Qwen3.6 prompt-profile detection "
                    "(stage1_balanced_prior -> rule_title_match)"
                ),
                severity=Severity.ERROR,
            )
        ]

    def detect_qwen36_batch(
        self,
        items: list[tuple[str, str]],
        rules: list[str] | None = None,
        batch_size: int = 3,
    ) -> dict[str, list[Violation]]:
        """Run the adopted Qwen3.6 Stage 1 + Rule ID flow in batches.

        Args:
            items: Pairs of stable item id and whole source text.
            rules: Optional allow-list of CERT-C rule IDs.
            batch_size: Number of source items per Stage 1 request.

        Returns:
            Mapping from item id to detected violations.
        """
        results: dict[str, list[Violation]] = {item_id: [] for item_id, _ in items}
        if self._prompt_profile != QWEN36_CHECK_PROFILE:
            for item_id, code in items:
                results[item_id] = self.detect(code, rules)
            return results

        for batch in _chunks(items, max(1, batch_size)):
            stage1_prompt = build_qwen36_stage1_batch_prompt(
                [{"id": item_id, "code": code} for item_id, code in batch]
            )
            stage1_output = self._complete_prompt(
                stage1_prompt,
                max_tokens=384,
                temperature=0.0,
            )
            labels = _parse_stage1_labels(stage1_output)
            positive = [
                (item_id, code)
                for item_id, code in batch
                if labels.get(item_id, "unknown") == "violation"
            ]
            if not positive:
                continue

            rule_catalog, valid_rules = self._load_rule_catalog()
            rule_ids: dict[str, str] = {}
            if not _uses_qwen36_sequential_p3(self._qwen36_rule_id_strategy):
                rule_prompt = build_qwen36_rule_id_batch_prompt(
                    [{"id": item_id, "code": code} for item_id, code in positive],
                    rule_catalog,
                )
                rule_output = self._complete_prompt(
                    rule_prompt,
                    max_tokens=max(128, 64 * len(positive)),
                    temperature=0.0,
                )
                rule_ids = _parse_rule_ids(rule_output, valid_rules)
                if (
                    len(positive) == 1
                    and not rule_ids
                    and _parse_rule_id(rule_output, valid_rules)
                ):
                    rule_ids[positive[0][0]] = _parse_rule_id(rule_output, valid_rules) or ""
                elif len(positive) == 1 and positive[0][0] not in rule_ids and len(rule_ids) == 1:
                    rule_ids[positive[0][0]] = next(iter(rule_ids.values()))
            for item_id, _code in positive:
                if _uses_qwen36_sequential_p3(self._qwen36_rule_id_strategy):
                    rule_id, candidates, selection = self._select_rule_id_sequential_p3(
                        _code,
                        rule_catalog,
                        valid_rules,
                    )
                else:
                    rule_id = rule_ids.get(item_id) or UNKNOWN_RULE_ID
                    candidates = None
                    selection = None
                if rules and rule_id not in rules:
                    continue
                results[item_id] = [
                    Violation(
                        rule_id=rule_id,
                        file_path="",
                        line=1,
                        column=1,
                        message=(
                            "Qwen3.6 batched prompt-profile detection "
                            "(stage1_balanced_prior -> rule_title_match)"
                        ),
                        severity=Severity.ERROR,
                        candidates=candidates,
                        rule_selection=selection,
                    )
                ]

        return results

    def _select_rule_id_sequential_p3(
        self,
        code: str,
        rule_catalog: str,
        valid_rules: set[str],
    ) -> tuple[str, list[RuleCandidate] | None, RuleSelectionResult | None]:
        """Generate sequential Top-2 candidates and select with p3 majority."""
        excluded: list[str] = []
        additional_cues = _qwen36_rule_id_pattern_cues(code)
        candidate_limit = _qwen36_sequential_candidate_limit(
            self._qwen36_rule_id_strategy,
            self._qwen36_selector_candidate_k,
        )
        for _ in range(candidate_limit):
            prompt = build_qwen36_rule_id_exclude_prompt(
                code,
                rule_catalog,
                excluded,
                additional_candidate_cues=additional_cues,
            )
            output = self._complete_rule_candidate_prompt(
                prompt,
                max_tokens=128,
                temperature=0.0,
            )
            rule_id = _parse_single_rule_id(output, valid_rules)
            if rule_id and rule_id not in excluded:
                excluded.append(rule_id)

        if not excluded:
            return UNKNOWN_RULE_ID, None, None

        candidates = [
            RuleCandidate(rule_id=rule_id, rank=rank)
            for rank, rule_id in enumerate(excluded, 1)
        ]
        selector_candidates = excluded[: max(2, self._qwen36_selector_candidate_k)]
        selector_candidates = selector_candidates[: len(excluded)]
        if len(selector_candidates) < 2:
            return excluded[0], candidates, None

        cards = self._load_rule_cards()
        votes: list[RuleSelectionVote] = []
        for ordered_candidates in _candidate_permutations(
            selector_candidates,
            self._qwen36_selector_permutations,
        ):
            prompt = build_rule_selector_prompt(code, ordered_candidates, cards)
            output = self._complete_rule_selector_prompt(
                prompt,
                max_tokens=768,
                temperature=0.0,
            )
            votes.append(parse_selector_json(output, ordered_candidates))

        original_rank = {rule_id: rank for rank, rule_id in enumerate(selector_candidates, 1)}
        aggregate = aggregate_rule_selection(
            votes,
            original_rank,
            fallback_to_rank1_on_no_valid_vote=True,
        )
        selected = aggregate.selected_by_majority or excluded[0]
        selected_rank = next(
            (candidate.rank for candidate in candidates if candidate.rule_id == selected),
            None,
        )
        evidence_parts = [
            "Qwen3.6 sequential Top-2 p3 selector",
            f"votes={aggregate.vote_counts}",
            f"consensus={aggregate.consensus_rate:.2f}",
        ]
        if aggregate.fallback_used:
            evidence_parts.append("fallback=top1_no_valid_vote")
        selection = RuleSelectionResult(
            decision=RuleSelectionDecision.APPLY_RULE,
            selected_rule_id=selected,
            selected_rank=selected_rank,
            evidence="; ".join(evidence_parts),
            raw_output=json.dumps(
                {
                    "votes": [
                        {
                            "selected_rule": vote.selected_rule,
                            "ranked_rules": list(vote.ranked_rules),
                            "parse_ok": vote.parse_ok,
                        }
                        for vote in votes
                    ],
                    "fallback_used": aggregate.fallback_used,
                },
                ensure_ascii=False,
            ),
        )
        return selected, candidates, selection

    def _complete_rule_selection_prompt(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> str:
        """Complete Rule ID prompts through the combined rule-selection override."""
        return self._complete_step_prompt(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            backend=self._rule_selection_backend,
        )

    def _complete_rule_candidate_prompt(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> str:
        """Complete Rule ID candidate-generation prompts."""
        return self._complete_step_prompt(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            backend=self._rule_candidate_backend,
        )

    def _complete_rule_selector_prompt(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> str:
        """Complete Rule ID selector-voting prompts."""
        return self._complete_step_prompt(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            backend=self._rule_selector_backend,
        )

    def _complete_step_prompt(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
        backend: InferenceBackend | None,
    ) -> str:
        """Complete a prompt locally or through a step override backend."""
        if backend is None:
            return self._complete_prompt(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        return backend.generate(
            _strip_nothink_directive(prompt),
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def _load_rule_catalog(self) -> tuple[str, set[str]]:
        if self._rule_catalog_cache is not None:
            return self._rule_catalog_cache

        if self._rule_catalog_path:
            data = json.loads(Path(self._rule_catalog_path).read_text(encoding="utf-8"))
        else:
            data_ref = resources.files("certfix.data").joinpath(
                "cert_c_rules_with_examples.json"
            )
            data = json.loads(data_ref.read_text(encoding="utf-8"))

        blocks: list[str] = []
        valid_rules: set[str] = set()
        for category in data["categories"]:
            category_name = category["name"]
            blocks.append(f"[{category_name}]")
            for rule in category["rules"]:
                rule_id = rule["id"]
                valid_rules.add(rule_id)
                title = rule["title"]
                cue = rule.get("example")
                if cue:
                    blocks.append(f"- {rule_id}: {title}; cue: {cue}")
                else:
                    blocks.append(f"- {rule_id}: {title}")

        self._rule_catalog_cache = ("\n".join(blocks), valid_rules)
        return self._rule_catalog_cache

    def _load_rule_cards(self) -> dict[str, RuleCard]:
        if self._rule_cards_cache is None:
            self._rule_cards_cache = load_rule_cards(
                Path(self._rule_catalog_path) if self._rule_catalog_path else None
            )
        return self._rule_cards_cache

    def fix(self, code: str, violation: Violation) -> str:
        """Generate fix using API."""
        prompt = build_fix_prompt(code, violation, self._prompt_profile)
        output = self.generate(prompt, max_tokens=self.max_tokens, temperature=self.temperature)
        return extract_fixed_code(output)

    def generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.1,
        stop: list[str] | None = None,
    ) -> str:
        """Generate raw text through the API backend."""
        if self._use_nothink_prefill and _starts_with_nothink(prompt):
            return self._completion_with_nothink_prefill(
                _strip_nothink_directive(prompt),
                max_tokens=max_tokens,
                temperature=temperature,
            )
        return self._chat_completion(prompt, max_tokens=max_tokens, temperature=temperature)

    def is_available(self) -> bool:
        """Check if API backend is available."""
        try:
            import httpx  # noqa: F401
        except ImportError:
            return False
        return not self.api_key_env or bool(os.environ.get(self.api_key_env, ""))

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        """Strip markdown code fences from output."""
        # Remove opening ```c or ``` and closing ```
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        return text


def _extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)

    try:
        obj = json.loads(stripped)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(stripped[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _parse_stage1_label(output: str) -> str:
    labels = _parse_stage1_labels(output)
    if labels:
        return next(iter(labels.values()))

    match = re.search(r"\b(violation|safe)\b", output, re.IGNORECASE)
    return match.group(1).lower() if match else "unknown"


def _parse_stage1_labels(output: str) -> dict[str, str]:
    obj = _extract_json_object(output)
    labels: dict[str, str] = {}
    if obj and isinstance(obj.get("predictions"), list):
        for item in obj["predictions"]:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id", "")).strip()
            label = str(item.get("label", "")).strip().lower()
            if item_id and label in {"violation", "safe"}:
                labels[item_id] = label
    return labels


def _parse_rule_id(output: str, valid_rules: set[str]) -> str | None:
    rule_ids = _parse_rule_ids(output, valid_rules)
    if rule_ids:
        return next(iter(rule_ids.values()))
    match = re.search(r"\b[A-Z]{2,3}\d{2}-C\b", output)
    if match and match.group(0) in valid_rules:
        return match.group(0)
    return None


def _parse_rule_ids(output: str, valid_rules: set[str]) -> dict[str, str]:
    obj = _extract_json_object(output)
    rule_ids: dict[str, str] = {}
    if obj and isinstance(obj.get("predictions"), list):
        for item in obj["predictions"]:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id", "")).strip()
            rule_id = str(item.get("rule_id", "")).strip()
            if not item_id:
                continue
            match = re.search(r"\b[A-Z]{2,3}\d{2}-C\b", rule_id)
            normalized = rule_id if rule_id in valid_rules else match.group(0) if match else ""
            if normalized in valid_rules:
                rule_ids[item_id] = normalized

    return rule_ids


def _parse_single_rule_id(output: str, valid_rules: set[str]) -> str | None:
    obj = _extract_json_object(output)
    if obj:
        rule_id = str(obj.get("rule_id", "")).strip().upper()
        if rule_id in valid_rules:
            return rule_id
    return _parse_rule_id(output, valid_rules)


def _uses_qwen36_sequential_p3(strategy: str) -> bool:
    """Return whether a strategy uses sequential candidate generation with p3 voting."""
    return strategy in {"sequential_top2_p3", "sequential_top5_p3"}


def _qwen36_sequential_candidate_limit(strategy: str, configured_candidate_k: int) -> int:
    """Return candidate-generation count for sequential Qwen3.6 Rule ID strategies."""
    if strategy == "sequential_top5_p3":
        return 5
    return max(2, configured_candidate_k)


def _chunks(items: list[tuple[str, str]], size: int) -> list[list[tuple[str, str]]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _candidate_permutations(candidates: list[str], count: int) -> list[list[str]]:
    permutations: list[list[str]] = []
    for index in range(max(1, count)):
        if index % 2 == 0:
            permutations.append(list(candidates))
        else:
            permutations.append(list(reversed(candidates)))
    return permutations


def _qwen36_rule_id_pattern_cues(code: str) -> list[str]:
    cues: list[str] = []
    if _has_repeated_join_or_detach_handle(code):
        cues.append(
            "CON39-C: include this rule when the same thread handle may be joined or "
            "detached more than once, or when different cleanup paths can join/detach "
            "the same handle."
        )
    if _has_macro_like_identifier_pointer_use(code):
        cues.append(
            "MSC38-C: include this rule when code takes the address of, stores, "
            "assigns, or uses as a function pointer a predefined identifier that may "
            "be implemented as a macro, including ctype names, errno, "
            "stdin/stdout/stderr, SIG_DFL, SIG_IGN, or SIG_ERR."
        )
    return cues


def _has_repeated_join_or_detach_handle(code: str) -> bool:
    handles: dict[str, int] = {}
    for match in re.finditer(r"\bpthread_(?:join|detach)\s*\(\s*([^,\)]+)", code):
        expr = re.sub(r"\s+", "", match.group(1))
        if not expr:
            continue
        handles[expr] = handles.get(expr, 0) + 1
        if handles[expr] >= 2:
            return True
    return False


def _has_macro_like_identifier_pointer_use(code: str) -> bool:
    identifiers = (
        "isalnum|isalpha|isblank|iscntrl|isdigit|isgraph|islower|isprint|ispunct|"
        "isspace|isupper|isxdigit|tolower|toupper|errno|stdin|stdout|stderr|"
        "SIG_DFL|SIG_IGN|SIG_ERR"
    )
    return bool(
        re.search(rf"&\s*(?:{identifiers})\b", code)
        or re.search(rf"\(\s*\*\s*\w+\s*\)\s*\([^)]*\)\s*=\s*(?:{identifiers})\b", code)
        or re.search(rf"\b\w+\s*=\s*(?:{identifiers})\b", code)
    )


def _starts_with_nothink(prompt: str) -> bool:
    return prompt.lstrip().startswith("/no_think")


def _strip_nothink_directive(prompt: str) -> str:
    stripped = prompt.lstrip()
    if not stripped.startswith("/no_think"):
        return prompt
    return stripped.removeprefix("/no_think").lstrip("\r\n ")
