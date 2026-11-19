"""Verify a trusted web-adapter identity before selecting a private work database."""
from __future__ import annotations

import hashlib
import hmac
import re
import time
from collections.abc import Callable, Mapping

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.db.context import DatabaseContext, current_database

OWNER = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
SIGNATURE = re.compile(r"[a-f0-9]{64}\Z")
AUDIENCE = "joblens-private-workspace/v1"
MAX_SKEW_SECONDS = 30


def identity_signature(secret: bytes, owner: str, timestamp: str, method: str, target: str) -> str:
    message = "\n".join((AUDIENCE, owner, timestamp, method, target)).encode("ascii")
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


class PrivateWorkspaceBoundary:
    """No database selection by browser cookies, client-provided actor IDs, or URL parameters."""

    def __init__(self, app: ASGIApp, *, workspaces: Mapping[str, DatabaseContext],
                 secret: bytes, clock: Callable[[], float] = time.time):
        if len(secret) < 32 or not workspaces or any(not OWNER.fullmatch(owner) for owner in workspaces):
            raise RuntimeError("Private workspace must have a dedicated proxy secret and verified accounts.")
        self.app = app
        self.workspaces = dict(workspaces)
        self.secret = secret
        self.clock = clock

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope["method"] == "GET" and scope["path"] == "/api/v1/health":
            await self.app(scope, receive, send)
            return

        async def reject(status: int, code: str, message: str) -> None:
            await JSONResponse({"error": {"code": code, "message": message}}, status_code=status,
                               headers={"Cache-Control": "no-store"})(scope, receive, send)

        headers = Headers(scope=scope)
        keys = ("x-joblens-owner", "x-joblens-issued", "x-joblens-workspace-signature")
        values = [headers.getlist(key) for key in keys]
        if any(len(value) != 1 for value in values):
            await reject(401, "workspace_sign_in_required", "请从 JobLens 登录后打开个人工作台。")
            return

        owner, issued, signature = (value[0] for value in values)
        request_target = scope.get("raw_path")
        try:
            if not request_target or not OWNER.fullmatch(owner) or not re.fullmatch(r"[0-9]{1,12}", issued) or not SIGNATURE.fullmatch(signature):
                raise ValueError
            query = scope.get("query_string", b"")
            target = (request_target + (b"?" + query if query else b"")).decode("ascii")
            if abs(self.clock() - int(issued)) > MAX_SKEW_SECONDS or any(ch in target for ch in "\r\n"):
                raise ValueError
            valid = hmac.compare_digest(signature, identity_signature(self.secret, owner, issued, scope["method"], target))
        except (ValueError, UnicodeError):
            valid = False
        if not valid:
            await reject(401, "workspace_sign_in_required", "登录凭证未能确认，请重新打开个人工作台。")
            return
        workspace = self.workspaces.get(owner)
        if workspace is None:
            await reject(403, "workspace_not_provisioned", "此账号还没有获准使用个人工作台。")
            return

        async def no_store(message):
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["cache-control"] = "private, no-store"
            await send(message)

        chosen = current_database.set(workspace)
        try:
            await self.app(scope, receive, no_store)
        finally:
            current_database.reset(chosen)
