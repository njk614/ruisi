#!/usr/bin/env python3
"""创建或更新 PresetMeetingData/meeting_index.json。

用于在会议资料生成完成后，按照 meeting_index.json 模板结构写入当前会议信息，
便于后续快速定位指定会议的客户画像与演示脚本 JSON。
"""

from __future__ import annotations

import argparse

from common import data_root, read_json, write_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("booking_id")
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--meeting-topic", required=True)
    parser.add_argument("--time-range", required=True)
    parser.add_argument("--meeting-region", default="")
    args = parser.parse_args()

    root = data_root(args.data_root)
    index_path = root / "PresetMeetingData" / "meeting_index.json"
    if index_path.exists():
        index = read_json(index_path)
    else:
        index = {
            "version": "1.0",
            "description": "已预置会议数据的索引文件，用于快速定位指定会议的客户画像与演示脚本",
            "meetings": [],
        }

    meetings = index.setdefault("meetings", [])
    meetings = [m for m in meetings if m.get("booking_id") != args.booking_id]
    meetings.append({
        "booking_id": args.booking_id,
        "meeting_topic": args.meeting_topic,
        "time_range": args.time_range,
        "meeting_region": args.meeting_region,
        "customer_profile_path": f"./{args.booking_id}/customer_profile/CustomerProfile.md",
        "presentation_script_path": f"./{args.booking_id}/PresentationScript.json",
    })
    index["meetings"] = meetings
    write_json(index_path, index)
    print(str(index_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
