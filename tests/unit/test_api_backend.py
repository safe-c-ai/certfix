"""Tests for API inference backend."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from certfix.exceptions import ConfigError, InferenceError
from certfix.inference.api import ApiBackend, _qwen36_rule_id_pattern_cues
from certfix.models import (
    RuleCandidate,
    RuleSelectionDecision,
    RuleSelectionResult,
    Severity,
    Violation,
)


def _make_backend(**kwargs: object) -> ApiBackend:
    """Create an ApiBackend with test defaults."""
    defaults = {
        "base_url": "https://api.example.com/v1",
        "model": "test-model",
        "api_key_env": "TEST_API_KEY",
        "timeout": 30,
        "max_tokens": 1024,
        "temperature": 0.1,
    }
    defaults.update(kwargs)
    return ApiBackend(**defaults)  # type: ignore[arg-type]


class TestIsAvailable:
    """Tests for is_available."""

    def test_httpx_not_installed(self) -> None:
        """Should return False when httpx is not installed."""
        backend = _make_backend()
        with patch.dict("sys.modules", {"httpx": None}):
            assert backend.is_available() is False

    @patch.dict("os.environ", {}, clear=True)
    def test_api_key_not_set(self) -> None:
        """Should return False when API key env is not set."""
        backend = _make_backend(api_key_env="MISSING_KEY")
        assert backend.is_available() is False

    @patch.dict("os.environ", {"TEST_API_KEY": "sk-test"})
    def test_available(self) -> None:
        """Should return True when httpx is installed and key is set."""
        backend = _make_backend()
        assert backend.is_available() is True

    @patch.dict("os.environ", {}, clear=True)
    def test_local_no_auth_available(self) -> None:
        """Empty api_key_env should allow local no-auth servers."""
        backend = _make_backend(api_key_env="")
        assert backend.is_available() is True


class TestGenerate:
    """Tests for raw generation routing."""

    def test_nothink_prefill_uses_completion_endpoint_when_enabled(self) -> None:
        backend = _make_backend(api_key_env="", use_nothink_prefill=True)
        backend._completion_with_nothink_prefill = MagicMock(return_value="ok")  # type: ignore[method-assign]
        backend._chat_completion = MagicMock(return_value="chat")  # type: ignore[method-assign]

        result = backend.generate("/no_think\nReturn code.", max_tokens=16, temperature=0.0)

        assert result == "ok"
        backend._completion_with_nothink_prefill.assert_called_once_with(  # type: ignore[attr-defined]
            "Return code.",
            max_tokens=16,
            temperature=0.0,
        )
        backend._chat_completion.assert_not_called()  # type: ignore[attr-defined]

    def test_nothink_prefill_disabled_uses_chat_completion(self) -> None:
        backend = _make_backend(api_key_env="", use_nothink_prefill=False)
        backend._completion_with_nothink_prefill = MagicMock(return_value="ok")  # type: ignore[method-assign]
        backend._chat_completion = MagicMock(return_value="chat")  # type: ignore[method-assign]

        result = backend.generate("/no_think\nReturn code.", max_tokens=16, temperature=0.0)

        assert result == "chat"
        backend._chat_completion.assert_called_once()
        backend._completion_with_nothink_prefill.assert_not_called()  # type: ignore[attr-defined]

    def test_qwen36_check_profile_uses_chat_completion_for_external_api(self) -> None:
        backend = _make_backend(
            api_key_env="",
            prompt_profile="qwen36_certfix_check_v1",
            use_nothink_prefill=False,
        )
        backend._completion_with_nothink_prefill = MagicMock(return_value="")  # type: ignore[method-assign]
        backend._chat_completion = MagicMock(  # type: ignore[method-assign]
            return_value='{"predictions":[{"id":"S001","label":"safe"}]}'
        )

        result = backend.detect("int main(void) { return 0; }")

        assert result == []
        backend._chat_completion.assert_called_once()
        backend._completion_with_nothink_prefill.assert_not_called()  # type: ignore[attr-defined]

    def test_extra_body_is_merged_into_chat_completion_payload(self) -> None:
        backend = _make_backend(
            api_key_env="",
            extra_body={"provider": {"order": ["DeepInfra"], "allow_fallbacks": False}},
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        backend._client = mock_client

        assert backend._chat_completion("test") == "ok"
        payload = mock_client.post.call_args.kwargs["json"]
        assert payload["provider"] == {"order": ["DeepInfra"], "allow_fallbacks": False}

    def test_chat_completion_records_usage(self) -> None:
        backend = _make_backend(api_key_env="")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 3,
                "total_tokens": 13,
            },
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        backend._client = mock_client

        assert backend._chat_completion("test") == "ok"
        assert backend.get_usage_summary() == {
            "api_requests": 1,
            "api_successes": 1,
            "api_retries": 0,
            "api_failures": 0,
            "usage_responses": 1,
            "prompt_tokens": 10,
            "completion_tokens": 3,
            "total_tokens": 13,
        }

    def test_usage_summary_includes_rule_selection_override(self) -> None:
        selector_backend = _make_backend(api_key_env="")
        selector_backend._usage["api_requests"] = 2
        selector_backend._usage["api_successes"] = 2
        selector_backend._usage["prompt_tokens"] = 20
        selector_backend._usage["completion_tokens"] = 4
        selector_backend._usage["total_tokens"] = 24
        backend = _make_backend(api_key_env="", rule_selection_backend=selector_backend)

        usage = backend.get_usage_summary()

        assert usage["api_requests"] == 0
        assert usage["rule_selection_backend"] == {
            "api_requests": 2,
            "api_successes": 2,
            "api_retries": 0,
            "api_failures": 0,
            "usage_responses": 0,
            "prompt_tokens": 20,
            "completion_tokens": 4,
            "total_tokens": 24,
        }

    def test_usage_summary_splits_rule_candidate_and_selector_overrides(self) -> None:
        candidate_backend = _make_backend(api_key_env="")
        candidate_backend._usage["api_requests"] = 2
        candidate_backend._usage["api_successes"] = 2
        candidate_backend._usage["prompt_tokens"] = 20
        selector_backend = _make_backend(api_key_env="")
        selector_backend._usage["api_requests"] = 3
        selector_backend._usage["api_successes"] = 3
        selector_backend._usage["prompt_tokens"] = 30
        backend = _make_backend(
            api_key_env="",
            rule_candidate_backend=candidate_backend,
            rule_selector_backend=selector_backend,
        )

        usage = backend.get_usage_summary()

        assert "rule_selection_backend" not in usage
        assert usage["rule_candidate_backend"]["api_requests"] == 2
        assert usage["rule_selector_backend"]["api_requests"] == 3

    def test_chat_completion_retries_transient_http_errors(self) -> None:
        import httpx

        backend = _make_backend(
            api_key_env="",
            retry_attempts=1,
            retry_initial_delay=0.0,
        )

        request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
        rate_limited = httpx.Response(429, request=request, text="try again")

        retry_response = MagicMock()
        retry_response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        retry_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.side_effect = [
            httpx.HTTPStatusError("rate limited", request=request, response=rate_limited),
            retry_response,
        ]
        backend._client = mock_client

        assert backend._chat_completion("test") == "ok"
        usage = backend.get_usage_summary()
        assert usage["api_requests"] == 2
        assert usage["api_retries"] == 1
        assert usage["api_successes"] == 1


class TestDetect:
    """Tests for detect."""

    @patch.dict("os.environ", {"TEST_API_KEY": "sk-test"})
    def test_parse_violations(self) -> None:
        """Should parse VIOLATION lines from API response."""
        backend = _make_backend()

        api_response = (
            "VIOLATION: MEM30-C at line 3: Do not access freed memory\n"
            "VIOLATION: EXP33-C at line 1: Do not read uninitialized memory"
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"choices": [{"message": {"content": api_response}}]}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        backend._client = mock_client

        violations = backend.detect("int x;")
        assert len(violations) == 2
        assert violations[0].rule_id == "MEM30-C"
        assert violations[0].line == 3
        assert violations[1].rule_id == "EXP33-C"

    @patch.dict("os.environ", {"TEST_API_KEY": "sk-test"})
    def test_no_violations(self) -> None:
        """Should return empty list for NO_VIOLATIONS."""
        backend = _make_backend()

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "NO_VIOLATIONS"}}]}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        backend._client = mock_client

        violations = backend.detect("int main() { return 0; }")
        assert violations == []

    @patch.dict("os.environ", {"TEST_API_KEY": "sk-test"})
    def test_rule_filter(self) -> None:
        """Should filter violations by rule list."""
        backend = _make_backend()

        api_response = (
            "VIOLATION: MEM30-C at line 3: Do not access freed memory\n"
            "VIOLATION: EXP33-C at line 1: Do not read uninitialized memory"
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": api_response}}]}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        backend._client = mock_client

        violations = backend.detect("int x;", rules=["MEM30-C"])
        assert len(violations) == 1
        assert violations[0].rule_id == "MEM30-C"

    @patch.dict("os.environ", {"TEST_API_KEY": "sk-test"})
    def test_qwen36_check_profile_runs_stage1_then_rule_id(self) -> None:
        """Qwen3.6 check profile should run binary detection before Rule ID."""
        backend = _make_backend(
            prompt_profile="qwen36_certfix_check_v1",
            use_nothink_prefill=True,
        )

        stage1_response = MagicMock()
        stage1_response.json.return_value = {
            "content": '{"predictions":[{"id":"S001","label":"violation"}]}'
        }
        stage1_response.raise_for_status = MagicMock()

        rule_response = MagicMock()
        rule_response.json.return_value = {
            "content": '{"predictions":[{"id":"S001","rule_id":"MEM30-C"}]}'
        }
        rule_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.side_effect = [stage1_response, rule_response]
        backend._client = mock_client

        violations = backend.detect('free(p);\nprintf("%s", p);')

        assert len(violations) == 1
        assert violations[0].rule_id == "MEM30-C"
        assert "stage1_balanced_prior" in violations[0].message
        assert mock_client.post.call_count == 2

    @patch.dict("os.environ", {"TEST_API_KEY": "sk-test"})
    def test_qwen36_check_profile_safe_skips_rule_id(self) -> None:
        """Safe Stage 1 result should not call the Rule ID prompt."""
        backend = _make_backend(
            prompt_profile="qwen36_certfix_check_v1",
            use_nothink_prefill=True,
        )

        stage1_response = MagicMock()
        stage1_response.json.return_value = {
            "content": '{"predictions":[{"id":"S001","label":"safe"}]}'
        }
        stage1_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = stage1_response
        backend._client = mock_client

        assert backend.detect("int main(void) { return 0; }") == []
        assert mock_client.post.call_count == 1

    @patch.dict("os.environ", {"TEST_API_KEY": "sk-test"})
    def test_qwen36_batch_profile_runs_batched_stage1_and_rule_id(self) -> None:
        """Batch helper should classify several whole-file items per request."""
        backend = _make_backend(
            prompt_profile="qwen36_certfix_check_v1",
            use_nothink_prefill=True,
        )

        stage1_response = MagicMock()
        stage1_response.json.return_value = {
            "content": (
                '{"predictions":['
                '{"id":"0","label":"violation"},'
                '{"id":"1","label":"safe"}'
                "]}"
            )
        }
        stage1_response.raise_for_status = MagicMock()

        rule_response = MagicMock()
        rule_response.json.return_value = {
            "content": '{"predictions":[{"id":"0","rule_id":"MEM30-C"}]}'
        }
        rule_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.side_effect = [stage1_response, rule_response]
        backend._client = mock_client

        results = backend.detect_qwen36_batch(
            [("0", 'free(p);\nprintf("%s", p);'), ("1", "int main(void) { return 0; }")],
            batch_size=2,
        )

        assert [v.rule_id for v in results["0"]] == ["MEM30-C"]
        assert results["1"] == []
        assert mock_client.post.call_count == 2

    @patch.dict("os.environ", {"TEST_API_KEY": "sk-test"})
    def test_qwen36_batch_rule_id_single_item_accepts_model_id_drift(self) -> None:
        """Single-item Rule ID output may use an example id such as S001."""
        backend = _make_backend(
            prompt_profile="qwen36_certfix_check_v1",
            use_nothink_prefill=True,
        )

        stage1_response = MagicMock()
        stage1_response.json.return_value = {
            "content": '{"predictions":[{"id":"0","label":"violation"}]}'
        }
        stage1_response.raise_for_status = MagicMock()

        rule_response = MagicMock()
        rule_response.json.return_value = {
            "content": '{"predictions":[{"id":"S001","rule_id":"MEM30-C"}]}'
        }
        rule_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.side_effect = [stage1_response, rule_response]
        backend._client = mock_client

        results = backend.detect_qwen36_batch([("0", 'free(p);\nprintf("%s", p);')])

        assert [v.rule_id for v in results["0"]] == ["MEM30-C"]

    @patch.dict("os.environ", {"TEST_API_KEY": "sk-test"})
    def test_qwen36_batch_can_use_sequential_top2_p3_rule_selection(self) -> None:
        """Sequential Rule ID mode should attach Top-2 candidates and selector metadata."""
        backend = _make_backend(
            prompt_profile="qwen36_certfix_check_v1",
            use_nothink_prefill=True,
            qwen36_rule_id_strategy="sequential_top2_p3",
        )

        stage1_response = MagicMock()
        stage1_response.json.return_value = {
            "content": '{"predictions":[{"id":"0","label":"violation"}]}'
        }
        stage1_response.raise_for_status = MagicMock()

        candidate_rules = ["MEM31-C", "MEM30-C"]
        candidate_responses = []
        for rule_id in candidate_rules:
            response = MagicMock()
            response.json.return_value = {"content": f'{{"rule_id":"{rule_id}"}}'}
            response.raise_for_status = MagicMock()
            candidate_responses.append(response)

        selector_responses = []
        for selected in ["MEM30-C", "MEM31-C", "MEM30-C"]:
            response = MagicMock()
            response.json.return_value = {
                "content": (
                    '{"selected_rule":"'
                    + selected
                    + '","ranked_rules":["MEM30-C","MEM31-C"]}'
                )
            }
            response.raise_for_status = MagicMock()
            selector_responses.append(response)

        mock_client = MagicMock()
        mock_client.post.side_effect = [stage1_response, *candidate_responses, *selector_responses]
        backend._client = mock_client

        results = backend.detect_qwen36_batch([("0", 'free(p);\nprintf("%s", p);')])

        violation = results["0"][0]
        assert violation.rule_id == "MEM30-C"
        assert [candidate.rule_id for candidate in violation.candidates or []] == candidate_rules
        assert violation.rule_selection is not None
        assert violation.rule_selection.selected_rule_id == "MEM30-C"
        assert violation.rule_selection.selected_rank == 2
        assert mock_client.post.call_count == 6
        stage1_payload = mock_client.post.call_args_list[0].kwargs["json"]
        assert stage1_payload["n_predict"] == 384
        assert "/no_think" not in stage1_payload["prompt"]
        assert "<think>\n\n</think>" in stage1_payload["prompt"]

    @patch.dict("os.environ", {"TEST_API_KEY": "sk-test"})
    def test_qwen36_sequential_can_route_only_selector_voting(self) -> None:
        """Candidate prompts can stay on detector while p3 selector prompts use an override."""
        selector_backend = MagicMock()
        selector_backend.generate.side_effect = [
            '{"selected_rule":"MEM30-C","ranked_rules":["MEM30-C","MEM31-C"]}',
            '{"selected_rule":"MEM31-C","ranked_rules":["MEM31-C","MEM30-C"]}',
            '{"selected_rule":"MEM30-C","ranked_rules":["MEM30-C","MEM31-C"]}',
        ]
        backend = _make_backend(
            prompt_profile="qwen36_certfix_check_v1",
            use_nothink_prefill=True,
            qwen36_rule_id_strategy="sequential_top2_p3",
            rule_selector_backend=selector_backend,
        )

        stage1_response = MagicMock()
        stage1_response.json.return_value = {
            "content": '{"predictions":[{"id":"0","label":"violation"}]}'
        }
        stage1_response.raise_for_status = MagicMock()

        candidate_responses = []
        for rule_id in ["MEM31-C", "MEM30-C"]:
            response = MagicMock()
            response.json.return_value = {"content": f'{{"rule_id":"{rule_id}"}}'}
            response.raise_for_status = MagicMock()
            candidate_responses.append(response)

        mock_client = MagicMock()
        mock_client.post.side_effect = [stage1_response, *candidate_responses]
        backend._client = mock_client

        results = backend.detect_qwen36_batch([("0", 'free(p);\nprintf("%s", p);')])

        violation = results["0"][0]
        assert violation.rule_id == "MEM30-C"
        assert selector_backend.generate.call_count == 3
        assert mock_client.post.call_count == 3


class TestFix:
    """Tests for fix."""

    @patch.dict("os.environ", {"TEST_API_KEY": "sk-test"})
    def test_fix_returns_code(self) -> None:
        """Should return fixed code."""
        backend = _make_backend()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "int *p = NULL;\nfree(p);\n"}}]
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        backend._client = mock_client

        violation = Violation(
            rule_id="MEM30-C",
            file_path="test.c",
            line=3,
            column=1,
            message="Do not access freed memory",
            severity=Severity.ERROR,
        )
        result = backend.fix("int *p = malloc(10);", violation)
        assert "int *p = NULL;" in result

    @patch.dict("os.environ", {"TEST_API_KEY": "sk-test"})
    def test_fix_strips_code_fences(self) -> None:
        """Should strip markdown code fences from response."""
        backend = _make_backend()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "```c\nint x = 0;\n```"}}]
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        backend._client = mock_client

        violation = Violation(
            rule_id="EXP33-C",
            file_path="test.c",
            line=1,
            column=1,
            message="Do not read uninitialized memory",
            severity=Severity.ERROR,
        )
        result = backend.fix("int x;", violation)
        assert result == "int x = 0;"
        assert "```" not in result


class TestQwen36PatternCues:
    """Tests for code-triggered Rule ID candidate cues."""

    def test_con39_cue_requires_same_join_or_detach_handle_twice(self) -> None:
        cues = _qwen36_rule_id_pattern_cues(
            "void f(pthread_t t) { pthread_join(t, 0); pthread_detach(t); }"
        )

        assert any("CON39-C" in cue for cue in cues)

    def test_con39_cue_ignores_different_handles(self) -> None:
        cues = _qwen36_rule_id_pattern_cues(
            "void f(pthread_t a, pthread_t b) { pthread_join(a, 0); pthread_join(b, 0); }"
        )

        assert not any("CON39-C" in cue for cue in cues)

    def test_msc38_cue_for_address_of_macro_like_identifier(self) -> None:
        cues = _qwen36_rule_id_pattern_cues("void *p = &errno;")

        assert any("MSC38-C" in cue for cue in cues)

    @patch.dict("os.environ", {"TEST_API_KEY": "sk-test"})
    def test_fix_uses_selected_rule_prompt(self) -> None:
        """Rule selection metadata should be included in API fix prompts."""
        backend = _make_backend()

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "```c\np = NULL;\n```"}}]
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        backend._client = mock_client

        violation = Violation(
            rule_id="MEM30-C",
            file_path="test.c",
            line=3,
            column=1,
            message="candidate",
            severity=Severity.ERROR,
            candidates=[RuleCandidate("MEM30-C", 1, "Use after free")],
            rule_selection=RuleSelectionResult(
                decision=RuleSelectionDecision.APPLY_RULE,
                selected_rule_id="MEM30-C",
                selected_rank=1,
                evidence="p is used after free",
            ),
        )

        result = backend.fix('free(p);\nprintf("%s", p);', violation)

        payload = mock_client.post.call_args.kwargs["json"]
        prompt = payload["messages"][0]["content"]
        assert "Target rule:\nMEM30-C" in prompt
        assert "Rule selection evidence:\np is used after free" in prompt
        assert result == "p = NULL;"


class TestChatCompletion:
    """Tests for _chat_completion."""

    @patch.dict("os.environ", {"TEST_API_KEY": "sk-test"})
    def test_successful_request(self) -> None:
        """Should return content from API response."""
        backend = _make_backend()

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "test response"}}]}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        backend._client = mock_client

        result = backend._chat_completion("test prompt")
        assert result == "test response"

        # Verify request was made correctly
        call_kwargs = mock_client.post.call_args
        assert "chat/completions" in call_kwargs[0][0]
        payload = call_kwargs[1]["json"]
        assert payload["model"] == "test-model"
        assert payload["messages"][0]["content"] == "test prompt"

    @patch.dict("os.environ", {"TEST_API_KEY": "sk-test"})
    def test_api_error(self) -> None:
        """Should raise InferenceError on API error."""
        import httpx

        backend = _make_backend()

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        error = httpx.HTTPStatusError("Server Error", request=MagicMock(), response=mock_response)
        mock_response.raise_for_status.side_effect = error

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        backend._client = mock_client

        with pytest.raises(InferenceError, match="API request failed"):
            backend._chat_completion("test")

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_api_key(self) -> None:
        """Should raise ConfigError when API key is not set."""
        backend = _make_backend(api_key_env="NONEXISTENT_KEY")

        with pytest.raises(ConfigError, match="API key not set"):
            backend._chat_completion("test")

    @patch.dict("os.environ", {}, clear=True)
    def test_empty_api_key_env_omits_authorization_header(self) -> None:
        """Local llama.cpp-compatible servers should not require a key."""
        backend = _make_backend(api_key_env="")

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        backend._client = mock_client

        result = backend._chat_completion("test")

        headers = mock_client.post.call_args.kwargs["headers"]
        assert result == "ok"
        assert "Authorization" not in headers


class TestStripCodeFences:
    """Tests for _strip_code_fences."""

    def test_strip_c_fence(self) -> None:
        assert ApiBackend._strip_code_fences("```c\nint x;\n```") == "int x;"

    def test_strip_plain_fence(self) -> None:
        assert ApiBackend._strip_code_fences("```\nint x;\n```") == "int x;"

    def test_no_fences(self) -> None:
        assert ApiBackend._strip_code_fences("int x;") == "int x;"
