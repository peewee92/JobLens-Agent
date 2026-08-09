"""Provider-adapter tests for Semantic Match."""
from __future__ import annotations

import json

import httpx
import pytest

from app.application.evidence_retrieval import EvidenceRelevanceTier, EvidenceRetrievalBasis
from app.application.semantic_match import (
    SemanticCandidateInput,
    SemanticMatcherFailedError,
    SemanticMatcherUnavailableError,
    SemanticMatchVerdict,
    SemanticRequirementInput,
)
from app.domain.career_context import EvidenceType
from app.core.config import Settings
from app.domain.job_requirements import RequirementImportance, RequirementType
from app.llm.semantic_matcher_factory import build_semantic_matcher
from app.llm.semantic_matchers import (
    DisabledSemanticMatcher,
    OpenAISemanticMatcher,
)


def _requirements() -> tuple[SemanticRequirementInput, ...]:
    return (
        SemanticRequirementInput(
            requirement_id="req_mcp",
            requirement_index=0,
            type=RequirementType.SKILL,
            importance=RequirementImportance.MUST_HAVE,
            original_text="熟悉 MCP 协议",
            normalized_capability="MCP",
            candidates=(
                SemanticCandidateInput(
                    evidence_id="ev_tools",
                    evidence_type=EvidenceType.PROJECT,
                    summary="实现 Agent Function Calling、工具调用和工具集成。",
                    relevance_tier=EvidenceRelevanceTier.RELATED,
                    retrieval_basis=EvidenceRetrievalBasis.RELATED_CAPABILITY_HINT,
                ),
            ),
        ),
    )


def test_semantic_matcher_factory_defaults_disabled_and_requires_explicit_openai() -> None:
    assert isinstance(
        build_semantic_matcher(Settings(_env_file=None)), DisabledSemanticMatcher
    )
    configured = build_semantic_matcher(
        Settings(
            _env_file=None,
            semantic_match_provider="openai",
            semantic_match_model="test-model",
            openai_api_key="test-key",
        )
    )
    assert isinstance(configured, OpenAISemanticMatcher)
    assert configured.model_name == "test-model"


def test_openai_semantic_matcher_uses_strict_chat_schema_without_overall_eligibility() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured.update(json.loads(request.content))
        output = {
            "assessments": [
                {
                    "requirementId": "req_mcp",
                    "verdict": "partial",
                    "evidenceIds": ["ev_tools"],
                    "reason": "工具调用经历相关，但不能证明已经具备 MCP 经验。",
                }
            ]
        }
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": json.dumps(output)}}
                ],
                "usage": {"prompt_tokens": 120, "completion_tokens": 35},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = OpenAISemanticMatcher(
            api_key="test-key",
            model="test-model",
            base_url="https://example.test/v1",
            api_style="chat_completions",
            enable_thinking=False,
            max_completion_tokens=4096,
            client=client,
        ).match(_requirements())

    assert captured["url"] == "https://example.test/v1/chat/completions"
    assert captured["stream"] is False
    assert captured["enable_thinking"] is False
    assert captured["max_completion_tokens"] == 4096
    assert captured["response_format"]["type"] == "json_schema"
    schema = captured["response_format"]["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert "eligibility" not in json.dumps(schema).casefold()
    assert "recommendation" not in json.dumps(schema).casefold()
    system_prompt = captured["messages"][0]["content"]
    assert "related" in system_prompt
    assert "matched" in system_prompt
    assert "Requirement: 熟悉 MCP 协议" in system_prompt
    assert "Evidence: 实现 Agent Function Calling、工具调用和工具集成" in system_prompt
    assert "Verdict: partial" in system_prompt
    assert "Requirement: 熟悉 FastAPI" in system_prompt
    assert "Evidence: 使用 Python 开发 REST API 服务，但没有明确使用 FastAPI" in system_prompt
    assert "Requirement: 熟悉 MCP 协议" in system_prompt
    assert "Evidence: 使用 React 开发 AI 聊天界面" in system_prompt
    assert "Verdict: not_matched" in system_prompt
    assert "related-only Evidence can never justify matched" in system_prompt
    user_payload = json.loads(captured["messages"][1]["content"])
    assert user_payload["requirements"][0]["candidates"][0]["evidenceId"] == "ev_tools"
    assert result.output.assessments[0].verdict is SemanticMatchVerdict.PARTIAL
    assert result.input_tokens == 120
    assert result.output_tokens == 35


def test_openai_semantic_matcher_requires_configuration() -> None:
    matcher = OpenAISemanticMatcher(api_key=None, model="")
    with pytest.raises(SemanticMatcherUnavailableError):
        matcher.match(_requirements())


def test_openai_semantic_matcher_maps_invalid_json_to_provider_failure() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "not-json"}}]},
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        matcher = OpenAISemanticMatcher(
            api_key="test-key",
            model="test-model",
            api_style="chat_completions",
            client=client,
        )
        with pytest.raises(SemanticMatcherFailedError, match="ValidationError|json"):
            matcher.match(_requirements())
