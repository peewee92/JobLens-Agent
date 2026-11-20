"""Local-only HTTP adapter, deliberately not in the shared job-import router."""
from ipaddress import ip_address
import os
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from app.application.url_capture.models import UrlJobCaptureRequest, UrlJobCaptureResponse
from app.application.url_capture.use_case import CaptureJobUrlUseCase
from app.core.config import get_settings

CAPTURE_PATH = "/api/v1/job-imports/url-capture"
router = APIRouter(prefix="/job-imports")


def error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message}}, status_code=status, headers={"Cache-Control": "no-store"},
    )


def local_capture_allowed(request: Request) -> bool:
    if (get_settings().app_env not in {"local", "development"}
            or os.environ.get("JOBLENS_DEMO") == "1" or os.environ.get("JOBLENS_PUBLIC_DEMO") == "1"
            or not any(os.environ.get(key) == "1" for key in ("JOBLENS_LOCAL_PRODUCT", "JOBLENS_URL_CAPTURE"))):
        return False
    try:
        if not request.client or not ip_address(request.client.host).is_loopback:
            return False
        if request.url.hostname not in {"127.0.0.1", "::1", "localhost"}:
            return False
        origin = request.headers.get("origin")
        if origin:
            frontend = urlsplit(origin)
            if (frontend.scheme, frontend.netloc) != (request.url.scheme, request.url.netloc):
                return False
    except ValueError:
        return False
    return True


def get_url_capture() -> CaptureJobUrlUseCase:
    return CaptureJobUrlUseCase()


@router.post("/url-capture", response_model=UrlJobCaptureResponse, responses={403: {"description": "Capture forbidden"}})
async def capture_job_url(
    payload: UrlJobCaptureRequest,
    request: Request,
    response: Response,
    capture: CaptureJobUrlUseCase = Depends(get_url_capture),
):
    if not local_capture_allowed(request):
        return error(403, "url_capture_forbidden", "岗位链接抓取仅在本机开放。")
    if request.headers.get("content-type", "").partition(";")[0].strip().lower() != "application/json":
        return error(422, "request_validation_error", "请提交 JSON 格式的岗位链接。")
    result = await capture.execute(payload)
    if "url_capture_ssrf_blocked" in result.blockers:
        return error(403, "url_capture_ssrf_blocked", "该链接指向不允许访问的网络地址。")
    response.headers["Cache-Control"] = "no-store"
    return result
