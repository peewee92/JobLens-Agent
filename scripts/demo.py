#!/usr/bin/env python3
"""Local synthetic product demo. Never opens the user's configured database."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'services/backend'
WEB = ROOT / 'apps/web'
MARKER = 'joblens-demo.json'


def demo_environment(directory: Path, backend_port: int = 8100) -> dict[str, str]:
    return {**os.environ, 'APP_ENV':'demo', 'JOBLENS_DEMO':'1',
        'JOBLENS_DEMO_DIRECTORY':str(directory), 'DATABASE_URL':f'sqlite:///{directory / "demo.db"}',
        'CAREER_AGENT_CHECKPOINT_PATH':str(directory / 'legacy-checkpoint.db'),
        'REQUIREMENT_EXTRACTOR_PROVIDER':'fixture', 'REQUIREMENT_EXTRACTOR_FALLBACK_PROVIDER':'disabled',
        'SEMANTIC_MATCH_PROVIDER':'disabled', 'PROFILE_EXTRACTOR_PROVIDER':'disabled',
        'CAREER_INTENT_PROVIDER':'disabled', 'OPENAI_API_KEY':'',
        'OPENAI_BASE_URL':'http://127.0.0.1:1/disabled', 'NEXT_TELEMETRY_DISABLED':'1',
        'NODE_OPTIONS':'', 'JOBLENS_BACKEND_URL':f'http://127.0.0.1:{backend_port}'}


def check_dependencies():
    python = BACKEND / '.venv/bin/python'
    if not python.exists():
        raise RuntimeError('缺少后端依赖，请先执行：cd services/backend && uv sync')
    if not shutil.which('pnpm') or not (WEB / 'node_modules/next/package.json').exists():
        raise RuntimeError('缺少网页依赖，请先安装 Node.js 与 pnpm，然后执行：cd apps/web && pnpm install --frozen-lockfile')


def prepare_demo(directory: Path, *, empty: bool = False):
    """Migrate only a newly created or explicitly owned demo directory; never replace data."""
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    marker = directory / MARKER
    if marker.exists():
        metadata = json.loads(marker.read_text())
        if metadata != {'kind':'joblens-synthetic-demo', 'version':1, 'status':'ready', 'empty':empty}:
            raise RuntimeError('该目录不是可恢复的同类演示，或上次初始化未完成；保留原目录，请不指定 --directory 创建新演示。')
        if not (directory / 'demo.db').is_file() or (directory / 'demo.db').is_symlink():
            raise RuntimeError('演示数据库缺失或为符号链接；不会创建替代数据。')
    else:
        if any(directory.iterdir()):
            raise RuntimeError('演示目录非空且没有专属标识，拒绝迁移或覆盖。请使用新空目录。')
        metadata = {'kind':'joblens-synthetic-demo', 'version':1, 'status':'initializing', 'empty':empty}
        marker.write_text(json.dumps(metadata))
    env = demo_environment(directory)
    python = str(BACKEND / '.venv/bin/python')
    with (directory / 'setup.log').open('a') as log:
        subprocess.run([python,'-m','alembic','upgrade','head'],cwd=BACKEND,env=env,stdout=log,stderr=log,check=True)
        if metadata['status'] == 'initializing' and not empty:
            subprocess.run([python,'-m','scripts.seed_product_demo'],cwd=BACKEND,env=env,stdout=log,stderr=log,check=True)
    metadata['status'] = 'ready'
    marker.write_text(json.dumps(metadata))


def prepare_web_types(web_port: int):
    # Next.js adds generated route types to its tsconfig. Keep those writes out of the user's config.
    target = WEB / f'.tsconfig-demo-{web_port}.json'
    if not target.exists():
        config = json.loads((WEB / 'tsconfig.json').read_text())
        config['include'] = ['next-env.d.ts','app/**/*.ts','app/**/*.tsx','components/**/*.ts','components/**/*.tsx','lib/**/*.ts','tests/**/*.ts']
        target.write_text(json.dumps(config,indent=2)+'\n')


def check_ports(*ports):
    if len(set(ports)) != len(ports):
        raise RuntimeError('网页与后端端口必须不同。')
    for port in ports:
        if not 1024 <= port <= 65535:
            raise RuntimeError('端口应在 1024–65535 范围内。')
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            try: sock.bind(('127.0.0.1',port))
            except OSError as exc: raise RuntimeError(f'端口 {port} 已被占用；不会停止其他进程，请更换端口。') from exc


def wait_ready(url, processes, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(p.poll() is not None for p in processes):
            raise RuntimeError('启动进程已退出，请查看演示目录中的日志。')
        try:
            with urlopen(url,timeout=2) as response:
                if response.status == 200: return
        except (OSError, URLError): pass
        time.sleep(.2)
    raise RuntimeError('启动超时，请查看演示目录中的日志；数据保留，不会自动重启。')


def stop(processes):
    for process in reversed(processes):
        try: os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError: pass
    for process in processes:
        try: process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            try: os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError: pass
            process.wait()


def main(argv=None):
    parser = argparse.ArgumentParser(description='隔离合成演示：不读取真实库，不使用模型。首次请先安装项目依赖。')
    parser.add_argument('--directory',type=Path,help='恢复本命令创建的演示目录；默认新建临时目录')
    parser.add_argument('--empty',action='store_true',help='从空白演示库开始，自行填写合成资料和岗位')
    parser.add_argument('--backend-port',type=int,default=8100)
    parser.add_argument('--web-port',type=int,default=3100)
    args = parser.parse_args(argv)
    processes, logs = [], []
    directory = None
    try:
        check_dependencies()
        check_ports(args.backend_port,args.web_port)
        directory = (args.directory or Path(tempfile.mkdtemp(prefix='joblens-demo-'))).resolve()
        print(f'正在准备隔离演示：{directory}',flush=True)
        prepare_demo(directory,empty=args.empty)
        env = demo_environment(directory,args.backend_port)
        # Separate Next.js cache: a normal development server may already be running.
        env['JOBLENS_DEMO_WEB_PORT'] = str(args.web_port)
        prepare_web_types(args.web_port)
        commands = [([str(BACKEND / '.venv/bin/python'),'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(args.backend_port)],BACKEND,'backend.log'),
            (['pnpm','exec','next','dev','--hostname','127.0.0.1','--port',str(args.web_port)],WEB,'web.log')]
        for command,cwd,name in commands:
            log = (directory / name).open('a'); logs.append(log)
            processes.append(subprocess.Popen(command,cwd=cwd,env=env,stdout=log,stderr=log,start_new_session=True))
        wait_ready(f'http://127.0.0.1:{args.backend_port}/api/v1/readiness',processes)
        wait_ready(f'http://127.0.0.1:{args.web_port}',processes)
        restore = [sys.executable,str(ROOT / 'scripts/demo.py'),'--directory',str(directory),
            '--backend-port',str(args.backend_port),'--web-port',str(args.web_port)]
        if args.empty: restore.append('--empty')
        print(f'\n打开：http://127.0.0.1:{args.web_port}\n纯合成资料与岗位，离线规则演示，不代表真实模型效果。',flush=True)
        print('从工作台比较岗位 → 确认目标 → 开始执行 → 完成行动与确认事实 → 更新分析。',flush=True)
        print('Ctrl+C 退出；只停止本命令创建的进程，保留演示数据。\n恢复命令：'+shlex.join(restore),flush=True)
        while all(p.poll() is None for p in processes): time.sleep(.3)
        raise RuntimeError('演示进程已退出；不会自动重复运行。请查看日志。')
    except KeyboardInterrupt:
        print('\n演示已停止，数据保留。',flush=True)
        return 0
    except (RuntimeError,ValueError,OSError,subprocess.CalledProcessError) as exc:
        print(f'无法启动演示：{exc}',file=sys.stderr)
        if directory: print(f'目录和日志：{directory}',file=sys.stderr)
        return 1
    finally:
        stop(processes)
        for log in logs: log.close()


def handle_stop(_signum, _frame):
    raise KeyboardInterrupt()


if __name__ == '__main__':
    signal.signal(signal.SIGTERM,handle_stop)
    raise SystemExit(main())
