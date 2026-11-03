"""Dedicated deployment entrypoint. Never use this module for private/local mode."""
import asyncio
import shutil
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from contextlib import asynccontextmanager

# Set before importing application configuration; override inherited model settings.
ROOT = Path(tempfile.mkdtemp(prefix='joblens-public-')).resolve()
TEMPLATE = ROOT / 'template'
TEMPLATE.mkdir()
os.environ.update({
    'APP_ENV': 'demo', 'DATABASE_URL': f'sqlite:///{TEMPLATE / "demo.db"}',
    'CAREER_AGENT_CHECKPOINT_PATH': str(ROOT / 'unused-legacy.db'),
    'REQUIREMENT_EXTRACTOR_PROVIDER': 'fixture', 'SEMANTIC_MATCH_PROVIDER': 'disabled',
    'PROFILE_EXTRACTOR_PROVIDER': 'disabled', 'CAREER_INTENT_PROVIDER': 'disabled',
    'REQUIREMENT_EXTRACTOR_FALLBACK_PROVIDER': 'disabled', 'OPENAI_API_KEY': '',
    'OPENAI_BASE_URL': 'http://127.0.0.1:1/disabled', 'JOBLENS_DEMO_DIRECTORY': str(TEMPLATE),
})
from app.demo.public_app import create_public_app
from app.demo.sessions import DemoSessions


def initialize():
    marker = TEMPLATE / 'joblens-demo.json'
    marker.write_text(json.dumps({'kind': 'joblens-synthetic-demo', 'version': 1, 'status': 'initializing', 'empty': False}))
    # Failure is fatal. Do not serve a partially seeded template.
    subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], check=True, timeout=120)
    empty = ROOT / 'empty.db'
    shutil.copyfile(TEMPLATE / 'demo.db', empty)
    empty.chmod(0o400)
    subprocess.run([sys.executable, '-m', 'scripts.seed_product_demo'], check=True, timeout=120)
    (TEMPLATE / 'demo.db').chmod(0o400)
    return DemoSessions(ROOT / 'sessions', TEMPLATE / 'demo.db', empty_template=empty)


class LazySessions:
    def __getattr__(self, name):
        if manager is None:
            raise RuntimeError('演示尚未初始化')
        return getattr(manager, name)


manager = None
app = create_public_app(LazySessions(), secret=os.environ.get('JOBLENS_DEMO_PROXY_SECRET', ''),
                        origin=os.environ.get('JOBLENS_DEMO_FRONTEND_ORIGIN', ''),
                        byok_enabled=os.environ.get('JOBLENS_BYOK_ENABLED') == '1')


@asynccontextmanager
async def lifespan(_app):
    global manager
    manager = initialize()
    async def collect():
        while True:
            await asyncio.sleep(30)
            manager.collect()
    collector = asyncio.create_task(collect())
    try:
        yield
    finally:
        collector.cancel()
        try:
            await collector
        except asyncio.CancelledError:
            pass
        manager.close()


app.router.lifespan_context = lifespan
