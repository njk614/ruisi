#!/usr/bin/env python3
"""讲解控制消息分发服务。

功能：
1. 接收上游消息并按内容分类。
2. 按消息内容分类为 start/pause/resume。
3. 调用不同 Python 接口命令。
4. 输出统一 JSON 结果。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Final

# 历史兼容：保留对 ruisi-free-qa 旧版固定结构消息的识别。
LEGACY_FREE_QA_PAUSE_DESCRIPTION: Final[str] = "【说明：当前消息最终发送给“讲解程序”，用于暂停当前讲解及讲解内容的推送】"
LEGACY_FREE_QA_RESUME_DESCRIPTION: Final[str] = "【说明：当前消息最终发送给“讲解程序”，用于恢复当前讲解及讲解内容的推送】"

START_PHRASES: Final[tuple[str, ...]] = (
    "开始讲解",
    "开始演示",
    "开始播放",
    "开始推送",
    "开讲",
    "开始吧",
    "现在开始",
    "讲解开始",
)

PAUSE_PHRASES: Final[tuple[str, ...]] = (
    "暂停",
    "暂停讲解",
    "暂停演示",
    "先暂停",
    "停一下",
    "稍等",
    "等一下",
    "不要讲了",
    "先别讲",
    "停止讲解",
    "暂停播放",
)

RESUME_PHRASES: Final[tuple[str, ...]] = (
    "继续演示",
    "继续讲解",
    "继续播放",
    "继续推送",
    "恢复演示",
    "恢复讲解",
    "恢复播放",
    "接着演示",
    "接着讲解",
    "可以继续",
    "继续吧",
    "开始讲解后继续",
    "继续一下",
    "继续说",
    "接着说",
    "恢复一下",
)

SCRIPT_DIR = Path(__file__).resolve().parent
SERVICE_ROOT_DIR = SCRIPT_DIR.parent
RUNTIME_DIR = SCRIPT_DIR.parent / "runtime"
DEDUP_FILE = RUNTIME_DIR / "processed_message_ids.json"
DEDUP_TTL_SECONDS = int(os.environ.get("EXPLAIN_DEDUP_TTL_SECONDS", "86400"))
DEDUP_MAX_RECORDS = int(os.environ.get("EXPLAIN_DEDUP_MAX_RECORDS", "5000"))


def json_out(payload: dict[str, Any]) -> int:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0


def build_response_payload(
    *,
    status: str,
    action: str,
    message: str,
    session_id: str,
    message_id: str,
    sender_jid: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": status,
        "action": action,
        "message": message,
        "session_id": session_id,
    }
    if message_id:
        payload["message_id"] = message_id
    if sender_jid:
        payload["sender_jid"] = sender_jid
    return payload


def load_dedup_records() -> dict[str, str]:
    if not DEDUP_FILE.exists():
        return {}
    try:
        data = json.loads(DEDUP_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def save_dedup_records(records: dict[str, str]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    DEDUP_FILE.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def prune_dedup_records(records: dict[str, str]) -> dict[str, str]:
    now = datetime.now()
    threshold = now - timedelta(seconds=max(60, DEDUP_TTL_SECONDS))
    kept: dict[str, str] = {}

    for msg_id, ts in records.items():
        try:
            created = datetime.fromisoformat(ts)
        except ValueError:
            continue
        if created >= threshold:
            kept[msg_id] = ts

    if len(kept) <= DEDUP_MAX_RECORDS:
        return kept

    ordered = sorted(kept.items(), key=lambda item: item[1], reverse=True)
    trimmed = dict(ordered[:DEDUP_MAX_RECORDS])
    return trimmed


def is_duplicate_message(message_id: str) -> bool:
    msg_id = message_id.strip()
    if not msg_id:
        return False

    records = prune_dedup_records(load_dedup_records())
    if msg_id in records:
        save_dedup_records(records)
        return True

    records[msg_id] = datetime.now().isoformat(timespec="seconds")
    records = prune_dedup_records(records)
    save_dedup_records(records)
    return False


def normalize_text(message: str) -> str:
    text = message.strip()
    text = re.sub(r"[\s\u3000]+", "", text)
    text = text.strip("，。！？!?.、；;：:")
    return text


def classify_structured_control_message(message: str) -> str:
    compact = re.sub(r"[\s\u3000]+", "", message)
    compact = compact.replace("'", '"')

    if LEGACY_FREE_QA_PAUSE_DESCRIPTION in message and '"status":"pause"' in compact:
        return "pause"
    if LEGACY_FREE_QA_RESUME_DESCRIPTION in message and '"status":"resume"' in compact:
        return "resume"

    if '"status":"pause"' in compact and "讲解程序" in message and "暂停" in message:
        return "pause"
    if '"status":"resume"' in compact and "讲解程序" in message and "恢复" in message:
        return "resume"
    return "none"


def classify_action(message: str) -> str:
    structured = classify_structured_control_message(message)
    if structured != "none":
        return structured

    text = normalize_text(message)
    if not text:
        return "none"

    if any(phrase in text for phrase in START_PHRASES):
        return "start"

    if any(phrase in text for phrase in PAUSE_PHRASES) or text in {"暂停", "停", "停止"}:
        return "pause"

    if any(phrase in text for phrase in RESUME_PHRASES) or text in {"继续", "接着", "恢复"}:
        return "resume"

    if len(text) <= 8 and any(token in text for token in ("继续", "恢复", "接着")):
        return "resume"

    if len(text) <= 8 and any(token in text for token in ("暂停", "停一下", "稍等")):
        return "pause"

    if len(text) <= 8 and any(token in text for token in ("开始", "开讲")):
        return "start"

    return "none"


def command_for_action(action: str) -> str:
    script_path = (SCRIPT_DIR / "explain_controller.py").resolve()
    default_map = {
        "start": f"python3 {script_path} --command start",
        "pause": f"python3 {script_path} --command pause",
        "resume": f"python3 {script_path} --command resume",
    }
    env_map = {
        "start": os.environ.get("EXPLAIN_START_CMD", "").strip(),
        "pause": os.environ.get("EXPLAIN_PAUSE_CMD", "").strip(),
        "resume": os.environ.get("EXPLAIN_RESUME_CMD", "").strip(),
    }
    return env_map.get(action) or default_map[action]


def run_python_interface(action: str, session_id: str, dry_run: bool) -> tuple[bool, str]:
    cmd_text = command_for_action(action)
    if dry_run:
        return True, f"dry-run (cwd={SERVICE_ROOT_DIR}): {cmd_text}"

    try:
        cmd = shlex.split(cmd_text, posix=False)
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            cwd=SERVICE_ROOT_DIR,
        )
    except OSError as exc:
        return False, f"执行命令失败: {exc}"
    except subprocess.TimeoutExpired:
        return False, "执行超时"

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "未知错误").strip()
        return False, f"接口返回失败: {detail}"

    output = (proc.stdout or "").strip()
    if output:
        return True, output
    return True, f"{action} completed, session_id={session_id}"


def main() -> int:
    parser = argparse.ArgumentParser(description="讲解控制消息分发服务")
    parser.add_argument("--sender-jid", default="")
    parser.add_argument("--message", required=True)
    parser.add_argument("--message-id", default="")
    parser.add_argument("--session-id", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    session_id = args.session_id.strip() or str(uuid.uuid4())
    sender_jid = args.sender_jid.strip()
    message = args.message.strip()

    if not message:
        return json_out(
            build_response_payload(
                status="failed",
                action="none",
                message="消息为空",
                session_id=session_id,
                message_id=args.message_id.strip(),
                sender_jid=sender_jid,
            )
        )

    action = classify_action(message)
    if action == "none":
        return json_out(
            build_response_payload(
                status="ignored",
                action="none",
                message="未匹配到控制意图",
                session_id=session_id,
                message_id=args.message_id.strip(),
                sender_jid=sender_jid,
            )
        )

    if is_duplicate_message(args.message_id):
        return json_out(
            build_response_payload(
                status="ignored",
                action=action,
                message="重复消息，已忽略",
                session_id=session_id,
                message_id=args.message_id.strip(),
                sender_jid=sender_jid,
            )
        )

    ok, detail = run_python_interface(action=action, session_id=session_id, dry_run=args.dry_run)
    if not ok:
        return json_out(
            build_response_payload(
                status="failed",
                action=action,
                message=detail,
                session_id=session_id,
                message_id=args.message_id.strip(),
                sender_jid=sender_jid,
            )
        )

    return json_out(
        build_response_payload(
            status="success",
            action=action,
            message=detail,
            session_id=session_id,
            message_id=args.message_id.strip(),
            sender_jid=sender_jid,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
