"""Bounded, ephemeral synthetic databases. A process restart invalidates all tokens."""
from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
from pathlib import Path
import secrets
import shutil
from threading import RLock
import time

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.db.context import DatabaseContext


class DemoError(Exception):
    def __init__(self, code: str, status: int, message: str):
        self.code, self.status, self.message = code, status, message


@dataclass
class Entry:
    context: DatabaseContext
    created: float
    touched: float
    active: int = 0
    write_count: int = 0
    requests: list[float] | None = None


class DemoSessions:
    def __init__(self, root: Path, template: Path, *, clock=time.monotonic, capacity=20, idle=1800, lifetime=7200):
        if not template.is_file() or template.is_symlink():
            raise RuntimeError('缺少合成演示模板')
        self.root, self.template, self.clock = root, template, clock
        self.capacity, self.idle, self.lifetime = capacity, idle, lifetime
        root.mkdir(parents=True, exist_ok=True)
        self.entries: dict[str, Entry] = {}
        self.creations: OrderedDict[str, list[float]] = OrderedDict()
        self.lock = RLock()

    def _expired(self, entry, now):
        return now - entry.created >= self.lifetime or now - entry.touched >= self.idle

    def _delete(self, token):
        entry = self.entries.pop(token)
        entry.context.engine.dispose()
        shutil.rmtree(entry.context.directory)

    def _collect(self, now):
        for token, entry in list(self.entries.items()):
            if entry.active == 0 and self._expired(entry, now):
                self._delete(token)
        for key, times in list(self.creations.items()):
            remaining = [t for t in times if now - t < 60]
            if remaining:
                self.creations[key] = remaining
            else:
                del self.creations[key]

    def create(self, client: str, *, replace: str | None = None):
        with self.lock:
            now = self.clock()
            self._collect(now)
            key = hashlib.sha256(client.encode()).hexdigest()
            times = self.creations.get(key, [])
            if len(times) >= 3:
                raise DemoError('demo_rate_limited', 429, '创建过于频繁，请一分钟后重试。')
            old = self.entries.get(replace or '')
            if old and old.active:
                raise DemoError('demo_busy', 409, '当前操作尚未结束，请稍后重置。')
            if len(self.entries) >= self.capacity and old is None:
                raise DemoError('demo_capacity', 503, '演示人数已满，请稍后重试。')
            token = secrets.token_urlsafe(32)
            directory = self.root / secrets.token_hex(16)
            directory.mkdir()
            engine = None
            try:
                shutil.copyfile(self.template, directory / 'demo.db')
                engine = create_engine(f'sqlite:///{directory / "demo.db"}', connect_args={'check_same_thread': False}, pool_pre_ping=True)
                @event.listens_for(engine, 'connect')
                def foreign_keys(connection, _):
                    connection.execute('PRAGMA foreign_keys=ON')
                context = DatabaseContext(engine, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False), directory)
                if old:
                    self._delete(replace)
                self.entries[token] = Entry(context, now, now)
                # Bound even the creation-rate bookkeeping under hostile traffic.
                if key not in self.creations and len(self.creations) >= 1024:
                    self.creations.popitem(last=False)
                self.creations[key] = [*times, now]
                return token
            except Exception:
                if engine is not None:
                    engine.dispose()
                shutil.rmtree(directory, ignore_errors=True)
                raise

    @contextmanager
    def acquire(self, token, *, write=False):
        with self.lock:
            now = self.clock()
            entry = self.entries.get(token)
            if entry is None or self._expired(entry, now):
                if entry and entry.active == 0:
                    self._delete(token)
                raise DemoError('demo_session_expired', 410, '演示已结束，请重新开始样本体验。')
            recent = [t for t in (entry.requests or []) if now - t < 60]
            if len(recent) >= 240 or (write and entry.write_count >= 100):
                raise DemoError('demo_request_limit', 429, '演示操作已达限制，请稍后或重新开始。')
            entry.requests = [*recent, now]
            entry.write_count += int(write)
            entry.active += 1
            entry.touched = now
        try:
            yield entry.context
        finally:
            with self.lock:
                entry.active -= 1

    def close(self):
        with self.lock:
            for token in list(self.entries):
                if not self.entries[token].active:
                    self._delete(token)
