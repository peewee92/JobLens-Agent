"""Protocol models shared unchanged by HTTP and MCP."""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.application.job_requirements.description_readiness import MAX_DESCRIPTION_CHARS
from .ssrf_guard import MAX_URL_CHARS, CaptureError, parse_url

CaptureUrl = Annotated[str, Field(min_length=8, max_length=MAX_URL_CHARS, pattern=r"^https?://")]
RenderMode = Literal["auto", "playwright"]
CaptureTimeout = Annotated[int, Field(ge=3000, le=25_000), Field(strict=True)]
ExtractionMethod = Literal["none", "json_ld", "static_html", "playwright_dom", "playwright_a11y"]
QualityGrade = Literal["full_jd", "partial_jd", "card_only", "unavailable"]
InterventionReason = Literal["login_required", "captcha_detected", "anti_bot_challenge", "unsupported_spa_shell"]
CaptureStatus = Literal["captured", "needs_human_intervention", "blocked", "failed"]


class CaptureModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UrlJobCaptureRequest(CaptureModel):
    url: CaptureUrl
    renderMode: RenderMode = "auto"
    timeoutMs: CaptureTimeout = 15_000

    @field_validator("url")
    @classmethod
    def valid_url(cls, value: str) -> str:
        try:
            parse_url(value)
        except CaptureError:
            # Syntactically valid but forbidden, handled by the shared policy.
            pass
        return value


class CapturedJobDraft(CaptureModel):
    title: str = Field(min_length=1, max_length=255)
    company: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=MAX_DESCRIPTION_CHARS)
    sourceUrl: str = Field(max_length=MAX_URL_CHARS)


class CaptureDiagnostics(CaptureModel):
    httpStatus: int | None
    elapsedMs: int = Field(ge=0)
    descriptionLength: int = Field(ge=0)
    rawTextLength: int = Field(ge=0)
    a11yNodeCount: int | None = Field(ge=0)
    adapterUsed: str = Field(max_length=64)
    truncationApplied: bool


class UrlJobCaptureResponse(CaptureModel):
    captureId: str = Field(min_length=1, max_length=128)
    status: CaptureStatus
    requestedUrl: str = Field(max_length=MAX_URL_CHARS)
    finalUrl: str | None = Field(max_length=MAX_URL_CHARS)
    capturedAt: datetime
    extractionMethod: ExtractionMethod
    qualityGrade: QualityGrade
    draft: CapturedJobDraft | None
    diagnostics: CaptureDiagnostics
    blockers: list[str]
    interventionReason: InterventionReason | None
    providerCalls: Literal[0]
