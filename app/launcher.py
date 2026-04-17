from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from app.core.bot import build_bot
from app.core.settings import ConfigError


WORKER_ENV_KEY = "DRAKORIA_RUN_MODE"
WORKER_ENV_VALUE = "worker"
AUTO_RELOAD_ENV_KEY = "AUTO_RELOAD"
WATCH_EXTENSIONS = {".py", ".json", ".env", ".example"}
WATCH_DIRECTORIES = ("app", "config")
WATCH_FILES = ("bot.py", ".env", ".env.example", "requirements.txt", "README.md")


async def _run_worker() -> None:
    try:
        await build_bot().run_async()
    except ConfigError as exc:
        print("[Drakoria] A inicializacao foi interrompida por erro de configuracao.")
        print(str(exc))
        raise SystemExit(1) from exc


def _iter_watch_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for relative in WATCH_DIRECTORIES:
        directory = root / relative
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if path.is_file() and path.suffix.lower() in WATCH_EXTENSIONS:
                paths.append(path)
    for relative in WATCH_FILES:
        path = root / relative
        if path.exists() and path.is_file():
            paths.append(path)
    unique: dict[str, Path] = {str(path.resolve()): path for path in paths}
    return list(unique.values())


def _snapshot_files(root: Path) -> dict[str, int]:
    snapshot: dict[str, int] = {}
    for path in _iter_watch_paths(root):
        try:
            snapshot[str(path.resolve())] = path.stat().st_mtime_ns
        except FileNotFoundError:
            continue
    return snapshot


def _spawn_worker(root: Path) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env[WORKER_ENV_KEY] = WORKER_ENV_VALUE
    env[AUTO_RELOAD_ENV_KEY] = "false"
    return subprocess.Popen(
        [sys.executable, "bot.py"],
        cwd=root,
        env=env,
    )


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def _supervisor_loop() -> None:
    root = Path.cwd()
    process = _spawn_worker(root)
    previous_snapshot = _snapshot_files(root)
    print(f"[Drakoria] Supervisor ativo. Processo do bot iniciado com PID {process.pid}.")

    try:
        while True:
            if process.poll() is not None:
                print(f"[Drakoria] Processo encerrado com codigo {process.returncode}. Reiniciando em 2 segundos...")
                time.sleep(2)
                process = _spawn_worker(root)
                previous_snapshot = _snapshot_files(root)
                print(f"[Drakoria] Novo processo iniciado com PID {process.pid}.")
                continue

            time.sleep(1.5)
            current_snapshot = _snapshot_files(root)
            if current_snapshot != previous_snapshot:
                print("[Drakoria] Alteracao detectada nos arquivos monitorados. Reiniciando bot para recarregar cache e codigo...")
                _terminate_process(process)
                process = _spawn_worker(root)
                previous_snapshot = current_snapshot
                print(f"[Drakoria] Reiniciado com PID {process.pid}.")
    except KeyboardInterrupt:
        print("[Drakoria] Encerrando supervisor e desligando o bot.")
    finally:
        _terminate_process(process)


def main() -> None:
    asyncio.run(_run_worker())

