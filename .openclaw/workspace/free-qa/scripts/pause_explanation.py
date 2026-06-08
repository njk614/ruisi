#!/usr/bin/env python3
"""调用 explanation-service 消息入口，触发暂停讲解。"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

from common import eprint, json_dumps, load_config


def resolve_message_service_script(config: dict[str, Any]) -> Path:
    section = config.get("explanation_service", {})
    configured = str(section.get("message_service_script", "")).strip()
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        return path.resolve()

    default_path = Path(__file__).resolve().parents[2] / "explanation-service" / "scripts" / "explanation_message_service.py"
    return default_path


def build_command(script_path: Path, config: dict[str, Any]) -> list[str]:
    section = config.get("explanation_service", {})
    pause_message = str(section.get("pause_message", "暂停讲解")).strip() or "暂停讲解"
    command = [sys.executable, str(script_path), "--message", pause_message]

    sender_jid = str(section.get("sender_jid", "")).strip()
    if sender_jid:
        command.extend(["--sender-jid", sender_jid])

    session_id = str(section.get("session_id", "")).strip()
    if session_id:
        command.extend(["--session-id", session_id])

    return command


def main() -> int:
    parser = argparse.ArgumentParser(description="触发 explanation-service 执行暂停讲解。")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        config = load_config()
        script_path = resolve_message_service_script(config)
        if not script_path.exists():
            raise FileNotFoundError(f"explanation-service 入口脚本不存在: {script_path}")

        command = build_command(script_path, config)
        if args.dry_run:
            print(json_dumps({"status": "success", "message": "dry-run", "command": command}))
            return 0

        result = subprocess.run(command, capture_output=True, text=True, check=False)
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        if result.returncode != 0:
            detail = stderr or stdout or f"exit={result.returncode}"
            raise RuntimeError(detail)

        print(json_dumps({"status": "success", "message": "已触发 explanation-service 暂停", "detail": stdout}))
        return 0
    except (OSError, RuntimeError, ValueError, FileNotFoundError) as exc:
        eprint(f"pause_explanation 执行失败：{exc}")
        print(json_dumps({"status": "failed", "message": f"暂停触发 explanation-service 失败：{exc}"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())