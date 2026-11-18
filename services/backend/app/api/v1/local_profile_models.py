"""Explicit per-request model authorization for the loopback-only personal launcher."""
from functools import lru_cache
import os
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import SecretStr, ValidationError

from app.api.deps import get_resume_document_parser
from app.api.v1.profile_proposals import read_resume_file
from app.api.v1.schemas.profile_extraction import ProfileExtractionRequest
from app.application.ports.resume_document_parser import AbstractResumeDocumentParser
from app.byok.api import CallInput, execute_for, plan_for
from app.byok.context import ConnectionInput, ModelSession
from app.core.config import get_settings
from app.demo.sessions import DemoError
from app.workflows.profile_extraction import MAX_RESUME_CHARS, MIN_RESUME_CHARS

router = APIRouter(prefix="/local/profile-model")


@lru_cache
def model_session() -> ModelSession:
    return ModelSession(mode="local", seed="empty")


def local_mode() -> None:
    if os.environ.get("JOBLENS_LOCAL_PRODUCT") != "1" or get_settings().app_env != "local":
        raise HTTPException(status_code=404)


def configuration():
    settings = get_settings()
    if settings.profile_extractor_provider != "openai" or not settings.profile_extractor_model.strip() or not settings.openai_api_key:
        return None
    try:
        # No network during setup or plan; resolve and pin an HTTPS destination only at dispatch.
        address = urlsplit(settings.openai_base_url)
        if (address.scheme != "https" or not address.hostname or address.username or address.password
                or address.query or address.fragment or address.port not in (None, 443)
                or "\\" in settings.openai_base_url or any(ord(c) <= 32 for c in settings.openai_base_url)):
            return None
        return ConnectionInput(
            baseUrl=settings.openai_base_url.rstrip("/"), apiKey=SecretStr(settings.openai_api_key),
            model=settings.profile_extractor_model, apiStyle=settings.profile_extractor_api_style,
            enableThinking=settings.profile_extractor_enable_thinking,
        )
    except (ValueError, ValidationError):
        return None


def active_session(connection: ConnectionInput):
    session = model_session()
    with session.lock:
        if session.connection is None:
            session.connection = connection
            session.version = 1
    return session


def error(code: str, message: str, status: int):
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


@router.get("/status", dependencies=[Depends(local_mode)])
def status():
    connection = configuration()
    return {"available": connection is not None}


def make_plan(text: str):
    connection = configuration()
    if connection is None:
        return error("local_profile_model_unavailable", "尚未配置可用的简历模型，可以先手动填写。", 409)
    text = text.strip()
    if not MIN_RESUME_CHARS <= len(text) <= MAX_RESUME_CHARS:
        return error("invalid_resume_text", "简历需要 50 到 30000 个可选中的文字字符。", 422)
    plan = plan_for(active_session(connection), "profile", text,
                    profile_max_tokens=max(256, min(get_settings().profile_extractor_max_completion_tokens or 4096, 4096)))
    return {**plan, "destination": urlsplit(connection.baseUrl).hostname}


@router.post("/plan", dependencies=[Depends(local_mode)])
def plan_text(value: ProfileExtractionRequest):
    return make_plan(value.resume_text)


@router.post("/file-plan", dependencies=[Depends(local_mode)])
async def plan_file(
    parser: Annotated[AbstractResumeDocumentParser, Depends(get_resume_document_parser)],
    file: Annotated[UploadFile | None, File()] = None,
):
    return make_plan(parser.parse(await read_resume_file(file)).text)


@router.post("/calls", dependencies=[Depends(local_mode)])
def call(command: CallInput):
    connection = configuration()
    if connection is None:
        return error("local_profile_model_unavailable", "简历模型不可用，没有发出请求。", 409)
    try:
        return execute_for(active_session(connection), "profile", command)
    except DemoError as exc:
        return error(exc.code, str(exc), exc.status)
