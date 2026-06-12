"""查询已预定的会议。

本脚本只读 meetings.json，按日期、会议室、预定人或主题关键词过滤已有预定，
按会议时间排序，并为 ruisi-booking-meeting 生成可直接展示给用户的列表文本。
不写入 meetings.json，不修改任何预定记录。
"""

import argparse
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path


TIME_RANGE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}~\d{2}:\d{2}$")
DEFAULT_DATA_ROOT = Path(
    os.environ.get(
        "OPENCLAW_DATA_ROOT",
        "/home/clawd/.openclaw/workspace/SimulatedData",
    )
)
DEFAULT_BOOKINGS_PATH = Path(
    os.environ.get(
        "OPENCLAW_MEETINGS_PATH",
        os.environ.get(
            "OPENCLAW_BOOKINGS_PATH",
            "/home/clawd/.openclaw/workspace/SimulatedData/meetings.json",
        ),
    )
)


def resolve_date(text):
    """把“今天/明天/后天/2026年6月5日/6月5日/2026-06-05”等归一化为 YYYY-MM-DD。"""
    today = datetime.now()
    if "后天" in text:
        return (today + timedelta(days=2)).strftime("%Y-%m-%d")
    if "明天" in text:
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")
    if "今天" in text or "今日" in text:
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

    raise ValueError("无法识别日期，请使用“今天”“明天”或“2026-06-05”")


def booking_start(booking):
    """返回用于排序的会议开始时间；格式异常的记录排到最后。"""
    time_range = str(booking.get("time_range", ""))
    if not TIME_RANGE_PATTERN.match(time_range):
        return datetime.max
    date_part, times = time_range.split(" ", 1)
    start_text = times.split("~", 1)[0]
    return datetime.strptime(f"{date_part} {start_text}", "%Y-%m-%d %H:%M")


def booking_date(booking):
    time_range = str(booking.get("time_range", ""))
    if " " in time_range:
        return time_range.split(" ", 1)[0]
    return ""


def match_booking(booking, filters):
    if filters["booking_id"] and str(booking.get("booking_id", "")) != filters["booking_id"]:
        return False
    if filters["date"] and booking_date(booking) != filters["date"]:
        return False
    if filters["date_from"] and booking_date(booking) < filters["date_from"]:
        return False
    if filters["date_to"] and booking_date(booking) > filters["date_to"]:
        return False
    if filters["room_name"] and filters["room_name"] not in str(booking.get("room_name", "")):
        return False
    if filters["booker_name"] and filters["booker_name"] not in str(booking.get("booker_name", "")):
        return False
    if filters["keyword"] and filters["keyword"] not in str(booking.get("meeting_topic", "")):
        return False
    return True


def format_attendees(value):
    if isinstance(value, list):
        return "、".join(str(item) for item in value) if value else "无"
    text = str(value or "").strip()
    return text or "无"


def build_display_text(bookings):
    if not bookings:
        return "未查询到符合条件的预定会议。"

    lines = [f"共查询到 {len(bookings)} 场预定会议："]
    for index, booking in enumerate(bookings, start=1):
        internal = format_attendees(booking.get("internal_attendees"))
        customer = format_attendees(booking.get("customer_attendees"))
        lines.append(
            f"{index}. {booking.get('time_range', '时间未知')} | "
            f"{booking.get('room_name', '会议室未知')} | "
            f"{booking.get('meeting_topic', '主题未填')}"
        )
        lines.append(
            f"   预定人：{booking.get('booker_name', '未知')}；"
            f"我方：{internal}；客户方：{customer}；"
            f"编号：{booking.get('booking_id', '未知')}"
        )
    return "\n".join(lines)


def load_bookings(path):
    target = Path(path)
    if not target.exists():
        return []
    with target.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main():
    parser = argparse.ArgumentParser(description="Query booked meetings.")
    parser.add_argument("--bookings-path", default=str(DEFAULT_BOOKINGS_PATH))
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--date", help="单日筛选，支持“今天/明天/2026-06-05”")
    parser.add_argument("--date-from", help="起始日期 YYYY-MM-DD 或自然语言")
    parser.add_argument("--date-to", help="结束日期 YYYY-MM-DD 或自然语言")
    parser.add_argument("--room-name", help="按会议室名称包含匹配")
    parser.add_argument("--booker-name", help="按预定人姓名包含匹配")
    parser.add_argument("--keyword", help="按会议主题关键词包含匹配")
    parser.add_argument("--booking-id", help="按预定编号精确匹配")
    args = parser.parse_args()

    try:
        filters = {
            "date": resolve_date(args.date) if args.date else "",
            "date_from": resolve_date(args.date_from) if args.date_from else "",
            "date_to": resolve_date(args.date_to) if args.date_to else "",
            "room_name": (args.room_name or "").strip(),
            "booker_name": (args.booker_name or "").strip(),
            "keyword": (args.keyword or "").strip(),
            "booking_id": (args.booking_id or "").strip(),
        }
        bookings = load_bookings(args.bookings_path)
        matched = [booking for booking in bookings if match_booking(booking, filters)]
        matched.sort(key=booking_start)
        result = {
            "status": "success",
            "count": len(matched),
            "bookings": matched,
            "display_text": build_display_text(matched),
            "message": f"found {len(matched)} bookings",
        }
    except Exception as exc:
        result = {
            "status": "failed",
            "count": 0,
            "bookings": [],
            "display_text": "",
            "message": str(exc),
        }

    output_path = Path(args.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
