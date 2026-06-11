"""查询指定会议时间范围内的空闲会议室。

本脚本读取 meeting_rooms.json 和 meetings.json，归一化用户请求的
会议时间范围，过滤已有重叠预定的会议室，并为 ruisi-booking-meeting
写出可用会议室列表。
"""

import argparse
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path


TIME_RANGE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}~\d{2}:\d{2}$")
TIME_TOKEN_PATTERN = re.compile(r"(上午|下午|中午|晚上|早上)?\s*(\d{1,2})(?:[:：](\d{1,2})|点(?:(\d{1,2})分?)?)")
DEFAULT_DATA_ROOT = Path(
    os.environ.get(
        "OPENCLAW_DATA_ROOT",
        "/home/clawd/.openclaw/workspace/SimulatedData",
    )
)
DEFAULT_ROOMS_PATH = DEFAULT_DATA_ROOT / "meeting_rooms.json"
DEFAULT_BOOKINGS_PATH = Path(
    os.environ.get(
        "OPENCLAW_MEETINGS_PATH",
        os.environ.get(
            "OPENCLAW_BOOKINGS_PATH",
            "/home/clawd/.openclaw/workspace/SimulatedData/meetings.json",
        ),
    )
)


def parse_slot(value):
    normalized = normalize_time_range(value)
    if not TIME_RANGE_PATTERN.match(normalized):
        raise ValueError("time_range must be a complete range, such as 2026-06-01 09:00~11:00")
    date_part, times = normalized.split(" ", 1)
    start_text, end_text = times.split("~", 1)
    start = datetime.strptime(f"{date_part} {start_text}", "%Y-%m-%d %H:%M")
    end = datetime.strptime(f"{date_part} {end_text}", "%Y-%m-%d %H:%M")
    if end <= start:
        raise ValueError("time_range end must be later than start")
    return start, end, normalized


def normalize_time_range(value):
    text = value.strip()
    if TIME_RANGE_PATTERN.match(text):
        return text

    date_part = resolve_date(text)
    time_matches = list(TIME_TOKEN_PATTERN.finditer(text))
    tokens = [match for match in time_matches if match.group(2)]
    if len(tokens) < 2:
        if len(tokens) == 1:
            raise ValueError("请提供完整时间范围，例如“今天上午9点到11点”，不要只提供一个时间点")
        raise ValueError("无法识别时间范围，请使用“今天上午9点到11点”或“2026-06-01 09:00~11:00”")

    start_hour, start_minute = parse_time_token(tokens[0])
    end_hour, end_minute = parse_time_token(tokens[1], fallback_period=tokens[0].group(1))
    return f"{date_part} {start_hour:02d}:{start_minute:02d}~{end_hour:02d}:{end_minute:02d}"


def resolve_date(text):
    today = datetime.now()
    if "明天" in text:
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")
    if "今天" in text:
        return today.strftime("%Y-%m-%d")

    match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})[日号]?", text)
    if match:
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"

    match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if match:
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"

    match = re.search(r"(\d{1,2})月(\d{1,2})[日号]?", text)
    if match:
        return f"{today.year:04d}-{int(match.group(1)):02d}-{int(match.group(2)):02d}"

    return today.strftime("%Y-%m-%d")


def parse_time_token(match, fallback_period=None):
    period = match.group(1) or fallback_period or ""
    hour = int(match.group(2))
    minute = int(match.group(3) or match.group(4) or 0)
    if period in {"下午", "晚上"} and hour < 12:
        hour += 12
    if period == "中午" and hour < 11:
        hour += 12
    if hour > 23 or minute > 59:
        raise ValueError("时间点无效，请检查小时和分钟")
    return hour, minute


def parse_existing_slot(value):
    if not TIME_RANGE_PATTERN.match(value):
        raise ValueError("stored booking time_range must match YYYY-MM-DD HH:MM~HH:MM")
    date_part, times = value.split(" ", 1)
    start_text, end_text = times.split("~", 1)
    start = datetime.strptime(f"{date_part} {start_text}", "%Y-%m-%d %H:%M")
    end = datetime.strptime(f"{date_part} {end_text}", "%Y-%m-%d %H:%M")
    if end <= start:
        raise ValueError("time_range end must be later than start")
    return start, end


def overlaps(left, right):
    left_start, left_end = left
    right_start, right_end = right
    return left_start < right_end and right_start < left_end


def load_json(path, default):
    target = Path(path)
    if not target.exists():
        return default
    with target.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main():
    parser = argparse.ArgumentParser(description="Query free meeting rooms.")
    parser.add_argument("--time-range", required=True)
    parser.add_argument("--rooms-path", default=str(DEFAULT_ROOMS_PATH))
    parser.add_argument("--bookings-path", default=str(DEFAULT_BOOKINGS_PATH))
    parser.add_argument("--output-path", required=True)
    args = parser.parse_args()

    try:
        requested_slot_start, requested_slot_end, normalized_range = parse_slot(args.time_range)
        requested_slot = (requested_slot_start, requested_slot_end)
        rooms = load_json(args.rooms_path, [])
        bookings = load_json(args.bookings_path, [])
        busy_room_ids = set()

        for booking in bookings:
            if overlaps(requested_slot, parse_existing_slot(booking["time_range"])):
                busy_room_ids.add(booking["room_id"])

        available = [room for room in rooms if room.get("room_id") not in busy_room_ids]
        result = {
            "status": "success",
            "rooms": available,
            "time_range": normalized_range,
            "message": f"found {len(available)} available rooms",
        }
    except Exception as exc:
        result = {"status": "failed", "rooms": [], "message": str(exc)}

    output_path = Path(args.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
