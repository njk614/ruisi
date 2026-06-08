#!/usr/bin/env python3
"""讲解控制器。

start: 初始化状态并拉起常驻发送进程
pause: 更新状态为暂停
resume: 更新状态为运行
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
STATE_DIR = SCRIPT_DIR.parent / "runtime"
STATE_FILE = STATE_DIR / "explanation_state.json"
LOG_FILE = STATE_DIR / "dispatcher.log"
DAEMON_SCRIPT = SCRIPT_DIR / "explanation_dispatch_daemon.py"
PRIMARY_DATA_FILE = "~/.openclaw/workspace/SimulatedData/PresentationScript.md"
FALLBACK_DATA_FILE = "data/PresentationScript.md"


def json_out(payload: dict[str, Any]) -> int:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0


def resolve_primary_data_file() -> str:
    return str(Path(os.path.expanduser(PRIMARY_DATA_FILE)))


def resolve_fallback_data_file() -> str:
    return str((SCRIPT_DIR.parent / FALLBACK_DATA_FILE).resolve())


def resolve_default_data_file() -> str:
    primary = Path(resolve_primary_data_file())
    if primary.exists() and primary.is_file():
        return str(primary)

    fallback = Path(resolve_fallback_data_file())
    if fallback.exists() and fallback.is_file():
        return str(fallback)
    return str(primary)


def default_state() -> dict[str, Any]:
    return {
        "mode": "paused",
        "index": 0,
        "completion_sent": False,
        "data_file": os.environ.get("EXPLAIN_DATA_FILE", resolve_default_data_file()),
        "interval_seconds": int(os.environ.get("EXPLAIN_INTERVAL_SECONDS", "10")),
        "target_jid": os.environ.get("EXPLAIN_TARGET_JID", "niujunke@im.tuguan.net"),
        "sender_account": os.environ.get("EXPLAIN_FROM_ACCOUNT", "a01@im.tuguan.net"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def read_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return default_state()
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            # 兼容历史状态中已废弃的 lecture_lines.txt
            current_data_file = str(data.get("data_file", "")).strip()
            if current_data_file.endswith("lecture_lines.txt"):
                data["data_file"] = resolve_default_data_file()
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return default_state()


def write_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_data_file(path_text: str) -> tuple[bool, str]:
    path = Path(os.path.expanduser(path_text))
    if not path.exists() or not path.is_file():
        primary_hint = Path(resolve_primary_data_file())
        fallback_hint = Path(resolve_fallback_data_file())
        return (
            False,
            "数据文件不存在: "
            f"{path}；请确认文件已存在，或通过 --data-file / EXPLAIN_DATA_FILE 指定路径。"
            f"默认优先路径: {primary_hint}；保底路径: {fallback_hint}",
        )
    return True, "ok"


def ensure_daemon_running() -> tuple[bool, str]:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as log_fp:
            subprocess.Popen(
                [sys.executable, str(DAEMON_SCRIPT)],
                cwd=str(SCRIPT_DIR.parent),
                stdout=log_fp,
                stderr=log_fp,
                start_new_session=True,
            )
        return True, "dispatcher started"
    except OSError as exc:
        return False, f"启动发送进程失败: {exc}"


def handle_start(data_file: str, interval_seconds: int, reset_index: bool) -> tuple[bool, str, dict[str, Any]]:
    state = read_state()
    resolved_data_file = str(Path(os.path.expanduser(data_file)))
    state["data_file"] = resolved_data_file
    state["interval_seconds"] = max(1, interval_seconds)
    state["completion_sent"] = False
    if reset_index:
        state["index"] = 0

    ok, detail = ensure_data_file(state["data_file"])
    if not ok:
        return False, detail, state

    state["mode"] = "running"
    write_state(state)
    daemon_ok, daemon_detail = ensure_daemon_running()
    if not daemon_ok:
        return False, daemon_detail, state
    return True, "已开始讲解并启动定时发送", state


def handle_pause() -> tuple[bool, str, dict[str, Any]]:
    state = read_state()
    state["mode"] = "paused"
    write_state(state)
    return True, "已暂停讲解，当前位置已保留", state


def handle_resume() -> tuple[bool, str, dict[str, Any]]:
    state = read_state()
    ok, detail = ensure_data_file(str(state.get("data_file", "")))
    if not ok:
        return False, detail, state

    state["mode"] = "running"
    write_state(state)
    daemon_ok, daemon_detail = ensure_daemon_running()
    if not daemon_ok:
        return False, daemon_detail, state
    return True, "已继续讲解，将从上次位置继续发送", state


def main() -> int:
    parser = argparse.ArgumentParser(description="讲解控制接口")
    parser.add_argument("--command", required=True, choices=["start", "pause", "resume"])
    parser.add_argument("--session-id", default="")
    parser.add_argument("--data-file", default="")
    parser.add_argument("--interval-seconds", type=int, default=10)
    parser.add_argument("--no-reset-index", action="store_true")
    args = parser.parse_args()

    default_data_file = resolve_default_data_file()
    data_file = args.data_file.strip() or os.environ.get("EXPLAIN_DATA_FILE", default_data_file)
    data_file = str(Path(os.path.expanduser(data_file)))

    if args.command == "start":
        ok, message, state = handle_start(
            data_file=data_file,
            interval_seconds=args.interval_seconds,
            reset_index=not args.no_reset_index,
        )
    elif args.command == "pause":
        ok, message, state = handle_pause()
    else:
        ok, message, state = handle_resume()

    status = "success" if ok else "failed"
    return json_out(
        {
            "status": status,
            "command": args.command,
            "message": message,
            "session_id": args.session_id,
            "mode": str(state.get("mode", "paused")),
            "index": int(state.get("index", 0)),
            "data_file": str(state.get("data_file", "")),
            "interval_seconds": int(state.get("interval_seconds", 10)),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
    )


if __name__ == "__main__":
    sys.exit(main())
