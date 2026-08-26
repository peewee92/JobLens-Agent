"""Check whether the configured Requirement provider is healthy enough for live Eval.

The command is zero-call by default. Live probing requires both
`--execute-health-probe` and `--confirm-live-cost`. A live check performs at most
two tiny requests: a plain generation probe, followed by the structured-output
probe only when the plain probe succeeds.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import time
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.evals.provider_smoke import (
    DEFAULT_PROVIDER_SMOKE_SNAPSHOT,
    ProviderSmokeSnapshot,
    save_provider_smoke_snapshot,
)


@dataclass(frozen=True)
class ProviderProbeResult:
    name: str
    attempted: bool
    healthy: bool
    status_code: int | None = None
    latency_ms: int | None = None
    trace_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class RequirementProviderHealthResult:
    state: str
    provider: str
    model: str
    api_style: str
    base_url: str
    api_key_configured: bool
    execution_requested: bool
    live_cost_confirmed: bool
    provider_calls: int
    plain_probe: ProviderProbeResult
    structured_probe: ProviderProbeResult
    ready_for_requirement_live_run: bool
    blocker: str | None = None


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute-health-probe",
        action="store_true",
        help="Perform the live Provider health requests.",
    )
    parser.add_argument(
        "--confirm-live-cost",
        action="store_true",
        help="Acknowledge that the health probe performs up to two billed Provider calls.",
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def check_requirement_provider_health(
    *,
    settings: Settings,
    execute_health_probe: bool,
    confirm_live_cost: bool,
    client: httpx.Client | None = None,
) -> RequirementProviderHealthResult:
    provider = settings.requirement_extractor_provider.strip().casefold() or "disabled"
    model = settings.requirement_extractor_model.strip()
    api_style = settings.requirement_extractor_api_style.strip().casefold()
    base_url = settings.openai_base_url.rstrip("/")
    api_key = settings.openai_api_key.strip() if settings.openai_api_key else ""

    skipped_plain = _skipped_probe("plain")
    skipped_structured = _skipped_probe("json_schema")

    blocker = _configuration_blocker(
        provider=provider,
        model=model,
        api_style=api_style,
        api_key=api_key,
    )
    if blocker is not None:
        return RequirementProviderHealthResult(
            state="blocked",
            provider=provider,
            model=model,
            api_style=api_style,
            base_url=base_url,
            api_key_configured=bool(api_key),
            execution_requested=execute_health_probe,
            live_cost_confirmed=confirm_live_cost,
            provider_calls=0,
            plain_probe=skipped_plain,
            structured_probe=skipped_structured,
            ready_for_requirement_live_run=False,
            blocker=blocker,
        )

    if not execute_health_probe:
        return RequirementProviderHealthResult(
            state="ready_for_explicit_execution",
            provider=provider,
            model=model,
            api_style=api_style,
            base_url=base_url,
            api_key_configured=True,
            execution_requested=False,
            live_cost_confirmed=confirm_live_cost,
            provider_calls=0,
            plain_probe=skipped_plain,
            structured_probe=skipped_structured,
            ready_for_requirement_live_run=False,
        )

    if not confirm_live_cost:
        return RequirementProviderHealthResult(
            state="blocked",
            provider=provider,
            model=model,
            api_style=api_style,
            base_url=base_url,
            api_key_configured=True,
            execution_requested=True,
            live_cost_confirmed=False,
            provider_calls=0,
            plain_probe=skipped_plain,
            structured_probe=skipped_structured,
            ready_for_requirement_live_run=False,
            blocker="live_cost_confirmation_required",
        )

    owns_client = client is None
    active_client = client or httpx.Client(
        timeout=settings.requirement_extractor_timeout_seconds
    )
    provider_calls = 0
    try:
        plain_probe = _run_probe(
            client=active_client,
            base_url=base_url,
            api_key=api_key,
            api_style=api_style,
            model=model,
            enable_thinking=settings.requirement_extractor_enable_thinking,
            structured=False,
        )
        provider_calls += 1
        if not plain_probe.healthy:
            return RequirementProviderHealthResult(
                state="unhealthy",
                provider=provider,
                model=model,
                api_style=api_style,
                base_url=base_url,
                api_key_configured=True,
                execution_requested=True,
                live_cost_confirmed=True,
                provider_calls=provider_calls,
                plain_probe=plain_probe,
                structured_probe=skipped_structured,
                ready_for_requirement_live_run=False,
                blocker="plain_probe_failed",
            )

        structured_probe = _run_probe(
            client=active_client,
            base_url=base_url,
            api_key=api_key,
            api_style=api_style,
            model=model,
            enable_thinking=settings.requirement_extractor_enable_thinking,
            structured=True,
        )
        provider_calls += 1
        ready = structured_probe.healthy
        return RequirementProviderHealthResult(
            state="healthy" if ready else "unhealthy",
            provider=provider,
            model=model,
            api_style=api_style,
            base_url=base_url,
            api_key_configured=True,
            execution_requested=True,
            live_cost_confirmed=True,
            provider_calls=provider_calls,
            plain_probe=plain_probe,
            structured_probe=structured_probe,
            ready_for_requirement_live_run=ready,
            blocker=None if ready else "structured_probe_failed",
        )
    finally:
        if owns_client:
            active_client.close()


def _configuration_blocker(
    *,
    provider: str,
    model: str,
    api_style: str,
    api_key: str,
) -> str | None:
    if provider != "openai":
        return "requirement_provider_must_be_openai"
    if not model:
        return "requirement_model_missing"
    if not api_key:
        return "openai_api_key_missing"
    if api_style not in {"chat_completions", "responses"}:
        return "unsupported_requirement_api_style"
    return None


def _skipped_probe(name: str) -> ProviderProbeResult:
    return ProviderProbeResult(name=name, attempted=False, healthy=False)


def _run_probe(
    *,
    client: httpx.Client,
    base_url: str,
    api_key: str,
    api_style: str,
    model: str,
    enable_thinking: bool | None,
    structured: bool,
) -> ProviderProbeResult:
    name = "json_schema" if structured else "plain"
    request_url, request_body = _probe_request(
        base_url=base_url,
        api_style=api_style,
        model=model,
        enable_thinking=enable_thinking,
        structured=structured,
    )
    started = time.perf_counter()
    try:
        response = client.post(
            request_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=request_body,
        )
    except httpx.HTTPError as error:
        return ProviderProbeResult(
            name=name,
            attempted=True,
            healthy=False,
            latency_ms=_latency_ms(started),
            error_code=type(error).__name__,
            error_message=str(error)[:200],
        )

    trace_id = _response_trace_id(response)
    if response.status_code != 200:
        error_code, error_message = _safe_provider_error(response)
        return ProviderProbeResult(
            name=name,
            attempted=True,
            healthy=False,
            status_code=response.status_code,
            latency_ms=_latency_ms(started),
            trace_id=trace_id,
            error_code=error_code,
            error_message=error_message,
        )

    try:
        payload = response.json()
        content = _probe_output_text(payload, api_style=api_style)
        if structured:
            parsed = json.loads(content)
            healthy = parsed == {"ok": True}
        else:
            healthy = bool(content.strip())
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        healthy = False

    return ProviderProbeResult(
        name=name,
        attempted=True,
        healthy=healthy,
        status_code=response.status_code,
        latency_ms=_latency_ms(started),
        trace_id=trace_id,
        error_code=None if healthy else "invalid_provider_response",
        error_message=None if healthy else "Provider returned HTTP 200 with an invalid health payload.",
    )


def _probe_request(
    *,
    base_url: str,
    api_style: str,
    model: str,
    enable_thinking: bool | None,
    structured: bool,
) -> tuple[str, dict[str, Any]]:
    schema = {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
        "additionalProperties": False,
    }
    if api_style == "chat_completions":
        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": "Return JSON with ok=true." if structured else "Reply exactly OK.",
                }
            ],
            "stream": False,
            "max_completion_tokens": 32 if structured else 16,
        }
        if enable_thinking is not None:
            body["enable_thinking"] = enable_thinking
        if structured:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "requirement_provider_health",
                    "strict": True,
                    "schema": schema,
                },
            }
        return f"{base_url}/chat/completions", body

    body = {
        "model": model,
        "store": False,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Return JSON with ok=true." if structured else "Reply exactly OK.",
                    }
                ],
            }
        ],
    }
    if structured:
        body["text"] = {
            "format": {
                "type": "json_schema",
                "name": "requirement_provider_health",
                "strict": True,
                "schema": schema,
            }
        }
    return f"{base_url}/responses", body


def _probe_output_text(payload: Any, *, api_style: str) -> str:
    if not isinstance(payload, dict):
        raise TypeError("Provider payload must be an object")
    if api_style == "chat_completions":
        choices = payload["choices"]
        content = choices[0]["message"]["content"]
        if not isinstance(content, str):
            raise TypeError("Chat completion content must be text")
        return content

    for output in payload.get("output", []):
        if not isinstance(output, dict):
            continue
        for content in output.get("content", []):
            if isinstance(content, dict) and content.get("type") == "output_text":
                text = content.get("text")
                if isinstance(text, str):
                    return text
    raise KeyError("Responses payload has no output_text")


def _response_trace_id(response: httpx.Response) -> str | None:
    for header in ("x-trace-id", "x-request-id"):
        value = response.headers.get(header)
        if value:
            return value
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    for key in ("traceId", "trace_id", "requestId", "request_id"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _safe_provider_error(response: httpx.Response) -> tuple[str | None, str | None]:
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return None, None
    if not isinstance(payload, dict):
        return None, None
    code = payload.get("code")
    message = payload.get("message")
    return (
        code.strip()[:80] if isinstance(code, str) and code.strip() else None,
        message.strip()[:200] if isinstance(message, str) and message.strip() else None,
    )


def _latency_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))


def record_provider_smoke_snapshot(
    result: RequirementProviderHealthResult,
    *,
    path: Path = DEFAULT_PROVIDER_SMOKE_SNAPSHOT,
) -> bool:
    """Persist only an actually executed live smoke; zero-call checks never overwrite history."""
    if not (
        result.execution_requested
        and result.live_cost_confirmed
        and result.provider_calls > 0
    ):
        return False
    save_provider_smoke_snapshot(
        ProviderSmokeSnapshot(
            checked_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            state=result.state,
            provider=result.provider,
            model=result.model,
            ready=result.ready_for_requirement_live_run,
            blocker=result.blocker,
            provider_calls=result.provider_calls,
            plain_status_code=result.plain_probe.status_code,
            structured_status_code=result.structured_probe.status_code,
        ),
        path=path,
    )
    return True


def _serialize(result: RequirementProviderHealthResult) -> dict[str, Any]:
    payload = asdict(result)
    payload["plainProbe"] = payload.pop("plain_probe")
    payload["structuredProbe"] = payload.pop("structured_probe")
    payload["readyForRequirementLiveRun"] = payload.pop(
        "ready_for_requirement_live_run"
    )
    payload["apiKeyConfigured"] = payload.pop("api_key_configured")
    payload["executionRequested"] = payload.pop("execution_requested")
    payload["liveCostConfirmed"] = payload.pop("live_cost_confirmed")
    payload["providerCalls"] = payload.pop("provider_calls")
    payload["apiStyle"] = payload.pop("api_style")
    payload["baseUrl"] = payload.pop("base_url")
    return payload


def main() -> int:
    args = _arguments()
    result = check_requirement_provider_health(
        settings=get_settings(),
        execute_health_probe=args.execute_health_probe,
        confirm_live_cost=args.confirm_live_cost,
    )
    record_provider_smoke_snapshot(result)
    payload = _serialize(result)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"state={result.state} provider={result.provider} model={result.model} "
            f"apiStyle={result.api_style} providerCalls={result.provider_calls} "
            f"readyForRequirementLiveRun={result.ready_for_requirement_live_run}"
        )
        if result.blocker:
            print(f"blocker={result.blocker}")
    if result.state == "blocked":
        return 2
    if result.state == "unhealthy":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
