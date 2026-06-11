#!/usr/bin/env python3
"""根据用户选择的页内序号解析真实会议 booking_id。

用于用户从会议列表中回复序号后，按当前页码和每页数量回到 meetings.json 中
定位对应会议，输出 booking_id 和会议对象。后续创建目录、检查目录、生成文件
都必须使用这里解析出的 booking_id，不能使用会议主题作为目录名。
"""

from __future__ import annotations

import argparse
import json

from common import data_root, read_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("selection", type=int, help="用户在当前页回复的序号，从 1 开始。")
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=15)
    args = parser.parse_args()

    if args.selection <= 0:
        raise SystemExit("selection 必须是当前页内从 1 开始的会议序号")

    root = data_root(args.data_root)
    meetings_path = root / "meetings.json"
    if not meetings_path.exists():
        raise SystemExit(f"会议预定文件不存在: {meetings_path}")

    meetings = read_json(meetings_path)
    if not isinstance(meetings, list):
        raise SystemExit("meetings.json 必须是数组")

    page = max(args.page, 1)
    page_size = max(args.page_size, 1)
    absolute_index = (page - 1) * page_size + (args.selection - 1)
    if absolute_index < 0 or absolute_index >= len(meetings):
        raise SystemExit("用户选择的会议序号超出当前会议列表范围")

    meeting = meetings[absolute_index]
    booking_id = meeting.get("booking_id")
    if not booking_id:
        raise SystemExit("选中的会议缺少 booking_id 字段，无法创建会议目录")

    print(json.dumps({
        "selection": args.selection,
        "page": page,
        "page_size": page_size,
        "absolute_index": absolute_index,
        "booking_id": booking_id,
        "meeting": meeting,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
