"""Read-only orchestration for one URL; no repositories, workflows or providers."""
from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from app.application.job_imports.manual import ManualJobInput
from app.application.job_requirements.description_readiness import MAX_DESCRIPTION_CHARS

from .html_extractor import ExtractedJob, HtmlPosting, a11y_description, grade_description
from .models import (
    CaptureDiagnostics, CapturedJobDraft, CaptureStatus, ExtractionMethod, InterventionReason,
    UrlJobCaptureRequest, UrlJobCaptureResponse,
)
from .playwright_fetcher import PlaywrightFetcher, RenderIntervention, intervention_for_status
from .ssrf_guard import CaptureBudget, CaptureError, GuardedHttpClient, PageResponse

_POLICY_CODES = {"url_capture_ssrf_blocked", "url_capture_policy_blocked", "unsupported_content_type"}


class CaptureJobUrlUseCase:
    def __init__(self, http=None, browser=None) -> None:
        self.http = http if http is not None else GuardedHttpClient()
        self.browser = browser if browser is not None else PlaywrightFetcher()

    async def execute(self, request: UrlJobCaptureRequest) -> UrlJobCaptureResponse:
        loop = asyncio.get_running_loop()
        started = loop.time()
        deadline = started + request.timeoutMs / 1000
        budget = CaptureBudget()
        document: PageResponse | None = None
        raw_length = 0
        a11y_count: int | None = None
        adapter = "guarded_http"

        def result(
            status: CaptureStatus, *, method: ExtractionMethod = "none",
            candidate: ExtractedJob | None = None, blocker: str | None = None,
            reason: InterventionReason | None = None,
        ) -> UrlJobCaptureResponse:
            draft = None
            text = candidate.description if candidate else ""
            clipped = text[:MAX_DESCRIPTION_CHARS].rstrip()
            if candidate is not None:
                assert document is not None and candidate.usable
                manual = ManualJobInput(
                    title=candidate.title[:255], company=candidate.company[:255], description=clipped,
                    sourceUrl=document.url,
                )
                draft = CapturedJobDraft.model_validate(manual.model_dump(by_alias=True))
            return UrlJobCaptureResponse(
                captureId=f"cap_{uuid4().hex}", status=status, requestedUrl=request.url,
                finalUrl=document.url if document else None, capturedAt=datetime.now(UTC),
                extractionMethod=method, qualityGrade=grade_description(clipped), draft=draft,
                diagnostics=CaptureDiagnostics(
                    httpStatus=document.status if document else None, elapsedMs=int((loop.time() - started) * 1_000),
                    descriptionLength=len(clipped), rawTextLength=max(raw_length, len(text)), a11yNodeCount=a11y_count,
                    adapterUsed=adapter, truncationApplied=len(text) > MAX_DESCRIPTION_CHARS,
                ),
                blockers=[blocker] if blocker else [], interventionReason=reason, providerCalls=0,
            )

        async def capture() -> UrlJobCaptureResponse:
            nonlocal document, raw_length, a11y_count, adapter
            document = await self.http.fetch(request.url, budget)
            page = await asyncio.to_thread(
                HtmlPosting, document.body if document.is_html else b"", content_type=document.headers.get("content-type", ""),
            )
            if reason := await asyncio.to_thread(page.intervention, document.url, document.status) or intervention_for_status(document.status):
                return result("needs_human_intervention", reason=reason)
            if not 200 <= document.status < 300:
                raise CaptureError("http_error")
            if not document.is_html:
                raise CaptureError("unsupported_content_type")
            structured = await asyncio.to_thread(page.structured)
            if request.renderMode == "auto":
                if structured and structured.usable and len(structured.description) >= 120:
                    raw_length = len(structured.description)
                    return result("captured", method="json_ld", candidate=structured)
                semantic, raw_length = await asyncio.to_thread(page.semantic, structured, source_url=document.url)
                if semantic.usable:
                    return result("captured", method="static_html", candidate=semantic)
                if structured and structured.usable:
                    return result("captured", method="json_ld", candidate=structured)
                if not page.has_scripts:
                    return result("failed", blocker="posting_not_found")

            adapter = "local_chromium"
            rendered = await self.browser.render(document, self.http, budget)
            page = await asyncio.to_thread(HtmlPosting, rendered.html)
            if reason := await asyncio.to_thread(page.intervention, document.url, document.status):
                return result("needs_human_intervention", reason=reason)
            rendered_structured = await asyncio.to_thread(page.structured) or structured
            semantic, raw_length = await asyncio.to_thread(page.semantic, rendered_structured, source_url=document.url)
            if rendered_structured and rendered_structured.usable and not semantic.usable:
                semantic = rendered_structured
            if semantic.usable and grade_description(semantic.description) == "full_jd":
                return result("captured", method="playwright_dom", candidate=semantic)
            accessible, a11y_count = a11y_description(rendered.accessibility, semantic.title, semantic.company)
            if (semantic.title and semantic.company and accessible
                    and (not semantic.usable or grade_description(accessible) == "full_jd")):
                return result("captured", method="playwright_a11y", candidate=replace(semantic, description=accessible))
            if semantic.usable:
                return result("captured", method="playwright_dom", candidate=semantic)
            if page.has_scripts:
                return result("needs_human_intervention", reason="unsupported_spa_shell")
            return result("failed", blocker="posting_not_found")

        operation = asyncio.create_task(capture())
        try:
            # Stop egress on the deadline even if browser-process teardown is still in progress.
            await asyncio.wait({operation}, timeout=max(0, deadline - loop.time()))
            if not operation.done() or loop.time() >= deadline:
                if operation.done():
                    _consume_cleanup(operation)
                return result("failed", blocker="capture_timeout")
            return operation.result()
        except RenderIntervention as exc:
            return result("needs_human_intervention", reason=exc.reason)
        except CaptureError as exc:
            return result("blocked" if exc.code in _POLICY_CODES else "failed", blocker=exc.code)
        finally:
            budget.closed = True
            if not operation.done():
                operation.cancel()
                operation.add_done_callback(_consume_cleanup)


def _consume_cleanup(task: asyncio.Task) -> None:
    if not task.cancelled():
        task.exception()
