#!/usr/bin/env python3
"""按当前会议定位 OpenClaw 预置客户画像/演示脚本资料。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from common import eprint, expand_path_placeholders, json_dumps, load_config, resolve_skill_path


DEFAULT_BASE_DIR = "/home/clawd/.openclaw/workspace/SimulatedData/PresetMeetingData"
DEFAULT_MEETING_REGION = "大会议室"


def parse_datetime(value: str) -> datetime:
    value = value.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"不支持的时间格式：{value}")


def parse_time_range(time_range: str) -> tuple[datetime, datetime]:
    if "~" not in time_range:
        raise ValueError(f"会议时间范围缺少 ~ 分隔符：{time_range}")

    start_raw, end_raw = [part.strip() for part in time_range.split("~", 1)]
    start = parse_datetime(start_raw)
    try:
        end = parse_datetime(end_raw)
    except ValueError:
        end = parse_datetime(f"{start.strftime('%Y-%m-%d')} {end_raw}")
    return start, end


def resolve_base_dir(config: dict[str, Any]) -> Path:
    preset = config.get("preset_meeting_data", {})
    return resolve_skill_path(preset.get("base_dir"), DEFAULT_BASE_DIR)


def resolve_index_file(config: dict[str, Any], base_dir: Path, override: str = "") -> Path:
    preset = config.get("preset_meeting_data", {})
    raw_index = override or str(preset.get("meeting_index_file", "")).strip() or "meeting_index.json"
    expanded = Path(expand_path_placeholders(raw_index)).expanduser()
    if expanded.is_absolute():
        return expanded
    return base_dir / expanded


def resolve_meeting_file(index_dir: Path, meeting: dict[str, Any], key: str, fallback: Path) -> Path:
    raw_path = str(meeting.get(key, "")).strip()
    if not raw_path:
        return fallback
    path = Path(expand_path_placeholders(raw_path)).expanduser()
    if path.is_absolute():
        return path
    return index_dir / path


def load_meeting_index(index_file: Path) -> dict[str, Any]:
    try:
        data = json.loads(index_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"meeting_index.json 格式错误：{exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("meetings"), list):
        raise ValueError("meeting_index.json 必须包含 meetings 数组")
    return data


def find_current_meeting(meetings: list[Any], meeting_region: str, now: datetime) -> dict[str, Any]:
    for item in meetings:
        if not isinstance(item, dict):
            continue
        if str(item.get("meeting_region", "")).strip() != meeting_region:
            continue
        start, end = parse_time_range(str(item.get("time_range", "")).strip())
        if start <= now <= end:
            return item
    raise LookupError(f"未找到会议室为“{meeting_region}”且时间包含 {now.strftime('%Y-%m-%d %H:%M:%S')} 的会议")


def fallback_result(message: str) -> dict[str, Any]:
    return {"exists": False, "fallback": "knowledge_only", "message": message}


def main() -> int:
    parser = argparse.ArgumentParser(description="按当前时间和会议室定位预置会议资料。")
    parser.add_argument("--meeting-region", default="")
    parser.add_argument("--current-time", default="", help="测试用，格式：YYYY-MM-DD HH:MM[:SS]")
    parser.add_argument("--meeting-index-file", default="", help="测试或覆盖用 meeting_index.json 路径")
    args = parser.parse_args()

    try:
        config = load_config()
        preset = config.get("preset_meeting_data", {})
        base_dir = resolve_base_dir(config)
        index_file = resolve_index_file(config, base_dir, args.meeting_index_file)
        meeting_region = args.meeting_region or str(preset.get("meeting_region", "")).strip() or DEFAULT_MEETING_REGION
        now = parse_datetime(args.current_time) if args.current_time else datetime.now()

        if not index_file.exists():
            raise FileNotFoundError(f"会议索引文件不存在：{index_file}")

        index_data = load_meeting_index(index_file)
        meeting = find_current_meeting(index_data["meetings"], meeting_region, now)
        booking_id = str(meeting.get("booking_id", "")).strip()
        if not booking_id:
            raise ValueError("匹配会议缺少 booking_id")

        index_dir = index_file.parent
        meeting_dir = index_dir / booking_id
        if not meeting_dir.exists():
            raise FileNotFoundError(f"会议目录不存在：{meeting_dir}")

        presentation_script = resolve_meeting_file(index_dir, meeting, "presentation_script_path", meeting_dir / "PresentationScript.json")
        if not presentation_script.exists():
            raise FileNotFoundError(f"PresentationScript.json 不存在：{presentation_script}")

        customer_profile = resolve_meeting_file(
            index_dir,
            meeting,
            "customer_profile_path",
            meeting_dir / "customer_profile" / "CustomerProfile.md",
        )

        print(
            json_dumps(
                {
                    "exists": True,
                    "booking_id": booking_id,
                    "meeting_topic": str(meeting.get("meeting_topic", "")).strip(),
                    "meeting_region": str(meeting.get("meeting_region", "")).strip(),
                    "time_range": str(meeting.get("time_range", "")).strip(),
                    "meeting_index_path": str(index_file),
                    "meeting_dir": str(meeting_dir),
                    "path": str(presentation_script),
                    "presentation_script_path": str(presentation_script),
                    "customer_profile_path": str(customer_profile),
                    "customer_profile_exists": customer_profile.exists(),
                    "matched_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
        )
        return 0
    except (OSError, ValueError, LookupError) as exc:
        eprint(f"profile_queries 会议资料不可用，降级为仅知识库回答：{exc}")
        print(json_dumps(fallback_result(str(exc))))
        return 0


if __name__ == "__main__":
    sys.exit(main())
