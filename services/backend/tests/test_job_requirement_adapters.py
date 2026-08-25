"""Provider-adapter tests for Job Requirement Extraction."""
from __future__ import annotations

import json

import httpx
import pytest

from app.application.job_requirements import (
    RequirementExtractorFailedError,
    RequirementExtractorUnavailableError,
)
from app.llm import OpenAIJobRequirementExtractor


def test_openai_requirement_adapter_uses_strict_schema_and_no_storage() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        output = {
            "requirements": [
                {
                    "type": "skill",
                    "originalText": "熟练掌握 Python 和 FastAPI",
                    "normalizedCapability": "Python",
                    "importance": "must_have",
                    "sourceCandidateId": "S0001",
                    "confidence": 0.95,
                }
            ]
        }
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": json.dumps(output)}
                        ],
                    }
                ],
                "usage": {"input_tokens": 100, "output_tokens": 40},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = OpenAIJobRequirementExtractor(
            api_key="test-key",
            model="test-model",
            base_url="https://example.test/v1",
            client=client,
        ).extract("岗位要求：熟练掌握 Python 和 FastAPI，并具备后端系统设计经验。")

    assert captured["model"] == "test-model"
    assert captured["store"] is False
    assert captured["text"]["format"]["type"] == "json_schema"
    assert captured["text"]["format"]["strict"] is True
    assert captured["text"]["format"]["schema"]["additionalProperties"] is False
    assert result.output.requirements[0].normalized_capability == "Python"
    assert result.input_tokens == 100
    assert result.output_tokens == 40


def test_openai_requirement_adapter_allows_raw_buffer_above_final_requirement_limit() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        output = {
            "requirements": [
                {
                    "type": "responsibility",
                    "originalText": "负责核心系统设计",
                    "normalizedCapability": None,
                    "importance": "must_have",
                    "sourceCandidateId": "S0001",
                    "confidence": 0.95,
                }
                for _ in range(51)
            ]
        }
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(output),
                        }
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = OpenAIJobRequirementExtractor(
            api_key="test-key",
            model="test-model",
            base_url="https://example.test/v1",
            api_style="chat_completions",
            client=client,
        ).extract("负责核心系统设计，并参与测试、上线与复盘。")

    schema = captured["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["requirements"]["maxItems"] == 64
    assert len(result.output.requirements) == 51


def test_openai_requirement_adapter_normalizes_blank_non_skill_capability_to_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        output = {
            "requirements": [
                {
                    "type": "responsibility",
                    "originalText": "至少要能独立 owner 一个核心方向",
                    "normalizedCapability": "   ",
                    "importance": "must_have",
                    "sourceCandidateId": "S0001",
                    "confidence": 0.95,
                }
            ]
        }
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(output),
                        }
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = OpenAIJobRequirementExtractor(
            api_key="test-key",
            model="test-model",
            base_url="https://example.test/v1",
            api_style="chat_completions",
            client=client,
        ).extract("至少要能独立 owner 一个核心方向")

    assert result.output.requirements[0].normalized_capability is None


def test_openai_requirement_adapter_prompt_preserves_requirement_importance_scope() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        output = {
            "requirements": [
                {
                    "type": "education",
                    "originalText": "本科及以上学历",
                    "normalizedCapability": None,
                    "importance": "must_have",
                    "sourceCandidateId": "S0001",
                    "confidence": 0.95,
                }
            ]
        }
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(output),
                        }
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        OpenAIJobRequirementExtractor(
            api_key="test-key",
            model="test-model",
            base_url="https://example.test/v1",
            api_style="chat_completions",
            client=client,
        ).extract("任职要求：本科及以上学历，计算机相关专业优先。")

    prompt = captured["messages"][0]["content"]
    assert "requirements/qualifications section" in prompt
    assert "default to must_have" in prompt
    assert "applies only to the clause it modifies" in prompt
    assert "split them into separate requirements" in prompt
    assert "at least N" in prompt
    assert "must not make every child independently must_have" in prompt
    assert "waiver or exception" in prompt
    assert "可放宽" in prompt
    assert "examples such as" in prompt
    assert "must not become independent must_have requirements" in prompt
    assert "responsibilities/duties/work content and qualifications/requirements" in prompt
    assert "Responsibilities are first-class JobRequirements" in prompt
    assert "preserve each materially distinct explicit duty" in prompt
    assert "do not relabel a duty as `skill`" in prompt


def test_openai_requirement_adapter_uses_flat_provider_schema_and_keeps_backend_skill_validation() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        output = {
            "requirements": [
                {
                    "type": "skill",
                    "originalText": "熟练掌握 Python",
                    "normalizedCapability": "Python",
                    "importance": "must_have",
                    "sourceCandidateId": "S0001",
                    "confidence": 0.95,
                }
            ]
        }
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(output),
                        }
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        OpenAIJobRequirementExtractor(
            api_key="test-key",
            model="test-model",
            base_url="https://example.test/v1",
            api_style="chat_completions",
            client=client,
        ).extract("岗位要求：熟练掌握 Python。")

    schema = captured["response_format"]["json_schema"]["schema"]
    skill_schema = schema["$defs"]["_SkillRequirementOutput"]
    other_schema = schema["$defs"]["_OtherRequirementOutput"]
    assert "oneOf" in json.dumps(schema)
    assert "discriminator" in json.dumps(schema)
    assert skill_schema["properties"]["type"]["const"] == "skill"
    assert skill_schema["properties"]["normalizedCapability"]["type"] == "string"
    assert skill_schema["properties"]["normalizedCapability"]["minLength"] == 1
    assert "sourceCandidateId" in skill_schema["required"]
    assert "sourceCandidateId" in other_schema["required"]
    assert "evidenceSpan" not in skill_schema["properties"]
    assert "evidenceSpan" not in other_schema["properties"]
    assert {item.get("type") for item in other_schema["properties"]["normalizedCapability"]["anyOf"]} == {"string", "null"}


def test_openai_requirement_adapter_rejects_skill_without_normalized_capability() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        output = {
            "requirements": [
                {
                    "type": "skill",
                    "originalText": "具备业务理解能力",
                    "normalizedCapability": None,
                    "importance": "preferred",
                    "sourceCandidateId": "S0001",
                    "confidence": 0.9,
                }
            ]
        }
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(output),
                        }
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        extractor = OpenAIJobRequirementExtractor(
            api_key="test-key",
            model="test-model",
            base_url="https://example.test/v1",
            api_style="chat_completions",
            client=client,
        )
        with pytest.raises(RequirementExtractorFailedError) as exc_info:
            extractor.extract("岗位要求：具备业务理解能力。")

    message = str(exc_info.value)
    assert "ValidationError" in message
    assert exc_info.value.failure_stage == "structured_output_validation"
    assert "failureStage=structured_output_validation" in message
    assert "requirements.0.skill.normalizedCapability:string_type" in message
    assert "具备业务理解能力" not in message


def test_openai_requirement_adapter_classifies_invalid_structured_output_json() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "not-json",
                        },
                        "finish_reason": "length",
                    }
                ],
                "usage": {"prompt_tokens": 321, "completion_tokens": 2048},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        extractor = OpenAIJobRequirementExtractor(
            api_key="test-key",
            model="test-model",
            base_url="https://example.test/v1",
            api_style="chat_completions",
            max_completion_tokens=2048,
            client=client,
        )
        with pytest.raises(RequirementExtractorFailedError) as exc_info:
            extractor.extract("岗位要求：具备业务理解能力。")

    message = str(exc_info.value)
    assert "ValidationError" in message
    assert exc_info.value.failure_stage == "structured_output_json"
    assert exc_info.value.input_tokens == 321
    assert exc_info.value.output_tokens == 2048
    assert exc_info.value.provider_finish_reason == "length"
    assert exc_info.value.output_chars == len("not-json")
    assert exc_info.value.requested_max_completion_tokens == 2048
    assert "failureStage=structured_output_json" in message
    assert "json_invalid" in message
    assert "finishReason=length" in message
    assert "inputTokens=321" in message
    assert "outputTokens=2048" in message
    assert "outputChars=8" in message
    assert "requestedMaxCompletionTokens=2048" in message
    assert "not-json" not in message


def test_openai_requirement_adapter_classifies_provider_response_shape_failure() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        extractor = OpenAIJobRequirementExtractor(
            api_key="test-key",
            model="test-model",
            base_url="https://example.test/v1",
            api_style="chat_completions",
            client=client,
        )
        with pytest.raises(RequirementExtractorFailedError) as exc_info:
            extractor.extract("岗位要求：具备业务理解能力。")

    message = str(exc_info.value)
    assert "ProviderOutputError" in message
    assert exc_info.value.failure_stage == "provider_response_shape"
    assert "failureStage=provider_response_shape" in message
    assert "reason=missing_choices" in message


def test_openai_requirement_adapter_supports_chat_completions_strict_schema() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured.update(json.loads(request.content))
        output = {
            "requirements": [
                {
                    "type": "skill",
                    "originalText": "熟练掌握 Python 和 FastAPI",
                    "normalizedCapability": "Python",
                    "importance": "must_have",
                    "sourceCandidateId": "S0001",
                    "confidence": 0.95,
                }
            ]
        }
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(output),
                        }
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 40},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = OpenAIJobRequirementExtractor(
            api_key="test-key",
            model="test-model",
            base_url="https://example.test/v1",
            api_style="chat_completions",
            enable_thinking=False,
            max_completion_tokens=8192,
            client=client,
        ).extract("岗位要求：熟练掌握 Python 和 FastAPI，并具备后端系统设计经验。")

    assert captured["url"] == "https://example.test/v1/chat/completions"
    assert captured["model"] == "test-model"
    assert captured["messages"][0]["role"] == "system"
    assert captured["messages"][1]["role"] == "user"
    assert captured["stream"] is False
    assert captured["enable_thinking"] is False
    assert captured["max_completion_tokens"] == 8192
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["response_format"]["json_schema"]["strict"] is True
    assert (
        captured["response_format"]["json_schema"]["schema"]["additionalProperties"]
        is False
    )
    assert "store" not in captured
    assert result.output.requirements[0].normalized_capability == "Python"
    assert result.input_tokens == 100
    assert result.output_tokens == 40


def test_openai_requirement_adapter_maps_source_candidate_to_raw_evidence() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        output = {
            "requirements": [
                {
                    "type": "experience",
                    "originalText": "2 年以上后端开发经验",
                    "normalizedCapability": None,
                    "importance": "must_have",
                    "sourceCandidateId": "S0002",
                    "confidence": 0.95,
                }
            ]
        }
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(output),
                        }
                    }
                ]
            },
        )

    description = "任职要求\n2 年以上后端开发经验，熟悉 Python"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = OpenAIJobRequirementExtractor(
            api_key="test-key",
            model="test-model",
            base_url="https://example.test/v1",
            api_style="chat_completions",
            client=client,
        ).extract(description)

    user_input = captured["messages"][1]["content"]
    assert "JOB DESCRIPTION" in user_input
    assert description in user_input
    assert "SOURCE CANDIDATES" in user_input
    assert "[S0001] 任职要求" in user_input
    assert "[S0002] 2 年以上后端开发经验，熟悉 Python" in user_input
    assert result.output.requirements[0].evidence_span == "2 年以上后端开发经验，熟悉 Python"
    assert result.output.requirements[0].evidence_span in description


def test_openai_requirement_adapter_rejects_unknown_source_candidate_id() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        output = {
            "requirements": [
                {
                    "type": "experience",
                    "originalText": "2 年以上后端开发经验",
                    "normalizedCapability": None,
                    "importance": "must_have",
                    "sourceCandidateId": "S9999",
                    "confidence": 0.95,
                }
            ]
        }
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(output),
                        }
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        extractor = OpenAIJobRequirementExtractor(
            api_key="test-key",
            model="test-model",
            base_url="https://example.test/v1",
            api_style="chat_completions",
            client=client,
        )
        with pytest.raises(
            RequirementExtractorFailedError,
            match="unknown sourceCandidateId: S9999",
        ):
            extractor.extract("任职要求\n2 年以上后端开发经验")


@pytest.mark.parametrize("status_code", [429, 503, 504])
def test_openai_requirement_adapter_classifies_transient_provider_outage_as_unavailable(
    status_code: int,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            headers={"x-trace-id": "trace_gateway_123"},
            json={"error": {"message": "temporary upstream outage"}},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        extractor = OpenAIJobRequirementExtractor(
            api_key="test-key",
            model="test-model",
            api_style="chat_completions",
            client=client,
        )
        with pytest.raises(
            RequirementExtractorUnavailableError,
            match=rf"HTTPStatusError\(status={status_code}, traceId=trace_gateway_123\)",
        ) as captured:
            extractor.extract(
                "岗位要求熟练掌握 Python 和 FastAPI，并具备后端开发经验。"
            )

    assert captured.value.status_code == status_code


def test_openai_requirement_adapter_retries_transient_outage_with_exponential_backoff() -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503, json={"error": {"message": "busy"}})
        output = {
            "requirements": [
                {
                    "type": "skill",
                    "originalText": "熟练掌握 Python",
                    "normalizedCapability": "Python",
                    "importance": "must_have",
                    "sourceCandidateId": "S0001",
                    "confidence": 0.95,
                }
            ]
        }
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": json.dumps(output)}}
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = OpenAIJobRequirementExtractor(
            api_key="test-key",
            model="test-model",
            api_style="chat_completions",
            client=client,
            retry_max_attempts=3,
            retry_backoff_seconds=0.25,
            sleep_fn=sleeps.append,
        ).extract("熟练掌握 Python")

    assert attempts == 3
    assert sleeps == [0.25, 0.5]
    assert result.output.requirements[0].normalized_capability == "Python"


def test_openai_requirement_adapter_retries_transport_timeout_as_unavailable() -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadTimeout("upstream timeout")
        output = {
            "requirements": [
                {
                    "type": "skill",
                    "originalText": "熟练掌握 Python",
                    "normalizedCapability": "Python",
                    "importance": "must_have",
                    "sourceCandidateId": "S0001",
                    "confidence": 0.95,
                }
            ]
        }
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": json.dumps(output)}}
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = OpenAIJobRequirementExtractor(
            api_key="test-key",
            model="test-model",
            api_style="chat_completions",
            client=client,
            retry_max_attempts=2,
            retry_backoff_seconds=0.1,
            sleep_fn=sleeps.append,
        ).extract("熟练掌握 Python")

    assert attempts == 2
    assert sleeps == [0.1]
    assert result.output.requirements[0].normalized_capability == "Python"


def test_openai_requirement_adapter_keeps_non_transient_http_error_as_failure() -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(500, json={"error": {"message": "internal error"}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        extractor = OpenAIJobRequirementExtractor(
            api_key="test-key",
            model="test-model",
            api_style="chat_completions",
            client=client,
            retry_max_attempts=3,
            retry_backoff_seconds=0.25,
            sleep_fn=sleeps.append,
        )
        with pytest.raises(
            RequirementExtractorFailedError,
            match=r"HTTPStatusError\(status=500\)",
        ):
            extractor.extract(
                "岗位要求熟练掌握 Python 和 FastAPI，并具备后端开发经验。"
            )

    assert attempts == 1
    assert sleeps == []


def test_openai_requirement_adapter_opens_circuit_after_repeated_transient_failures() -> None:
    attempts = 0
    now = 100.0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, json={"error": {"message": "busy"}})

    def monotonic() -> float:
        return now

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        extractor = OpenAIJobRequirementExtractor(
            api_key="test-key",
            model="test-model",
            api_style="chat_completions",
            client=client,
            circuit_failure_threshold=2,
            circuit_cooldown_seconds=30.0,
            monotonic_fn=monotonic,
        )

        for _ in range(2):
            with pytest.raises(RequirementExtractorUnavailableError):
                extractor.extract("熟练掌握 Python")

        with pytest.raises(
            RequirementExtractorUnavailableError,
            match="circuit is open",
        ):
            extractor.extract("熟练掌握 Python")

    assert attempts == 2


def test_openai_requirement_adapter_half_open_probe_resets_circuit_after_success() -> None:
    attempts = 0
    now = 100.0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts <= 2:
            return httpx.Response(503, json={"error": {"message": "busy"}})
        output = {
            "requirements": [
                {
                    "type": "skill",
                    "originalText": "熟练掌握 Python",
                    "normalizedCapability": "Python",
                    "importance": "must_have",
                    "sourceCandidateId": "S0001",
                    "confidence": 0.95,
                }
            ]
        }
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": json.dumps(output)}}
                ]
            },
        )

    def monotonic() -> float:
        return now

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        extractor = OpenAIJobRequirementExtractor(
            api_key="test-key",
            model="test-model",
            api_style="chat_completions",
            client=client,
            circuit_failure_threshold=2,
            circuit_cooldown_seconds=30.0,
            monotonic_fn=monotonic,
        )

        for _ in range(2):
            with pytest.raises(RequirementExtractorUnavailableError):
                extractor.extract("熟练掌握 Python")

        now = 131.0
        result = extractor.extract("熟练掌握 Python")
        result_again = extractor.extract("熟练掌握 Python")

    assert attempts == 4
    assert result.output.requirements[0].normalized_capability == "Python"
    assert result_again.output.requirements[0].normalized_capability == "Python"


def test_openai_requirement_adapter_non_transient_failure_does_not_trip_circuit() -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(500, json={"error": {"message": "internal error"}})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        extractor = OpenAIJobRequirementExtractor(
            api_key="test-key",
            model="test-model",
            api_style="chat_completions",
            client=client,
            circuit_failure_threshold=1,
            circuit_cooldown_seconds=30.0,
        )
        for _ in range(2):
            with pytest.raises(RequirementExtractorFailedError):
                extractor.extract("熟练掌握 Python")

    assert attempts == 2


def test_openai_requirement_adapter_requires_configuration() -> None:
    extractor = OpenAIJobRequirementExtractor(api_key=None, model="")

    with pytest.raises(RequirementExtractorUnavailableError):
        extractor.extract("岗位要求熟练掌握 Python 和 FastAPI，并具备后端开发经验。")


def test_openai_requirement_adapter_maps_refusal() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "refusal", "refusal": "cannot comply"}
                        ],
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        extractor = OpenAIJobRequirementExtractor(
            api_key="test-key",
            model="test-model",
            client=client,
        )
        with pytest.raises(RequirementExtractorFailedError, match="refused"):
            extractor.extract(
                "岗位要求熟练掌握 Python 和 FastAPI，并具备后端开发经验。"
            )
