"""Bounded physical dispatch, scoped to the current session. No retries or fallbacks."""
from contextlib import contextmanager
from threading import BoundedSemaphore
import httpx
from app.byok.context import current_model
from app.byok.transport import PublicTransport
from app.demo.sessions import DemoError

slots = BoundedSemaphore(2)

@contextmanager
def execution(state):
    with state.lock:
        if state.busy:
            raise DemoError('model_busy', 409, '当前模型操作尚未结束。')
        if not state.connection:
            raise DemoError('model_not_connected', 409, '请先连接自己的模型。')
        if not slots.acquire(blocking=False):
            raise DemoError('model_capacity', 503, '模型服务当前繁忙，请稍后重试；尚未发送请求。')
        state.busy = True
    try:
        yield
    finally:
        with state.lock:
            state.busy = False
        slots.release()


class OnceTransport(httpx.BaseTransport):
    def __init__(self, state):
        self.state = state
        self.inner = PublicTransport()
        self.sent = False
    def handle_request(self, request):
        if self.sent or not self.state.busy:
            raise httpx.TransportError('模型请求未获授权或已发送，禁止自动重试')
        self.sent = True
        response = self.inner.handle_request(request)
        # Even an untrusted compatible service must not echo its received credential into a trace.
        response.read()
        secret = self.state.connection.apiKey.get_secret_value().encode()
        content = response.content.replace(secret, b'[REDACTED]') if secret else response.content
        return httpx.Response(response.status_code, content=content,
            headers={'content-type':'application/json'}, request=request)
    def close(self):
        self.inner.close()


def transport_factory():
    state = current_model.get()
    if state and state.mode == 'byok':
        return lambda: OnceTransport(state)
    return None


@contextmanager
def import_lease(state):
    with state.lock:
        if state.importing:
            raise DemoError('import_busy', 409, '另一个岗位正在保存，请先检查岗位列表。')
        state.importing = True
    try:
        yield
    finally:
        with state.lock:
            state.importing = False
