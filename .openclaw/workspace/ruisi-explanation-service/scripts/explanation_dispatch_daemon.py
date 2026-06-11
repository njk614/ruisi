#!/usr/bin/env python3
"""讲解定时发送守护进程。

读取 runtime/explanation_state.json，并在 mode=running 时按讲解脚本表格中的
"时长(秒)"节奏发送讲解词。发送成功后推进 index，实现断点续发。
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = SCRIPT_DIR.parent / "runtime"
STATE_FILE = RUNTIME_DIR / "explanation_state.json"
LOCK_FILE = RUNTIME_DIR / "dispatcher.lock"


def log(message: str) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    print(f"[{now}] {message}", flush=True)


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        return {}
    return {}


def save_state(state: dict[str, Any]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_duration_seconds(text: str, fallback: int) -> int:
    match = re.search(r"(\d+)", text)
    if not match:
        return max(1, fallback)
    return max(1, int(match.group(1)))


def read_script_entries(path_text: str, default_interval: int) -> list[dict[str, Any]]:
    try:
        path = Path(path_text)
        if not path.exists() or not path.is_file():
            return []
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    entries: list[dict[str, Any]] = []
    in_script_table = False

    for raw in lines:
        line = raw.strip()
        if not line:
            if in_script_table and entries:
                break
            continue

        if line.startswith("|") and "页码" in line and "讲解词" in line and "时长" in line:
            in_script_table = True
            continue

        if not in_script_table:
            continue

        if not line.startswith("|"):
            if entries:
                break
            continue

        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 4:
            continue

        # 跳过分隔行
        if all(re.fullmatch(r"[-:]+", cell or "-") for cell in cells):
            continue

        page_match = re.search(r"\d+", cells[0])
        speech = cells[1].strip()
        duration_text = cells[3].strip()

        if not page_match or not speech:
            continue

        entries.append(
            {
                "page": int(page_match.group(0)),
                "speech": speech,
                "duration_seconds": parse_duration_seconds(duration_text, default_interval),
            }
        )

    return entries


def send_line(state: dict[str, Any], line: str) -> tuple[bool, str]:
    api_url = str(os.environ.get("EXPLAIN_SEND_API_URL", "http://127.0.0.1:18900/send")).strip()
    if not api_url:
        # 没配置真实发送接口时，用日志模拟发送。
        return True, f"mock-send: {line}"

    token = str(os.environ.get("EXPLAIN_SEND_API_TOKEN", "")).strip()
    target_jid = str(state.get("target_jid", "")).strip()
    sender_account = str(state.get("sender_account", "")).strip()

    if not target_jid:
        return False, "target_jid 为空"

    payload = {"jid": target_jid, "body": line}
    if sender_account:
        payload["from"] = sender_account

    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(api_url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            content = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return False, str(exc)

    if not content:
        return True, "sent"

    try:
        data = json.loads(content)
        if isinstance(data, dict) and data.get("success") is False:
            return False, str(data.get("error") or data)
        return True, "sent"
    except json.JSONDecodeError:
        return True, "sent"


def acquire_lock() -> bool:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode("utf-8"))
        os.close(fd)
        return True
    except FileExistsError:
        return False


def release_lock() -> None:
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def wait_seconds_with_pause_awareness(seconds: int) -> None:
    # 小步轮询，确保 pause/resume 后能尽快响应，不被整秒阻塞。
    remaining = max(0.0, float(seconds))
    tick = 0.2
    while remaining > 0:
        time.sleep(min(tick, remaining))
        remaining -= tick
        state = load_state()
        if str(state.get("mode", "paused")) != "running":
            break


def loop() -> None:
    if not acquire_lock():
        log("dispatcher already running, exit")
        return

    log("dispatcher started")
    try:
        while True:
            state = load_state()
            mode = str(state.get("mode", "paused"))
            interval_seconds = max(1, int(state.get("interval_seconds", 10)))

            if mode != "running":
                time.sleep(1)
                continue

            data_file = str(state.get("data_file", "")).strip()
            entries = read_script_entries(data_file, interval_seconds)
            if not entries:
                log(f"data file empty or missing: {data_file}")
                time.sleep(2)
                continue

            index = int(state.get("index", 0))
            if index >= len(entries):
                # 全部页码发送完成后仅切到 paused，不额外发送结束文案。
                state["completion_sent"] = True
                state["mode"] = "paused"
                save_state(state)
                log("all pages sent, switched to paused")
                time.sleep(1)
                continue

            current = entries[index]
            ok, detail = send_line(state, str(current["speech"]))
            if ok:
                state["index"] = index + 1
                state["completion_sent"] = False
                save_state(state)
                log(
                    f"sent page {current['page']} ({index + 1}/{len(entries)}), "
                    f"wait {current['duration_seconds']}s"
                )
                wait_seconds_with_pause_awareness(int(current["duration_seconds"]))
            else:
                log(f"send failed: {detail}")
                time.sleep(2)
    finally:
        release_lock()
        log("dispatcher stopped")


if __name__ == "__main__":
    loop()
