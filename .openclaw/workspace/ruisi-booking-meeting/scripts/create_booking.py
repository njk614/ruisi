"""创建会议预定记录。

本脚本用于校验用户选择的会议室和会议时间，检查预定冲突，
将新的预定记录追加写入 meetings.json，并按 ruisi-booking-meeting
要求的模板结构生成 booking_info.json。
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
        raise ValueError("slot must be a complete range, such as 2026-06-01 09:00~11:00")
    date_part, times = normalized.split(" ", 1)
    start_text, end_text = times.split("~", 1)
    start = datetime.strptime(f"{date_part} {start_text}", "%Y-%m-%d %H:%M")
    end = datetime.strptime(f"{date_part} {end_text}", "%Y-%m-%d %H:%M")
    if end <= start:
        raise ValueError("slot end must be later than start")
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
        raise ValueError("slot end must be later than start")
    return start, end


def overlaps(left, right):
    left_start, left_end = left
    right_start, right_end = right
    return left_start < right_end and right_start < left_end


def generate_booking_id(normalized_slot, bookings):
    meeting_date = normalized_slot.split(" ", 1)[0]
    prefix = "M" + meeting_date.replace("-", "")
    pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)$")
    max_sequence = 0

    for booking in bookings:
        booking_id = str(booking.get("booking_id", ""))
        match = pattern.match(booking_id)
        if match:
            max_sequence = max(max_sequence, int(match.group(1)))

    return f"{prefix}_{max_sequence + 1:03d}"


def load_bookings(path):
    target = Path(path)
    if not target.exists():
        return []
    with target.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_rooms(path):
    target = Path(path)
    if not target.exists():
        return []
    with target.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_room(room_id, room_name, rooms_path):
    if room_id:
        rooms = load_rooms(rooms_path)
        matched = next((room for room in rooms if room.get("room_id") == room_id), None)
        return room_id, matched
    if not room_name:
        raise ValueError("room_id or room_name is required")
    rooms = load_rooms(rooms_path)
    matched = next((room for room in rooms if room.get("name") == room_name), None)
    if not matched:
        raise ValueError(f"room not found by name: {room_name}")
    return matched["room_id"], matched


def resolve_zone(room_id, room_name, room):
    if room and room.get("zone"):
        return room["zone"]
    if room_id == "ROOM-SMALL" or room_name == "小会议室":
        return "meeting-room-small"
    if room_id == "ROOM-LARGE" or room_name == "大会议室":
        return "meeting-room-large"
    return room_id or room_name or ""


def write_json(path, payload):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Create a meeting booking.")
    parser.add_argument("--room-id")
    parser.add_argument("--room-name")
    parser.add_argument("--slot", required=True)
    parser.add_argument("--booker-name", required=True)
    parser.add_argument("--internal-attendees", required=True)
    parser.add_argument("--customer-attendees", default="")
    parser.add_argument("--meeting-topic", required=True)
    parser.add_argument("--rooms-path", default=str(DEFAULT_ROOMS_PATH))
    parser.add_argument("--bookings-path", default=str(DEFAULT_BOOKINGS_PATH))
    parser.add_argument("--output-path", required=True)
    args = parser.parse_args()

    try:
        requested_slot_start, requested_slot_end, normalized_slot = parse_slot(args.slot)
        requested_slot = (requested_slot_start, requested_slot_end)
        room_id, room = resolve_room(args.room_id, args.room_name, args.rooms_path)
        internal_attendees = parse_attendees(args.internal_attendees)
        customer_attendees = parse_attendees(args.customer_attendees, allow_empty=True)
        if not internal_attendees:
            raise ValueError("internal_attendees must not be empty")
        if not args.booker_name.strip():
            raise ValueError("booker_name must not be empty")
        if not args.meeting_topic.strip():
            raise ValueError("meeting_topic must not be empty")

        bookings = load_bookings(args.bookings_path)
        for booking in bookings:
            same_room = booking.get("room_id") == room_id
            if same_room and overlaps(requested_slot, parse_existing_slot(booking["time_range"])):
                raise ValueError("room is already booked for the requested slot")

        booking_id = generate_booking_id(normalized_slot, bookings)
        booking = {
            "booking_id": booking_id,
            "room_id": room_id,
            "room_name": room.get("name") if room else args.room_name,
            "zone": resolve_zone(room_id, args.room_name, room),
            "time_range": normalized_slot,
            "booker_name": args.booker_name,
            "internal_staff": len(internal_attendees),
            "visitor_count": len(customer_attendees),
            "meeting_topic": args.meeting_topic,
            "internal_attendees": internal_attendees,
            "customer_attendees": customer_attendees,
            "created_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        bookings.append(booking)
        write_json(args.bookings_path, bookings)
        write_json(args.output_path, booking)
        result = {"status": "success", "booking_id": booking_id, "booking": booking, "message": "booking created"}
    except Exception as exc:
        result = {"status": "failed", "booking_id": "", "message": str(exc)}
        write_json(args.output_path, result)

    print(json.dumps(result, ensure_ascii=False))


def parse_attendees(value, allow_empty=False):
    text = (value or "").strip()
    if allow_empty and text in {"", "无", "没有", "无客户"}:
        return []
    return [item.strip() for item in re.split(r"[,，、;；]", text) if item.strip()]


if __name__ == "__main__":
    main()
