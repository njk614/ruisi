#!/usr/bin/env python3
"""自动演示后台推送脚本。

这个脚本由 send_message.py 在“开始演示”时拉起，独立运行在后台：
- 读取当前会议的 PresentationScript.json，并展开为按顺序推送的章节/段落列表。
- 先调用内容展示器 /api/playlist/load 加载当前会议资源包。
- 每个段落依次发送数字人模拟消息和内容展示器 /api/show 指令。
- 每段发送后按 segment.duration 等待，并在等待期间响应暂停、继续、跳转、停止命令。
- 通过 runtime/demo_state.json 持续记录当前推送状态，便于外部查询。
"""

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from send_message import build_segment_messages, display_playlist_id, format_body, load_display_playlist, send_with_retry


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TESTDATA_PATH = SKILL_ROOT / "data" / "testdata.json"
RUNTIME_DIR = SKILL_ROOT / "runtime"
STATE_PATH = RUNTIME_DIR / "demo_state.json"
COMMAND_PATH = RUNTIME_DIR / "demo_command.json"
PID_PATH = RUNTIME_DIR / "demo.pid"
PAUSE_FLAG_PATH = RUNTIME_DIR / "demo_pause.flag"
LOG_PATH = RUNTIME_DIR / "demo_runner.log"


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def wait_until_not_before(not_before):
    """等待入口脚本给 OpenClaw 返回确认消息后，再开始真实推送。"""
    if not_before is None:
        return
    try:
        target = float(not_before)
    except (TypeError, ValueError):
        return
    while True:
        remaining = target - time.time()
        if remaining <= 0:
            return
        time.sleep(min(0.1, remaining))


def ensure_runtime_dir():
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def write_json_atomic(path, payload):
    """原子写入 JSON，避免外部读取到半截状态或命令文件。"""
    ensure_runtime_dir()
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temp_path.replace(path)


def read_json_file(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def log(message):
    """写入后台演示运行日志，主要用于排查启动、发送和异常流程。"""
    ensure_runtime_dir()
    with LOG_PATH.open("a", encoding="utf-8") as file:
        file.write(f"{utc_now()} {message}\n")


def load_sequence(path):
    """读取 PresentationScript.json，并展开成可顺序推送的段落列表。"""
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    chapters = payload.get("chapters") if isinstance(payload, dict) else None
    if not isinstance(chapters, list) or not chapters:
        raise ValueError("展示序列缺少 chapters")

    items = []
    for chapter_position, chapter in enumerate(chapters):
        if not isinstance(chapter, dict):
            continue
        segments = chapter.get("segments")
        if not isinstance(segments, list):
            continue
        for segment_position, segment in enumerate(segments):
            if not isinstance(segment, dict):
                continue
            items.append(
                {
                    "chapter": chapter,
                    "segment": segment,
                    "chapter_position": chapter_position,
                    "segment_position": segment_position,
                    "chapter_index": zero_based_index(chapter.get("chapter_id"), chapter_position),
                    "segment_index": zero_based_index(segment.get("segment_id"), segment_position),
                }
            )
    if not items:
        raise ValueError("展示序列没有可用 segments")
    return items


def zero_based_index(value, fallback):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return number - 1 if number > 0 else fallback


def find_item_index(items, chapter_index, segment_index=0):
    """根据内容展示器数组下标定位目标段落；找不到段落时退到该章节第一段。"""
    for index, item in enumerate(items):
        if item["chapter_index"] == chapter_index and item["segment_index"] == segment_index:
            return index
    for index, item in enumerate(items):
        if item["chapter_index"] == chapter_index:
            return index
    return None


def state_payload(status, item=None, message=None, remaining_duration=None):
    """构造 demo_state.json 内容，记录当前章节、段落、文本和剩余等待时间。"""
    payload = {
        "status": status,
        "pid": os.getpid(),
        "updated_at": utc_now(),
    }
    if item is not None:
        chapter = item["chapter"]
        segment = item["segment"]
        payload.update(
            {
                "chapter_index": item["chapter_index"],
                "segment_index": item["segment_index"],
                "chapter_id": chapter.get("chapter_id"),
                "segment_id": segment.get("segment_id"),
                "chapter_topic": chapter.get("chapter_topic"),
                "text": segment.get("text"),
                "duration": segment.get("duration"),
                "audio": segment.get("audio"),
                "performance_code": segment.get("performance_code"),
            }
        )
    if remaining_duration is not None:
        payload["remaining_duration"] = max(0, round(float(remaining_duration), 3))
    if message:
        payload["message"] = message
    return payload


def write_state(status, item=None, message=None, remaining_duration=None):
    write_json_atomic(STATE_PATH, state_payload(status, item=item, message=message, remaining_duration=remaining_duration))


def read_command(last_command_id):
    """读取入口脚本写入的最新控制命令，并避免重复执行同一条命令。"""
    command = read_json_file(COMMAND_PATH)
    if not isinstance(command, dict):
        return None, last_command_id
    command_id = command.get("id") or command.get("updated_at")
    if not command_id or command_id == last_command_id:
        return None, last_command_id
    return command, command_id


def current_command_id():
    command = read_json_file(COMMAND_PATH)
    if not isinstance(command, dict):
        return None
    return command.get("id") or command.get("updated_at")


def is_pause_flag_set():
    """硬暂停标记：入口脚本写入后，后台会在多个检查点立即停止后续推送。"""
    return PAUSE_FLAG_PATH.exists()


def clear_pause_flag():
    try:
        PAUSE_FLAG_PATH.unlink()
    except FileNotFoundError:
        pass


def apply_command_not_before(command):
    if isinstance(command, dict):
        wait_until_not_before(command.get("not_before"))


def send_item(item, dry_run=False):
    """发送当前段落对应的两类消息：数字人模拟消息和内容展示器 show 指令。"""
    messages = build_segment_messages(item["chapter"], item["segment"])
    if dry_run:
        for prefix, message in messages:
            if is_pause_flag_set():
                return "paused"
            log(f"DRY_RUN {format_body(prefix, message)}")
        return True

    for prefix, message in messages:
        if is_pause_flag_set():
            return "paused"
        ok, detail = send_with_retry(prefix, message)
        if not ok:
            log(f"SEND_FAILED detail={detail}")
            return False
    return True


def load_playlist_before_demo(dry_run=False, playlist_id=None):
    """自动演示开始前，先让内容展示器加载当前会议的 playlist。"""
    playlist_id = playlist_id or display_playlist_id()
    if dry_run:
        log(f"DRY_RUN LOAD_PLAYLIST playlist_id={playlist_id}")
        return True
    try:
        response = load_display_playlist(playlist_id)
    except Exception as exc:
        log(f"LOAD_PLAYLIST_FAILED detail={exc}")
        return False
    if response.get("success") is True:
        log(f"LOAD_PLAYLIST_OK playlist_id={playlist_id}")
        return True
    log(f"LOAD_PLAYLIST_FAILED response={response}")
    return False


def command_target_index(command, items, current_index):
    """把 jump 命令中的章节/段落下标转换成 items 列表下标。"""
    command_name = command.get("command")
    if command_name != "jump":
        return current_index
    try:
        chapter_index = int(command.get("chapter_index"))
    except (TypeError, ValueError):
        return current_index
    try:
        segment_index = int(command.get("segment_index", 0))
    except (TypeError, ValueError):
        segment_index = 0
    target_index = find_item_index(items, chapter_index, segment_index)
    return current_index if target_index is None else target_index


def wait_for_resume_or_jump(items, current_index, last_command_id):
    """暂停状态下阻塞等待继续、跳转或停止命令。"""
    item = items[current_index] if 0 <= current_index < len(items) else None
    while True:
        command, last_command_id = read_command(last_command_id)
        if command:
            name = command.get("command")
            if name == "resume":
                clear_pause_flag()
                apply_command_not_before(command)
                write_state("running", item=item, message="resumed")
                return current_index, last_command_id, "resume"
            if name == "jump":
                clear_pause_flag()
                apply_command_not_before(command)
                target_index = command_target_index(command, items, current_index)
                return target_index, last_command_id, "jump"
            if name == "stop":
                clear_pause_flag()
                return current_index, last_command_id, "stop"
        time.sleep(0.2)


def pause_if_requested(items, current_index, last_command_id, message="paused"):
    """如果入口脚本设置了暂停标记，就进入暂停等待流程。"""
    if not is_pause_flag_set():
        return current_index, last_command_id, None
    item = items[current_index] if 0 <= current_index < len(items) else None
    write_state("paused", item=item, message=message)
    current_index, last_command_id, action = wait_for_resume_or_jump(items, current_index, last_command_id)
    return current_index, last_command_id, action


def wait_duration(items, current_index, duration, last_command_id):
    """按当前段落 duration 等待，同时轮询暂停、跳转、停止命令。"""
    remaining = max(0.0, float(duration or 0))
    item = items[current_index]
    last_tick = time.monotonic()
    while remaining > 0:
        if is_pause_flag_set():
            write_state("paused", item=item, message="paused", remaining_duration=remaining)
            current_index, last_command_id, action = wait_for_resume_or_jump(items, current_index, last_command_id)
            if action == "stop":
                return current_index, last_command_id, "stop"
            if action == "jump":
                return current_index, last_command_id, "jump"
            item = items[current_index]
            last_tick = time.monotonic()

        command, last_command_id = read_command(last_command_id)
        if command:
            name = command.get("command")
            if name == "pause":
                write_state("paused", item=item, message="paused", remaining_duration=remaining)
                current_index, last_command_id, action = wait_for_resume_or_jump(items, current_index, last_command_id)
                if action == "stop":
                    return current_index, last_command_id, "stop"
                if action == "jump":
                    return current_index, last_command_id, "jump"
                item = items[current_index]
                last_tick = time.monotonic()
            elif name == "jump":
                clear_pause_flag()
                apply_command_not_before(command)
                target_index = command_target_index(command, items, current_index)
                return target_index, last_command_id, "jump"
            elif name == "stop":
                clear_pause_flag()
                return current_index, last_command_id, "stop"

        time.sleep(min(0.2, remaining))
        now = time.monotonic()
        remaining -= now - last_tick
        last_tick = now
        write_state("running", item=item, message="waiting", remaining_duration=remaining)
    return current_index + 1, last_command_id, "next"


def run_demo(args):
    """后台演示主循环：加载脚本、逐段发送、按 duration 推进。"""
    ensure_runtime_dir()
    PID_PATH.write_text(str(os.getpid()), encoding="utf-8")
    log(f"BOOT pid={os.getpid()} data={args.data} dry_run={args.dry_run}")
    write_state("starting", message="loading sequence")
    items = load_sequence(args.data)
    if not load_playlist_before_demo(dry_run=args.dry_run, playlist_id=args.playlist_id):
        write_state("failed", message="load playlist failed")
        return 1
    start_index = find_item_index(items, args.start_chapter_index, args.start_segment_index)
    if start_index is None and args.require_start_target:
        write_state("failed", message="start target not found")
        log(f"START_TARGET_NOT_FOUND chapter_index={args.start_chapter_index} segment_index={args.start_segment_index}")
        return 1
    current_index = 0 if start_index is None else start_index
    last_command_id = current_command_id()
    write_state("running", item=items[current_index], message="started")
    log(f"START pid={os.getpid()} index={current_index} dry_run={args.dry_run}")
    wait_until_not_before(args.not_before)

    while current_index < len(items):
        command, last_command_id = read_command(last_command_id)
        if command:
            name = command.get("command")
            if name == "pause":
                write_state("paused", item=items[current_index], message="paused before send")
                current_index, last_command_id, action = wait_for_resume_or_jump(items, current_index, last_command_id)
                if action == "stop":
                    break
            elif name == "jump":
                clear_pause_flag()
                apply_command_not_before(command)
                current_index = command_target_index(command, items, current_index)
            elif name == "stop":
                clear_pause_flag()
                break

        current_index, last_command_id, action = pause_if_requested(items, current_index, last_command_id, message="paused before send")
        if action == "stop":
            break
        if action == "jump":
            continue

        item = items[current_index]
        write_state("running", item=item, message="sending")
        send_result = send_item(item, dry_run=args.dry_run)
        if send_result == "paused":
            write_state("paused", item=item, message="paused during send")
            current_index, last_command_id, action = wait_for_resume_or_jump(items, current_index, last_command_id)
            if action == "stop":
                break
            if action == "jump":
                continue
            item = items[current_index]
            write_state("running", item=item, message="sending")
            send_result = send_item(item, dry_run=args.dry_run)
        if not send_result:
            write_state("failed", item=item, message="send failed")
            return 1

        duration = item["segment"].get("duration") or 0
        next_index, last_command_id, action = wait_duration(items, current_index, duration, last_command_id)
        if action == "stop":
            write_state("stopped", item=item, message="stopped")
            return 0
        current_index = next_index

    write_state("completed", message="demo completed")
    log("COMPLETED")
    return 0


def parse_args():
    parser = argparse.ArgumentParser(description="按演示脚本 duration 自动推送数字人消息和内容展示器指令。")
    parser.add_argument("--data", default=str(DEFAULT_TESTDATA_PATH), help="Path to demo sequence JSON.")
    parser.add_argument("--playlist-id", help="Content display playlist_id. Defaults to CONTENT_DISPLAY_PLAYLIST_ID.")
    parser.add_argument("--start-chapter-index", type=int, default=0)
    parser.add_argument("--start-segment-index", type=int, default=0)
    parser.add_argument("--require-start-target", action="store_true", help="Fail instead of falling back to the first segment when the start target is missing.")
    parser.add_argument("--not-before", type=float)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main():
    try:
        return run_demo(parse_args())
    except Exception as exc:
        ensure_runtime_dir()
        write_state("failed", message=str(exc))
        log(f"FAILED {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
