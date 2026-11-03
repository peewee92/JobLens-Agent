"""Deny-by-default public adapter; business handlers remain unchanged."""
import json
from contextlib import nullcontext
from app.byok.context import current_model
import hmac
import re
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse
from app.db.context import current_database
from app.demo.sessions import DemoError, DemoSessions
from app.main import create_app

ID = r'[A-Za-z0-9_-]{1,160}'
READS = [
    r'/readiness', r'/workbench(?:/workspaces)?', r'/profile', r'/search-intent',
    r'/career-context/release-readiness', r'/jobs',
    rf'/jobs/{ID}(?:/(?:requirements|eligibility|evidence-candidates|match-input-readiness|requirement-release-readiness|match-reports|description-observations))?',
    rf'/jobs/{ID}/requirement-extractions/{ID}',
    r'/match-ranking(?:/preflight)?', r'/match-review/readiness', r'/recommendation-coverage',
    r'/match-blockers', r'/match-improvement',
    rf'/career-agent/runs(?:/{ID}(?:/(?:result|execution|update-plan|comparison))?)?',
    rf'/application-workspaces/{ID}(?:/(?:overview|actions|timeline|preparation|evidence-context|evidence-proposals|resume-variants|analysis-plan))?',
    rf'/application-workspaces/{ID}/(?:interview/questions|resume-variant/proposal)',
    rf'/job-preparation/{ID}',
]
WRITES = [
    r'/career-agent/runs', r'/career-agent/initial-scope-plan', r'/career-agent/initial-scope-runs',
    rf'/career-agent/runs/{ID}/(?:resume|continue|execution|updates)',
    rf'/application-workspaces/{ID}/actions/{ID}/status',
]


def permitted(method, path):
    patterns = READS if method == 'GET' else WRITES if method == 'POST' else []
    return any(re.fullmatch('/api/v1' + pattern, path) for pattern in patterns)


BYOK_READS = [r'/model-connection(?:/test-plan)?', r'/profile-calls/' + ID,
    rf'/jobs/{ID}/(?:requirement-call-plan|requirement-calls/{ID}|semantic-call-plan|semantic-calls/{ID})',
    r'/session-export']
BYOK_WRITES = [r'/model-connection/test', r'/profile-call-plan', r'/profile-calls', r'/job-imports/manual',
    rf'/jobs/{ID}/(?:requirement-calls|semantic-calls|requirement-confirmations|match-report)']

def byok_permitted(method, path):
    # Explicit workflow is available, but natural-language Agent remains disabled.
    if permitted(method, path):
        return True
    patterns = BYOK_READS if method == 'GET' else BYOK_WRITES if method == 'POST' else (
        [r'/profile', r'/search-intent', r'/model-connection'] if method == 'PUT' else
        [r'/model-connection'] if method == 'DELETE' else [])
    return any(re.fullmatch('/api/v1' + pattern, path) for pattern in patterns)


def error(code, status, message):
    return JSONResponse({'error': {'code': code, 'message': message}}, status_code=status,
                        headers={'Cache-Control': 'no-store'})


class PublicBoundary:
    def __init__(self, app, *, sessions, secret, origin, byok_enabled=False):
        self.byok_enabled = byok_enabled
        self.app, self.sessions, self.secret, self.origin = app, sessions, secret, origin

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        path, method = scope['path'], scope['method']
        if path == '/api/v1/health' and method == 'GET':
            return await self.app(scope, receive, send)
        if len(scope.get('query_string', b'')) > 8192:
            return await error('demo_query_too_large', 413, '演示查询过大。')(scope, receive, send)
        headers = dict(scope['headers'])
        supplied = headers.get(b'x-joblens-proxy', b'').decode('latin-1')
        if not hmac.compare_digest(supplied, self.secret):
            return await error('demo_unauthorized', 401, '请从公开演示网页进入。')(scope, receive, send)
        if method != 'GET' and headers.get(b'origin', b'').decode('latin-1') != self.origin:
            return await error('demo_origin_rejected', 403, '请求来源无效。')(scope, receive, send)
        session_route = path == '/api/v1/demo/session'
        # Cap streamed bodies too, not only Content-Length. No uploads are allowed.
        chunks, size = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            size += len(message.get('body', b''))
            if size > (131072 if self.byok_enabled else 32768):
                return await error('demo_body_too_large', 413, '演示请求过大。')(scope, receive, send)
            chunks.append(message)
            if not message.get('more_body', False):
                break
        async def replay():
            return chunks.pop(0) if chunks else await receive()
        token = headers.get(b'x-demo-session', b'').decode('latin-1')
        try:
            if session_route and method in ('POST', 'DELETE'):
                client = headers.get(b'x-demo-client', b'unknown').decode('latin-1')[:256]
                if method == 'DELETE':
                    # Reset is atomic: no unrestricted deletion of another session.
                    with self.sessions.acquire(token):
                        pass
                try:
                    body = json.loads(b''.join(m.get('body', b'') for m in chunks) or b'{}')
                    if not isinstance(body, dict) or set(body) - {'mode', 'seed'}:
                        raise ValueError()
                    mode, seed = body.get('mode', 'sample'), body.get('seed', 'sample')
                except (ValueError, TypeError):
                    raise DemoError('session_input_invalid', 422, '会话参数无效。')
                if mode == 'byok' and not self.byok_enabled:
                    raise DemoError('byok_disabled', 403, '自带模型功能尚未开放。')
                new_token = await run_in_threadpool(self.sessions.create, client,
                    replace=token if method == 'DELETE' else None, mode=mode, seed=seed)
                return await JSONResponse({'sessionToken': new_token, 'idleSeconds': 1800, 'maxAgeSeconds': 7200},
                    headers={'Cache-Control': 'no-store'})(scope, replay, send)
            with self.sessions.acquire(token, write=method != "GET") as context:
                model_state = self.sessions.state(token)
                if model_state.mode == 'byok' and not self.byok_enabled:
                    raise DemoError('byok_disabled', 403, '自带模型功能已关闭。请重新进入样本体验。')
                if not session_route and not (byok_permitted(method, path) if model_state.mode == 'byok' else permitted(method, path)):
                    raise DemoError('demo_route_disabled', 403, '当前模式不开放此接口。')
                marker = current_database.set(context)
                model_marker = current_model.set(model_state)
                try:
                    if session_route:
                        response = JSONResponse({'active': True, 'mode': model_state.mode, 'synthetic': model_state.seed == 'sample'}, headers={'Cache-Control': 'no-store'})
                        await response(scope, replay, send)
                    else:
                        async def no_cache(message):
                            if message['type'] == 'http.response.start':
                                message['headers'] = [(k, v) for k, v in message['headers'] if k.lower() != b'cache-control'] + [(b'cache-control', b'no-store')]
                            await send(message)
                        from app.byok.calls import execution, import_lease
                        importing = model_state.mode == 'byok' and path == '/api/v1/job-imports/manual' and method == 'POST'
                        paid = model_state.mode == 'byok' and method == 'POST' and bool(re.fullmatch(r'/api/v1/jobs/' + ID + r'/(?:requirement-calls|semantic-calls)', path))
                        with import_lease(model_state) if importing else nullcontext():
                            if importing:
                                from sqlalchemy import text
                                with context.engine.connect() as conn:
                                    count = conn.execute(text('SELECT count(*) FROM jobs')).scalar_one()
                                if count >= 5:
                                    raise DemoError('job_limit', 429, '当前会话最多保存五个岗位。')
                            with execution(model_state) if paid else nullcontext():
                                await self.app(scope, replay, no_cache)

                finally:
                    current_model.reset(model_marker)
                    current_database.reset(marker)
        except DemoError as exc:
            await error(exc.code, exc.status, exc.message)(scope, receive, send)


def create_public_app(sessions: DemoSessions, *, secret: str, origin: str, byok_enabled: bool = False):
    if len(secret) < 32 or not origin.startswith(('https://', 'http://localhost:', 'http://127.0.0.1:')) or origin.endswith('/'):
        raise RuntimeError('公开演示需要至少 32 字符代理密钥与无尾斜线的前端来源。')
    app = create_app()
    from app.byok.api import router as byok_router
    from fastapi.exceptions import RequestValidationError
    app.include_router(byok_router, prefix='/api/v1')
    @app.exception_handler(RequestValidationError)
    async def safe_validation(_request, _error):
        # Pydantic's default errors include raw input (including API keys).
        return error('invalid_request', 422, '输入格式无效，请检查必填项、长度与接口类型。')
    @app.exception_handler(DemoError)
    async def session_error(_request, exc):
        return error(exc.code, exc.status, exc.message)
    app.add_middleware(PublicBoundary, sessions=sessions, secret=secret, origin=origin, byok_enabled=byok_enabled)
    return app
