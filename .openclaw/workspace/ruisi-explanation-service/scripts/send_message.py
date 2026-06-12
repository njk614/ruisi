#!/usr/bin/env python3
"""ruisi-explanation-service 的消息入口脚本。

这个脚本由 OpenClaw 或其他 Skill 调用，负责识别自然语言/JSON 指令：
- “开始演示”时启动后台 run_demo_sequence.py，按会议脚本自动推送讲解。
- “暂停/继续/停止/跳转”时写入 runtime 控制文件，让后台进程响应。
- 收到单段 chapters 数据时，立即构造数字人消息并调用内容展示器。
- 数字人消息仍通过 P02/XMPP 模拟发送；内容展示器通过 HTTP API 真实调用。
"""

import argparse
import ctypes
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_API_URL = "http://127.0.0.1:18900/send"
DEFAULT_TO_JID = "niujunke@im.tuguan.net"
DEFAULT_FROM_ACCOUNT = "a01@im.tuguan.net"
DEFAULT_DISPLAY_BASE_URL = "http://172.16.1.138:8088"
DEFAULT_TESTDATA_PATH = Path(__file__).resolve().parents[1] / "data" / "testdata.json"
DEFAULT_PRESET_MEETING_DATA_DIR = Path("/home/clawd/.openclaw/workspace/SimulatedData/PresetMeetingData")
DEFAULT_MEETING_ROOM_NAME = "大会议室"
DEFAULT_AUDIO_BASE_URL = "http://192.168.1.254:8888/PresetMeetingData/"
DEFAULT_ACK_DELAY_SECONDS = 2.0

# runtime 目录保存后台演示进程的状态、控制命令、暂停标记和 pid。
SKILL_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = SKILL_ROOT / "runtime"
STATE_PATH = RUNTIME_DIR / "demo_state.json"
COMMAND_PATH = RUNTIME_DIR / "demo_command.json"
PID_PATH = RUNTIME_DIR / "demo.pid"
PAUSE_FLAG_PATH = RUNTIME_DIR / "demo_pause.flag"
RUNNER_PATH = Path(__file__).resolve().parent / "run_demo_sequence.py"

# 内部通道标识，仅用于决定消息走 P02/XMPP 还是内容展示器 HTTP API。
DIGITAL_HUMAN_CHANNEL = "digital_human"
CONTENT_DISPLAY_CHANNEL = "content_display"

CHINESE_NUMBERS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


# 这些演示控制成功提示暂时不返回到界面：开始/暂停/恢复/跳转/停止成功时
# 静默处理，stdout 不输出。失败提示与其他成功提示（如“讲解已推送”“演示状态”）不受影响。
SILENCED_SUCCESS_MESSAGES = {
    "演示已开始",
    "演示已暂停",
    "演示已恢复",
    "正在跳转指定章节",
    "演示已停止",
}


def result(status, message):
    if status == "success" and message in SILENCED_SUCCESS_MESSAGES:
        return
    print(json.dumps({"status": status, "message": message}, ensure_ascii=False, separators=(",", ":")))


def normalized_json(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def parse_args():
    parser = argparse.ArgumentParser(description="接收 OpenClaw 传入的讲解控制消息，并分发到后台演示/P02/内容展示器。")
    parser.add_argument("--payload", help="Raw JSON or natural language command. If omitted, stdin is used.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and build messages without sending.")
    parser.add_argument("--print-messages", action="store_true", help="Print built P02 message bodies in dry-run mode.")
    parser.add_argument("--demo-dry-run", action="store_true", help="Start auto demo runner in dry-run mode.")
    return parser.parse_args()


def utc_timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def now_epoch():
    return time.time()


def ack_delay_seconds():
    value = os.environ.get("DEMO_ACK_DELAY_SECONDS")
    if value is None:
        return DEFAULT_ACK_DELAY_SECONDS
    try:
        return max(0.0, float(value))
    except ValueError:
        return DEFAULT_ACK_DELAY_SECONDS


def not_before_timestamp():
    return now_epoch() + ack_delay_seconds()


def testdata_path():
    configured = os.environ.get("SIM_TESTDATA_PATH")
    return Path(configured) if configured else DEFAULT_TESTDATA_PATH


def preset_meeting_data_dir():
    configured = os.environ.get("PRESET_MEETING_DATA_DIR")
    return Path(configured) if configured else DEFAULT_PRESET_MEETING_DATA_DIR


def meeting_index_path():
    configured = os.environ.get("MEETING_INDEX_PATH")
    return Path(configured) if configured else preset_meeting_data_dir() / "meeting_index.json"


def meeting_room_name():
    return os.environ.get("MEETING_ROOM_NAME") or DEFAULT_MEETING_ROOM_NAME


def audio_base_url():
    return os.environ.get("DIGITAL_HUMAN_AUDIO_BASE_URL") or DEFAULT_AUDIO_BASE_URL


def display_base_url():
    return (os.environ.get("CONTENT_DISPLAY_BASE_URL") or DEFAULT_DISPLAY_BASE_URL).rstrip("/")


def display_playlist_id():
    return os.environ.get("CONTENT_DISPLAY_PLAYLIST_ID") or None


def parse_local_datetime(value):
    return datetime.strptime(value.strip(), "%Y-%m-%d %H:%M")


def current_local_datetime():
    override = os.environ.get("SIM_CURRENT_TIME")
    if override:
        return parse_local_datetime(override)
    return datetime.now().replace(tzinfo=None)


def parse_time_range(time_range):
    if not isinstance(time_range, str) or "~" not in time_range:
        return None, None
    start_text, end_text = time_range.split("~", 1)
    start_at = parse_local_datetime(start_text)
    end_text = end_text.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}$", end_text):
        end_at = parse_local_datetime(end_text)
    else:
        end_time = datetime.strptime(end_text, "%H:%M").time()
        end_at = datetime.combine(start_at.date(), end_time)
    return start_at, end_at


def resolve_meeting_path(base_dir, path_value):
    path = Path(path_value)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def find_current_meeting():
    """从 meeting_index.json 中找出当前时间正在大会议室进行的会议。"""
    index_path = meeting_index_path()
    base_dir = index_path.parent
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        return None, f"读取会议索引失败: {exc}"
    except json.JSONDecodeError:
        return None, "会议索引 JSON 格式无效"

    meetings = payload.get("meetings") if isinstance(payload, dict) else None
    if not isinstance(meetings, list):
        return None, "会议索引缺少 meetings"

    now = current_local_datetime()
    room = meeting_room_name()
    matches = []
    for meeting in meetings:
        if not isinstance(meeting, dict):
            continue
        if str(meeting.get("meeting_region") or "").strip() != room:
            continue
        try:
            start_at, end_at = parse_time_range(meeting.get("time_range"))
        except ValueError:
            continue
        if start_at and end_at and start_at <= now <= end_at:
            matches.append(meeting)

    if not matches:
        return None, f"当前{room}没有正在进行的会议"
    meeting = matches[0]
    booking_id = str(meeting.get("booking_id") or "").strip()
    script_rel = str(meeting.get("presentation_script_path") or "").strip()
    if not booking_id:
        return None, "匹配会议缺少 booking_id"
    if not script_rel:
        script_path = (base_dir / booking_id / "PresentationScript.json").resolve()
    else:
        script_path = resolve_meeting_path(base_dir, script_rel)
    return {"meeting": meeting, "booking_id": booking_id, "script_path": script_path}, None


def full_audio_url(audio):
    """把脚本里的音频相对路径补成数字人可访问的完整 URL。"""
    if audio is None:
        return ""
    audio_text = str(audio).strip()
    if not audio_text:
        return ""
    if re.match(r"^https?://", audio_text, flags=re.IGNORECASE):
        return audio_text
    return audio_base_url().rstrip("/") + "/" + audio_text.lstrip("/").replace("\\", "/")


def ensure_runtime_dir():
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def write_json_atomic(path, payload):
    ensure_runtime_dir()
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temp_path.replace(path)


def read_json_file(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def read_demo_state():
    state = read_json_file(STATE_PATH)
    return state if isinstance(state, dict) else {}


def is_process_alive(pid):
    try:
        pid_number = int(pid)
    except (TypeError, ValueError):
        return False
    if pid_number <= 0:
        return False
    if os.name == "nt":
        process_query_limited_information = 0x1000
        still_active = 259
        handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, pid_number)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == still_active
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid_number, 0)
        return True
    except OSError:
        return False


def terminate_process(pid):
    try:
        pid_number = int(pid)
    except (TypeError, ValueError):
        return False
    if pid_number <= 0:
        return False
    if not is_process_alive(pid_number):
        return True
    try:
        if os.name == "nt":
            handle = ctypes.windll.kernel32.OpenProcess(0x0001, False, pid_number)
            if not handle:
                return False
            try:
                return bool(ctypes.windll.kernel32.TerminateProcess(handle, 0))
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        os.kill(pid_number, 15)
        return True
    except OSError:
        return False


def is_runner_status_active(status):
    return status in {"starting", "running", "paused"}


def is_demo_active(state):
    """判断后台演示进程是否仍处于可控制状态。"""
    return is_runner_status_active(state.get("status")) and is_process_alive(state.get("pid"))


def write_demo_command(command, **kwargs):
    """写入控制命令，后台 run_demo_sequence.py 会轮询读取这个文件。"""
    payload = {
        "id": utc_timestamp(),
        "command": command,
        "updated_at": utc_timestamp(),
        "not_before": not_before_timestamp(),
    }
    payload.update(kwargs)
    write_json_atomic(COMMAND_PATH, payload)


def write_demo_state(payload):
    state = read_demo_state()
    state.update(payload)
    state["updated_at"] = utc_timestamp()
    write_json_atomic(STATE_PATH, state)


def set_pause_flag(enabled):
    ensure_runtime_dir()
    if enabled:
        PAUSE_FLAG_PATH.write_text(utc_timestamp(), encoding="utf-8")
        return
    try:
        PAUSE_FLAG_PATH.unlink()
    except FileNotFoundError:
        pass


def remove_runtime_file(path):
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def reset_runtime_commands():
    remove_runtime_file(COMMAND_PATH)
    remove_runtime_file(PAUSE_FLAG_PATH)


def pause_active_demo_temporarily():
    """入口收到任何消息时先临时暂停自动推送，避免边解析边继续发下一段。"""
    state = read_demo_state()
    if is_demo_active(state):
        set_pause_flag(True)
        write_demo_command("pause", reason="incoming_message")
        return True
    return False


def sequence_has_start_target(script_path, chapter_index, segment_index=0):
    """启动到指定章节前先做一次同步校验，避免目标不存在时回退推送第一章。"""
    try:
        payload = json.loads(Path(script_path).read_text(encoding="utf-8-sig"))
    except OSError as exc:
        return False, f"读取演示脚本失败: {exc}"
    except json.JSONDecodeError:
        return False, "演示脚本 JSON 格式无效"

    chapters = payload.get("chapters") if isinstance(payload, dict) else None
    if not isinstance(chapters, list) or not chapters:
        return False, "演示脚本缺少 chapters"

    for chapter_position, chapter in enumerate(chapters):
        if not isinstance(chapter, dict):
            continue
        current_chapter_index = number_to_zero_based_index(chapter.get("chapter_id"), chapter_position)
        if current_chapter_index != chapter_index:
            continue
        segments = chapter.get("segments")
        if not isinstance(segments, list) or not segments:
            return False, "指定章节缺少可用段落"
        for segment_position, segment in enumerate(segments):
            if not isinstance(segment, dict):
                continue
            current_segment_index = number_to_zero_based_index(segment.get("segment_id"), segment_position)
            if current_segment_index == segment_index:
                return True, None
        if segment_index == 0:
            return True, None
        return False, "指定章节缺少指定段落"
    return False, "未找到指定章节"


def start_demo_runner(dry_run=False, chapter_index=0, segment_index=0, require_start_target=False):
    """根据当前会议动态定位 PresentationScript.json，并启动后台自动演示进程。"""
    ensure_runtime_dir()
    state = read_demo_state()
    if is_demo_active(state):
        write_demo_command("stop", reason="restart")
        time.sleep(0.5)
    reset_runtime_commands()
    meeting_info, error = find_current_meeting()
    if error:
        return "failed", error
    script_path = Path(meeting_info["script_path"])
    if not script_path.exists():
        return "failed", f"演示脚本不存在: {script_path}"
    if require_start_target:
        target_exists, target_error = sequence_has_start_target(script_path, chapter_index, segment_index)
        if not target_exists:
            return "failed", target_error
    playlist_id = meeting_info["booking_id"]

    command = [
        sys.executable,
        str(RUNNER_PATH),
        "--data",
        str(script_path),
        "--playlist-id",
        playlist_id,
        "--start-chapter-index",
        str(chapter_index),
        "--start-segment-index",
        str(segment_index),
        "--not-before",
        str(not_before_timestamp()),
    ]
    if dry_run:
        command.append("--dry-run")
    if require_start_target:
        command.append("--require-start-target")

    stdout_path = RUNTIME_DIR / "demo_runner.stdout.log"
    stderr_path = RUNTIME_DIR / "demo_runner.stderr.log"
    stdout = stdout_path.open("a", encoding="utf-8")
    stderr = stderr_path.open("a", encoding="utf-8")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if os.name == "nt":
        creationflags |= getattr(subprocess, "DETACHED_PROCESS", 0)
        creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    try:
        process = subprocess.Popen(
            command,
            cwd=str(SKILL_ROOT),
            stdout=stdout,
            stderr=stderr,
            stdin=subprocess.DEVNULL,
            close_fds=True,
            creationflags=creationflags,
        )
    finally:
        stdout.close()
        stderr.close()

    PID_PATH.write_text(str(process.pid), encoding="utf-8")
    return "success", "演示已开始"


def control_demo(command, demo_dry_run=False, **kwargs):
    """处理暂停、继续、跳转、停止等运行中控制命令。"""
    state = read_demo_state()
    if command == "jump" and not is_demo_active(state) and state.get("status") == "completed":
        status, message = start_demo_runner(
            dry_run=demo_dry_run,
            chapter_index=kwargs.get("chapter_index", 0),
            segment_index=kwargs.get("segment_index", 0),
            require_start_target=True,
        )
        if status == "success":
            return "success", "正在跳转指定章节"
        return status, message
    if command in {"pause", "resume", "jump", "stop"} and not is_demo_active(state):
        return "failed", "当前没有正在运行的演示"
    if command == "pause":
        set_pause_flag(True)
    elif command in {"resume", "jump", "stop"}:
        set_pause_flag(False)
    write_demo_command(command, **kwargs)
    if command == "stop":
        stop_demo_process(state)
        stop_content_display()
    messages = {
        "pause": "演示已暂停",
        "resume": "演示已恢复",
        "jump": "正在跳转指定章节",
        "stop": "演示已停止",
    }
    return "success", messages.get(command, "演示控制指令已发送")


def stop_demo_process(initial_state):
    """停止后台演示进程，并清理命令、暂停标记和 pid 文件。"""
    pid = initial_state.get("pid")
    deadline = time.time() + 2.0
    while time.time() < deadline:
        if not is_process_alive(pid):
            write_demo_state({"status": "stopped", "message": "演示已停止"})
            cleanup_runtime_control_files(keep_state=True)
            return True
        time.sleep(0.1)
    terminated = terminate_process(pid)
    time.sleep(0.2)
    if terminated and not is_process_alive(pid):
        write_demo_state({"status": "stopped", "message": "演示进程已关闭"})
        cleanup_runtime_control_files(keep_state=True)
        return True
    write_demo_state({"status": "stopping", "message": "已发送停止命令，进程仍在退出中"})
    return False


def cleanup_runtime_control_files(keep_state=True):
    remove_runtime_file(COMMAND_PATH)
    remove_runtime_file(PAUSE_FLAG_PATH)
    if not keep_state:
        remove_runtime_file(STATE_PATH)
    remove_runtime_file(PID_PATH)


def demo_status_result():
    state = read_demo_state()
    if not state:
        print(json.dumps({"status": "success", "message": "暂无演示状态", "state": {}}, ensure_ascii=False, separators=(",", ":")))
        return 0
    if is_runner_status_active(state.get("status")) and not is_process_alive(state.get("pid")):
        state = dict(state)
        state["status"] = "stale"
        state["message"] = "演示进程已退出，状态文件为历史记录"
    print(json.dumps({"status": "success", "message": "演示状态", "state": state}, ensure_ascii=False, separators=(",", ":")))
    return 0


def format_body(channel, message):
    """把数字人模拟消息格式化成发给 P02 的 JSON 文本。"""
    if isinstance(message, str):
        return message
    return normalized_json(message)


def try_load_json(raw):
    payload = load_json_like(raw)
    return payload if isinstance(payload, dict) else None


def load_json_like(raw):
    """兼容用户只粘贴 `"chapters": [...]` 片段而不是完整 JSON 对象的情况。"""
    candidates = [raw]
    stripped = raw.strip()
    if not stripped.startswith("{") and '"chapters"' in stripped:
        candidates.append("{" + stripped + "}")

    for candidate in candidates:
        normalized = re.sub(r",(\s*[}\]])", r"\1", candidate.strip())
        try:
            return json.loads(normalized)
        except json.JSONDecodeError:
            continue
    return None


def require_string(payload, key):
    value = payload.get(key)
    if value is None or str(value).strip() == "":
        return None
    return str(value).strip()


def require_present(payload, key):
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def build_segment_messages(chapter, segment):
    """从章节/段落中提取数字人消息和内容展示器 show 指令。"""
    chapter_id = chapter.get("chapter_id")
    segment_id = segment.get("segment_id")
    performance_code = segment.get("performance_code") or ""
    action_prefix = f"[action:{performance_code}]" if performance_code else ""
    digital_human_message = {
        "messagetype": "bot",
        "data": {
            "messageId": f"section-{chapter_id}-{segment_id}",
            "text": f"{action_prefix}{segment.get('text') or ''}",
            "duration": segment.get("duration"),
            "audioUrl": full_audio_url(segment.get("audio")),
        },
    }
    display_message = {
        "chapter_index": number_to_zero_based_index(chapter_id, 0),
        "segment_index": number_to_zero_based_index(segment_id, 0),
        "show_subtitle": True,
    }
    return [(DIGITAL_HUMAN_CHANNEL, digital_human_message), (CONTENT_DISPLAY_CHANNEL, display_message)]


def number_to_zero_based_index(value, fallback):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    if number <= 0:
        return fallback
    return number - 1


def load_testdata():
    path = testdata_path()
    try:
        with path.open("r", encoding="utf-8-sig") as file:
            payload = json.load(file)
    except OSError as exc:
        return None, f"读取测试序列失败: {exc}"
    except json.JSONDecodeError:
        return None, "测试序列 JSON 格式无效"

    chapters = payload.get("chapters") if isinstance(payload, dict) else None
    if not isinstance(chapters, list) or not chapters:
        return None, "测试序列缺少 chapters"
    return chapters, None


def first_segment_for_chapter(chapter):
    segments = chapter.get("segments")
    if not isinstance(segments, list) or not segments:
        return None
    segment = segments[0]
    return segment if isinstance(segment, dict) else None


def find_chapter_by_number(chapters, chapter_number):
    for index, chapter in enumerate(chapters):
        if not isinstance(chapter, dict):
            continue
        if chapter.get("chapter_id") == chapter_number:
            return chapter
        if index + 1 == chapter_number:
            return chapter
    return None


def normalize_keyword(text):
    return re.sub(r"[\s，。,.、：:（）()《》\"'“”‘’\-_]+", "", text or "").lower()


def find_chapter_by_keyword(chapters, text):
    compact = normalize_keyword(text)
    best = None
    best_score = 0
    for chapter in chapters:
        if not isinstance(chapter, dict):
            continue
        topic = normalize_keyword(str(chapter.get("chapter_topic") or ""))
        if not topic:
            continue
        score = 0
        if topic in compact or compact in topic:
            score = len(topic)
        else:
            for token in re.split(r"[-_：:（）()]+", str(chapter.get("chapter_topic") or "")):
                token = normalize_keyword(token)
                if len(token) >= 2 and token in compact:
                    score = max(score, len(token))
        if score > best_score:
            best = chapter
            best_score = score
    return best


def build_messages_from_testdata(chapter_number=None, keyword=None):
    chapters, error = load_testdata()
    if error:
        return None, error

    chapter = None
    if chapter_number is not None:
        chapter = find_chapter_by_number(chapters, chapter_number)
    if chapter is None and keyword:
        chapter = find_chapter_by_keyword(chapters, keyword)
    if chapter is None:
        return None, "未找到匹配章节"

    segment = first_segment_for_chapter(chapter)
    if segment is None:
        return None, "匹配章节缺少可用段落"
    return build_segment_messages(chapter, segment), None


def build_chapters_messages(raw, payload):
    """处理手动输入的 chapters 数据块，只取第一章第一段做一次即时推送。"""
    chapters = payload.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        return None, "chapters 必须是非空数组"

    chapter = chapters[0]
    if not isinstance(chapter, dict):
        return None, "chapter 必须是对象"

    segments = chapter.get("segments")
    if not isinstance(segments, list) or not segments:
        return None, "segments 必须是非空数组"

    segment = segments[0]
    if not isinstance(segment, dict):
        return None, "segment 必须是对象"

    return build_segment_messages(chapter, segment), None


def chinese_number_to_int(text):
    if text is None:
        return None
    text = text.strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)
    if text in CHINESE_NUMBERS:
        return CHINESE_NUMBERS[text]
    if text.startswith("十") and len(text) == 2:
        tail = CHINESE_NUMBERS.get(text[1])
        return 10 + tail if tail is not None else None
    if text.endswith("十") and len(text) == 2:
        head = CHINESE_NUMBERS.get(text[0])
        return head * 10 if head is not None else None
    if "十" in text and len(text) == 3:
        head = CHINESE_NUMBERS.get(text[0])
        tail = CHINESE_NUMBERS.get(text[2])
        if head is not None and tail is not None:
            return head * 10 + tail
    return None


def extract_chapter_number(text):
    match = re.search(r"第\s*([0-9]+|[零一二两三四五六七八九十]{1,3})\s*[章节页]", text)
    if not match:
        return None
    number = chinese_number_to_int(match.group(1))
    if number is None or number <= 0:
        return None
    return number


def build_demo_control(text, demo_dry_run=False):
    """识别开始、暂停、继续、停止、跳转等自然语言演示控制意图。"""
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return None

    chapter_number = extract_chapter_number(compact)
    if chapter_number is not None and re.search(r"(跳|跳转|切换|切到|转到|到|看|看看|播放|讲)", compact):
        return control_demo("jump", demo_dry_run=demo_dry_run, chapter_index=chapter_number - 1, segment_index=0)

    if re.search(r"(开始演示|启动演示|开始讲解|启动讲解|开始播放演示|播放演示)", compact):
        return start_demo_runner(dry_run=demo_dry_run)

    if re.search(r"(暂停演示|暂停讲解|暂停播放|暂停|先停|停一下|别讲|别放)", compact):
        return control_demo("pause")

    if re.search(r"(继续演示|继续讲解|继续播放|继续|接着讲|接着放|恢复演示|恢复播放)", compact):
        return control_demo("resume")

    if re.search(r"(停止演示|结束演示|停止讲解|结束讲解|退出演示|停止播放)", compact):
        return control_demo("stop")

    if re.search(r"(演示状态|当前演示|发送到哪|推送到哪|讲到哪)", compact):
        return ("status", "演示状态")

    return None


def build_natural_language_message(text):
    """处理非演示控制类自然语言，当前主要用于按章节查找并即时推送一段。"""
    compact = re.sub(r"\s+", "", text)
    if not compact:
        return None, "无效的指令内容"

    chapter_number = extract_chapter_number(compact)
    if chapter_number is not None and re.search(r"(跳|跳转|切换|看|看看|讲|播放|到)", compact):
        return build_messages_from_testdata(chapter_number=chapter_number)

    if re.search(r"(跳|跳转|切换|切到|转到|看|看看|讲|播放|到).+", compact):
        messages, error = build_messages_from_testdata(keyword=compact)
        if messages is not None:
            return messages, None

    return None, "无法识别控制意图"


def build_messages(raw):
    payload = try_load_json(raw)
    if payload is not None:
        if "chapters" in payload:
            return build_chapters_messages(raw, payload)
        return None, "无法识别 JSON 指令结构"
    return build_natural_language_message(raw)


def post_json(url, payload, token=None, timeout=5):
    """发送 JSON POST 请求，供 XMPP 发送接口和内容展示器 HTTP API 共用。"""
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content = response.read().decode("utf-8")
    if not content:
        return {}
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {"raw": content}


def post_display_api(path, payload, timeout=5):
    url = f"{display_base_url()}{path}"
    return post_json(url, payload, timeout=timeout)


def load_display_playlist(playlist_id=None):
    resolved_playlist_id = playlist_id or display_playlist_id()
    if not resolved_playlist_id:
        raise ValueError("缺少内容展示器 playlist_id")
    return post_display_api("/api/playlist/load", {"playlist_id": resolved_playlist_id})


def show_display_segment(message):
    return post_display_api("/api/show", message)


def stop_content_display():
    """停止内容展示器当前显示内容，让大屏回到未加载/待机状态。"""
    try:
        response = post_display_api("/api/stop", {})
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        write_demo_state({"content_display_stop": "failed", "content_display_stop_detail": str(exc)})
        return False, str(exc)
    if response.get("success") is True:
        write_demo_state({"content_display_stop": "success"})
        return True, response
    write_demo_state({"content_display_stop": "failed", "content_display_stop_detail": response})
    return False, response


def send_with_retry(channel, message):
    """按消息类型选择发送通道：内容展示器走 HTTP，数字人模拟消息走 P02/XMPP。"""
    if channel == CONTENT_DISPLAY_CHANNEL:
        last_error = None
        for attempt in range(2):
            try:
                response = show_display_segment(message)
                if response.get("success") is True:
                    return True, response
                last_error = response
            except (OSError, urllib.error.URLError, TimeoutError) as exc:
                last_error = str(exc)
            if attempt == 0:
                time.sleep(0.3)
        return False, last_error

    api_url = os.environ.get("XMPP_SEND_API_URL") or DEFAULT_API_URL
    to_jid = os.environ.get("P02_JID") or DEFAULT_TO_JID
    from_account = os.environ.get("XMPP_FROM_ACCOUNT") or DEFAULT_FROM_ACCOUNT
    token = os.environ.get("XMPP_SEND_API_TOKEN") or None
    request_payload = {
        "jid": to_jid,
        "body": format_body(channel, message),
        "from": from_account,
    }

    last_error = None
    for attempt in range(2):
        try:
            response = post_json(api_url, request_payload, token=token)
            if response.get("success") is True:
                return True, response
            last_error = response.get("error") or response
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            last_error = str(exc)
        if attempt == 0:
            time.sleep(0.3)
    return False, last_error


def main():
    """脚本主入口：先暂停运行中演示，再解析并执行当前消息。"""
    args = parse_args()
    raw = args.payload if args.payload is not None else sys.stdin.read()
    if not raw or not raw.strip():
        result("failed", "无效的指令内容")
        return 1

    pause_active_demo_temporarily()

    demo_control = build_demo_control(raw.strip(), demo_dry_run=args.demo_dry_run)
    if demo_control is not None:
        status, message = demo_control
        if status == "status":
            return demo_status_result()
        result(status, message)
        return 0 if status == "success" else 1

    messages, error = build_messages(raw.strip())
    if error:
        result("failed", error)
        return 1

    if args.dry_run and args.print_messages:
        built = [{"channel": channel, "body": format_body(channel, message)} for channel, message in messages]
        print(json.dumps({"status": "success", "message": "讲解已推送", "bodies": built}, ensure_ascii=False, separators=(",", ":")))
        return 0

    if args.dry_run:
        result("success", "讲解已推送")
        return 0

    for channel, message in messages:
        ok, _detail = send_with_retry(channel, message)
        if not ok:
            result("failed", "消息发送失败")
            return 1

    result("success", "讲解已推送")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
