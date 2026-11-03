"""Public HTTPS only: pin validated IP at connect time, preserve TLS/SNI hostname."""
import ipaddress
import socket
import ssl
from urllib.parse import urlsplit
import httpcore
import httpx
from httpcore._backends.sync import SyncBackend


def validate_url(value):
    u = urlsplit(value)
    if (u.scheme != 'https' or not u.hostname or u.username or u.password or u.query or u.fragment
            or u.port not in (None, 443) or '\\' in value or any(ord(c) <= 32 for c in value)):
        raise ValueError('仅支持无凭证、无查询参数的公共 HTTPS 地址（443 端口）')
    public_addresses(u.hostname)
    return value.rstrip('/')


def public_addresses(host):
    try:
        addresses = list(dict.fromkeys(item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)))
        if not addresses or any(not ipaddress.ip_address(a).is_global or ipaddress.ip_address(a).ipv4_mapped is not None
                                for a in addresses if isinstance(ipaddress.ip_address(a), ipaddress.IPv6Address)):
            raise ValueError('地址不可用')
        if not addresses or any(not ipaddress.ip_address(a).is_global or ipaddress.ip_address(a).is_multicast or ipaddress.ip_address(a).is_reserved for a in addresses):
            raise ValueError('地址不可用')
        return addresses
    except (OSError, ValueError) as exc:
        raise ValueError('模型地址必须解析到公共网络，不能使用本机或内网地址') from exc


class PublicNetworkBackend(httpcore.NetworkBackend):
    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        # SyncBackend receives a numeric address: DNS cannot change between check and connect.
        address = public_addresses(host)[0]
        if port != 443 or local_address is not None:
            raise httpcore.ConnectError('模型目标被拒绝')
        return SyncBackend().connect_tcp(address, port, timeout, socket_options=socket_options)
    def connect_unix_socket(self, *args, **kwargs):
        raise httpcore.ConnectError('Unix socket disabled')
    def sleep(self, seconds):
        raise httpcore.ConnectError('Automatic retries disabled')


class PublicTransport(httpx.HTTPTransport):
    def __init__(self):
        # HTTPX exposes no network_backend argument. Keep its public request/response adapter,
        # replacing only its pool, with an explicit dependency compatibility test.
        super().__init__(retries=0, trust_env=False)
        self._pool.close()
        self._pool = httpcore.ConnectionPool(ssl_context=ssl.create_default_context(), retries=0,
            network_backend=PublicNetworkBackend(), max_connections=1, max_keepalive_connections=0)
    def handle_request(self, request):
        if request.url.scheme != 'https' or request.url.port not in (None, 443):
            raise httpx.ConnectError('模型目标被拒绝')
        request.headers['Accept-Encoding'] = 'identity'
        response = super().handle_request(request)
        if response.headers.get('content-encoding', 'identity').lower() != 'identity':
            response.close()
            raise httpx.ReadError('模型服务必须返回未压缩 JSON')
        # Bound untrusted provider output, including error bodies.
        data = bytearray()
        try:
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > 262144:
                    raise httpx.ReadError('模型响应超过上限')
        finally:
            response.close()
        return httpx.Response(response.status_code, headers={k:v for k,v in response.headers.items()
            if k.lower() not in ('content-encoding','content-length','transfer-encoding')}, content=bytes(data), request=request)
