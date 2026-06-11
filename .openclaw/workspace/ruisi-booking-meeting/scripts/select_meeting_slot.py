"""生成可供用户选择的会议时段选项。

本脚本扫描会议室和预定数据，返回每个会议室的最大连续空闲时间段，
供 ruisi-booking-meeting 向用户展示简洁的可预约会议时段列表。
"""

import argparse
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path


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
DATE_PATTERN = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
RANGE_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})~(\d{2}:\d{2})$")


def parse_date_key(value):
    match = DATE_PATTERN.match(value)
    if not match:
        raise ValueError("date_from must match YYYY-MM-DD")
    return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))


def to_date_key(value):
    return value.strftime("%Y-%m-%d")


def parse_clock(value):
    hour_text, minute_text = value.split(":", 1)
    hour = int(hour_text)
    minute = int(minute_text)
    if hour > 23 or minute > 59:
        raise ValueError("invalid clock value")
    return hour * 60 + minute


def format_clock(minutes):
    hour = minutes // 60
    minute = minutes % 60
    return f"{hour:02d}:{minute:02d}"


def round_up_to_next_half_hour(value):
    minutes = value.hour * 60 + value.minute
    if value.minute % 30 == 0 and value.second == 0 and value.microsecond == 0:
        return minutes
    return ((minutes + 30) // 30) * 30


def parse_range(value):
    match = RANGE_PATTERN.match(value)
    if not match:
        raise ValueError(f"invalid booking time_range: {value}")
    start = parse_clock(match.group(2))
    end = parse_clock(match.group(3))
    if end <= start:
        raise ValueError(f"invalid booking time_range: {value}")
    return {"date": match.group(1), "start": start, "end": end}


def overlaps(left, right):
    return left["date"] == right["date"] and left["start"] < right["end"] and right["start"] < left["end"]


def merge_busy_ranges(ranges):
    sorted_ranges = sorted(
        [item for item in ranges if item["end"] > item["start"]],
        key=lambda item: item["start"],
    )
    merged = []
    for item in sorted_ranges:
        if not merged or item["start"] > merged[-1]["end"]:
            merged.append(dict(item))
        else:
            merged[-1]["end"] = max(merged[-1]["end"], item["end"])
    return merged


def read_json(path, fallback):
    target = Path(path)
    if not target.exists():
        return fallback
    with target.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path, payload):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def build_result(options, query):
    room_groups = build_room_groups(options)
    return {
        "status": "success",
        "options": options,
        "other_date_option": {
            "index": 0,
            "label": "选择其他日期",
            "action": "choose_other_date",
        },
        "room_groups": room_groups,
        "display_text": build_display_text(room_groups, query),
        "query": query,
        "message": f"found {len(options)} available slots",
    }


def compute_available_slots(args):
    minimum_duration = args.duration_minutes or 1
    if minimum_duration <= 0:
        raise ValueError("duration_minutes must be positive")

    days = args.days or 7
    max_options = args.max_options or 100
    work_start = parse_clock(args.work_start)
    work_end = parse_clock(args.work_end)
    if work_end <= work_start:
        raise ValueError("work_end must be later than work_start")

    now = datetime.fromisoformat(args.now) if args.now else datetime.now()
    today_key = to_date_key(now)
    current_cutoff = round_up_to_next_half_hour(now)
    start_date = parse_date_key(args.date_from) if args.date_from else datetime(now.year, now.month, now.day)

    rooms = read_json(args.rooms_path, [])
    bookings = read_json(args.bookings_path, [])
    parsed_bookings = [
        {"room_id": booking.get("room_id"), "range": parse_range(booking["time_range"])}
        for booking in bookings
    ]
    candidate_rooms = [
        room for room in rooms
        if not args.preferred_room_name or room.get("name") == args.preferred_room_name
    ]

    options = []
    for room in candidate_rooms:
        for day_offset in range(days):
            date = start_date + timedelta(days=day_offset)
            date_key = to_date_key(date)
            if date_key < today_key:
                continue
            day_work_start = max(work_start, current_cutoff) if date_key == today_key else work_start
            if day_work_start >= work_end:
                continue

            work_range = {"date": date_key, "start": day_work_start, "end": work_end}
            busy_ranges = [
                {
                    "start": max(day_work_start, booking["range"]["start"]),
                    "end": min(work_end, booking["range"]["end"]),
                }
                for booking in parsed_bookings
                if booking["room_id"] == room.get("room_id") and overlaps(work_range, booking["range"])
            ]
            free_start = day_work_start
            for busy in merge_busy_ranges(busy_ranges):
                if busy["start"] - free_start >= minimum_duration:
                    append_option(options, date_key, free_start, busy["start"], room)
                    if len(options) >= max_options:
                        return build_result(options, query_payload(args, start_date, today_key, current_cutoff))
                free_start = max(free_start, busy["end"])

            if work_end - free_start >= minimum_duration:
                append_option(options, date_key, free_start, work_end, room)
                if len(options) >= max_options:
                    return build_result(options, query_payload(args, start_date, today_key, current_cutoff))

    return build_result(options, query_payload(args, start_date, today_key, current_cutoff))


def append_option(options, date_key, start, end, room):
    slot = f"{date_key} {format_clock(start)}~{format_clock(end)}"
    options.append(
        {
            "index": len(options) + 1,
            "label": f"{slot} {room.get('name')} {room.get('capacity')}人",
            "slot": slot,
            "room_id": room.get("room_id"),
            "room_name": room.get("name"),
            "capacity": room.get("capacity"),
            "date": date_key,
            "start_time": format_clock(start),
            "end_time": format_clock(end),
        }
    )


def build_room_groups(options):
    groups = []
    group_by_room_id = {}
    for option in options:
        room_id = option.get("room_id") or option.get("room_name") or ""
        if room_id not in group_by_room_id:
            group = {
                "room_id": option.get("room_id"),
                "room_name": option.get("room_name"),
                "capacity": option.get("capacity"),
                "options": [],
            }
            group_by_room_id[room_id] = group
            groups.append(group)
        group_by_room_id[room_id]["options"].append(option)
    return groups


def short_date(date_key):
    return date_key[5:] if len(date_key) >= 10 else date_key


def build_display_text(room_groups, query):
    days = query.get("days") or 7
    range_title = "未来一周可以预约时间范围：" if days == 7 else f"未来{days}天可以预约时间范围："
    lines = []
    if not room_groups:
        lines.append("暂无可预约时间段。")

    for room_number, group in enumerate(room_groups, start=1):
        lines.append(f"会议室{room_number}：**{group.get('room_name')}**（可容纳人数：{group.get('capacity')}人）")
        lines.append(range_title)
        lines.append("| 编号 | 日期 | 时段 |")
        lines.append("| --- | --- | --- |")
        for option in group["options"]:
            lines.append(
                f"| {option['index']} | {short_date(option['date'])} | "
                f"{option['start_time']}~{option['end_time']} |"
            )

    lines.append("请回复**编号**，选择其他日期请直接回复“0”")
    return "\n".join(lines)


def query_payload(args, start_date, today_key, current_cutoff):
    return {
        "date_from": to_date_key(start_date),
        "days": args.days or 7,
        "work_start": args.work_start,
        "work_end": args.work_end,
        "today": today_key,
        "today_cutoff": format_clock(current_cutoff),
    }


def main():
    parser = argparse.ArgumentParser(description="Select available meeting slots.")
    parser.add_argument("--date-from")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--duration-minutes", type=int, default=1)
    parser.add_argument("--preferred-room-name")
    parser.add_argument("--work-start", default="07:00")
    parser.add_argument("--work-end", default="21:00")
    parser.add_argument("--max-options", type=int, default=100)
    parser.add_argument("--now")
    parser.add_argument("--rooms-path", default=str(DEFAULT_ROOMS_PATH))
    parser.add_argument("--bookings-path", default=str(DEFAULT_BOOKINGS_PATH))
    parser.add_argument("--output-path", required=True)
    args = parser.parse_args()

    try:
        result = compute_available_slots(args)
    except Exception as exc:
        result = {"status": "failed", "options": [], "message": str(exc)}

    write_json(args.output_path, result)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
