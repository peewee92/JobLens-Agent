#!/usr/bin/env python3
"""Start the personal product on loopback, without seeds or implicit model configuration."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import time

from demo import BACKEND, ROOT, WEB, check_dependencies, check_ports, handle_stop, stop, wait_ready

MARKER = "joblens-local.json"
DB_NAME = "local.db"
DATA_VERSION = {"kind": "joblens-personal-local", "version": 1, "status": "ready"}


def protected_directory(directory: Path) -> Path:
    if directory.is_symlink():
        raise RuntimeError("本地数据目录不能是符号链接。")
    path = directory.resolve()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker = path / MARKER
    database = path / DB_NAME
    if marker.is_file() and not marker.is_symlink():
        if json.loads(marker.read_text()) != DATA_VERSION or not database.is_file() or database.is_symlink():
            raise RuntimeError("该目录尚未完成初始化或缺少正式数据库；保留原目录，请另选目录。")
    else:
        if any(path.iterdir()):
            raise RuntimeError("仅接受空目录或由本命令创建的本地库；不会迁移演示库或其他数据库。")
        with marker.open("x") as stream:
            json.dump({**DATA_VERSION, "status": "initializing"}, stream)
    return path


def environment(directory: Path, config: Path | None, backend: int, web: int):
    prefixes = ("PROFILE_EXTRACTOR_", "REQUIREMENT_EXTRACTOR_", "SEMANTIC_MATCH_", "CAREER_INTENT_", "OPENAI_", "JOBLENS_")
    base = {key: value for key, value in os.environ.items() if not key.startswith(prefixes)}
    return {**base, "APP_ENV": "local", "JOBLENS_LOCAL_PRODUCT": "1", "JOBLENS_LOCAL_WEB_PORT": str(web),
            "JOBLENS_LOCAL_CONFIG": str(config) if config else "",
            "JOBLENS_BACKEND_URL": f"http://127.0.0.1:{backend}", "WEB_BASE_URL": f"http://127.0.0.1:{web}",
            "DATABASE_URL": f"sqlite:///{directory / DB_NAME}",
            "CAREER_AGENT_CHECKPOINT_PATH": str(directory / "checkpoint.db"),
            "REQUIREMENT_ACCEPTANCE_PRIVATE_ROOT": str(directory / "acceptance"),
            "NEXT_TELEMETRY_DISABLED": "1", "PYTHONDONTWRITEBYTECODE": "1",
            "REQUIREMENT_EXTRACTOR_FALLBACK_PROVIDER": "disabled", "CAREER_INTENT_PROVIDER": "disabled"}


def prepare_web(web: int):
    path = WEB / f".tsconfig-local-{web}.json"
    if not path.exists():
        config = json.loads((WEB / "tsconfig.json").read_text())
        config["include"] = ["next-env.d.ts", "app/**/*.ts", "app/**/*.tsx", "components/**/*.ts", "components/**/*.tsx", "lib/**/*.ts", "tests/**/*.ts"]
        path.write_text(json.dumps(config, indent=2) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description="启动 JobLens 本地正式模式（不加载演示样本，不自动调用模型）。")
    parser.add_argument("--directory", type=Path, default=ROOT / "data/local/personal")
    parser.add_argument("--model-config", type=Path, help="可选：现有后端模型配置文件；省略则关闭模型，从手填开始。")
    parser.add_argument("--backend-port", type=int, default=8102)
    parser.add_argument("--web-port", type=int, default=3102)
    parser.add_argument("--production", action="store_true", help="先构建网页再启动稳定版本，不显示开发工具。")
    args = parser.parse_args(argv)
    processes, logs = [], []
    directory = None
    try:
        check_dependencies()
        check_ports(args.backend_port, args.web_port)
        config = args.model_config.resolve(strict=True) if args.model_config else None
        if config and not config.is_file():
            raise RuntimeError("模型配置必须是一个文件。")
        directory = protected_directory(args.directory)
        print(f"准备本地正式数据库：{directory}", flush=True)
        env = environment(directory, config, args.backend_port, args.web_port)
        python = str(BACKEND / ".venv/bin/python")
        with (directory / "setup.log").open("a") as log:
            subprocess.run([python, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env,
                           stdout=log, stderr=log, check=True)
        (directory / MARKER).write_text(json.dumps(DATA_VERSION) + "\n")
        prepare_web(args.web_port)
        web_env = {key: value for key, value in env.items() if key != "JOBLENS_LOCAL_CONFIG"}
        if args.production:
            print("正在构建本地网页…", flush=True)
            with (directory / "build.log").open("a") as log:
                subprocess.run(["pnpm", "exec", "next", "build", "--webpack"], cwd=WEB,
                               env=web_env, stdout=log, stderr=log, check=True)
        web_command = ["pnpm", "exec", "next", "start" if args.production else "dev"]
        if not args.production:
            web_command += ["--webpack"]
        web_command += ["--hostname", "127.0.0.1", "--port", str(args.web_port)]
        commands = [
            ([python, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(args.backend_port)], BACKEND, env, "backend.log"),
            (web_command, WEB, web_env, "web.log"),
        ]
        for command, cwd, child_env, name in commands:
            log = (directory / name).open("a")
            logs.append(log)
            processes.append(subprocess.Popen(command, cwd=cwd, env=child_env, stdout=log, stderr=log, start_new_session=True))
        wait_ready(f"http://127.0.0.1:{args.backend_port}/api/v1/readiness", processes)
        wait_ready(f"http://127.0.0.1:{args.web_port}", processes)
        restart = [sys.executable, str(ROOT / "scripts/local.py"), "--directory", str(directory),
                   "--backend-port", str(args.backend_port), "--web-port", str(args.web_port)]
        if config:
            restart += ["--model-config", str(config)]
        if args.production:
            restart += ["--production"]
        print(f"打开：http://127.0.0.1:{args.web_port}（本地正式模式）", flush=True)
        print(("已读取指定的模型配置；模型步骤仍需逐次确认。" if config else "未接入模型；可先手填职业资料。")
              + "\nCtrl+C 结束，进度保留。恢复命令：" + shlex.join(restart), flush=True)
        while all(proc.poll() is None for proc in processes):
            time.sleep(.3)
        raise RuntimeError("有服务退出，未自动重启。")
    except KeyboardInterrupt:
        return 0
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"无法启动：{exc}", file=sys.stderr)
        if directory:
            print(f"查看日志：{directory}", file=sys.stderr)
        return 1
    finally:
        stop(processes)
        for log in logs:
            log.close()


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, handle_stop)
    raise SystemExit(main())
