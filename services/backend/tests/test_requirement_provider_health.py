"""Requirement Provider health-gate tests."""
from __future__ import annotations

from collections import deque

import httpx

from app.core.config import Settings
from scripts.check_requirement_provider_health import check_requirement_provider_health


class StubClient:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = deque(responses)
        self.calls: list[tuple[str, dict[str, object]]] = []

    def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]):
        self.calls.append((url, json))
        return self.responses.popleft()


def _settings(**overrides: object) -> Settings:
    payload: dict[str, object] = {
        "requirement_extractor_provider": "openai",
        "requirement_extractor_model": "deepseek-v4-flash",
        "requirement_extractor_api_style": "chat_completions",
        "requirement_extractor_enable_thinking": False,
        "requirement_extractor_timeout_seconds": 60.0,
        "openai_api_key": "test-key",
        "openai_base_url": "https://provider.example/v1",
    }
    payload.update(overrides)
    return Settings(**payload)


def _chat_response(
    status: int,
    *,
    content: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    trace_id: str | None = None,
) -> httpx.Response:
    request = httpx.Request("POST", "https://provider.example/v1/chat/completions")
    if status == 200:
        payload = {
            "choices": [
                {
                    "message": {
                        "content": content,
                    }
                }
            ]
        }
    else:
        payload = {
            "code": error_code,
            "message": error_message,
            "traceId": trace_id,
        }
    return httpx.Response(status, json=payload, request=request)


def test_health_gate_is_zero_call_by_default() -> None:
    client = StubClient([])

    result = check_requirement_provider_health(
        settings=_settings(),
        execute_health_probe=False,
        confirm_live_cost=False,
        client=client,  # type: ignore[arg-type]
    )

    assert result.state == "ready_for_explicit_execution"
    assert result.provider_calls == 0
    assert result.ready_for_requirement_live_run is False
    assert client.calls == []


def test_health_gate_requires_explicit_live_cost_confirmation() -> None:
    client = StubClient([])

    result = check_requirement_provider_health(
        settings=_settings(),
        execute_health_probe=True,
        confirm_live_cost=False,
        client=client,  # type: ignore[arg-type]
    )

    assert result.state == "blocked"
    assert result.blocker == "live_cost_confirmation_required"
    assert result.provider_calls == 0
    assert client.calls == []


def test_plain_failure_stops_before_structured_probe() -> None:
    client = StubClient(
        [
            _chat_response(
                503,
                error_code="SERVICE_BUSY",
                error_message="服务繁忙，请稍后重试",
                trace_id="trace_busy",
            )
        ]
    )

    result = check_requirement_provider_health(
        settings=_settings(),
        execute_health_probe=True,
        confirm_live_cost=True,
        client=client,  # type: ignore[arg-type]
    )

    assert result.state == "unhealthy"
    assert result.blocker == "plain_probe_failed"
    assert result.provider_calls == 1
    assert result.plain_probe.status_code == 503
    assert result.plain_probe.error_code == "SERVICE_BUSY"
    assert result.plain_probe.trace_id == "trace_busy"
    assert result.structured_probe.attempted is False
    assert len(client.calls) == 1


def test_structured_failure_blocks_live_run_after_plain_success() -> None:
    client = StubClient(
        [
            _chat_response(200, content="OK"),
            _chat_response(
                503,
                error_code="SERVICE_BUSY",
                error_message="服务繁忙，请稍后重试",
                trace_id="trace_structured_busy",
            ),
        ]
    )

    result = check_requirement_provider_health(
        settings=_settings(),
        execute_health_probe=True,
        confirm_live_cost=True,
        client=client,  # type: ignore[arg-type]
    )

    assert result.state == "unhealthy"
    assert result.blocker == "structured_probe_failed"
    assert result.provider_calls == 2
    assert result.plain_probe.healthy is True
    assert result.structured_probe.status_code == 503
    assert result.structured_probe.error_code == "SERVICE_BUSY"
    assert result.ready_for_requirement_live_run is False
    assert len(client.calls) == 2
    assert "response_format" not in client.calls[0][1]
    assert "response_format" in client.calls[1][1]


def test_double_success_opens_requirement_live_gate() -> None:
    client = StubClient(
        [
            _chat_response(200, content="OK"),
            _chat_response(200, content='{"ok":true}'),
        ]
    )

    result = check_requirement_provider_health(
        settings=_settings(),
        execute_health_probe=True,
        confirm_live_cost=True,
        client=client,  # type: ignore[arg-type]
    )

    assert result.state == "healthy"
    assert result.blocker is None
    assert result.provider_calls == 2
    assert result.plain_probe.healthy is True
    assert result.structured_probe.healthy is True
    assert result.ready_for_requirement_live_run is True


def test_invalid_provider_configuration_is_blocked_without_calls() -> None:
    client = StubClient([])

    result = check_requirement_provider_health(
        settings=_settings(requirement_extractor_provider="fixture"),
        execute_health_probe=True,
        confirm_live_cost=True,
        client=client,  # type: ignore[arg-type]
    )

    assert result.state == "blocked"
    assert result.blocker == "requirement_provider_must_be_openai"
    assert result.provider_calls == 0
    assert client.calls == []
