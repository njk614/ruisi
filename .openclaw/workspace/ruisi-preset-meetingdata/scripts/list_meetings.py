#!/usr/bin/env python3
"""读取 meetings.json 并分页输出会议列表。

用于 Skill 触发后的第一步：查询已预定会议，按序号展示会议主题和时间范围，
供用户选择需要预置数据的会议。用户可见列表不展示会议 ID，后续必须使用
resolve_meeting_selection.py 根据页码和序号反查 booking_id。
"""

from __future__ import annotations

import argparse
import json

from common import data_root, read_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=15)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    args = parser.parse_args()

    root = data_root(args.data_root)
    meetings_path = root / "meetings.json"
    if not meetings_path.exists():
        raise SystemExit(f"会议预定文件不存在: {meetings_path}")

    meetings = read_json(meetings_path)
    if not isinstance(meetings, list):
        raise SystemExit("meetings.json 必须是数组")

    total = len(meetings)
    page = max(args.page, 1)
    page_size = max(args.page_size, 1)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = meetings[start:end]

    if args.json:
        print(json.dumps({
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_next": end < total,
            "meetings": page_items,
        }, ensure_ascii=False, indent=2))
        return 0

    print(f"共检索到 {total} 个会议：")
    for idx, meeting in enumerate(page_items, start=1):
        topic = meeting.get("meeting_topic", "未命名会议")
        time_range = meeting.get("time_range", "未填写时间")
        print(f"{idx}. {topic} | {time_range}")
    print("请回复序号选择需要预置数据的会议，继续查看下一页数据请回复 ‘0’")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
