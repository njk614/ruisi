#!/usr/bin/env python3
"""校验 PresentationScript.md 是否符合讲解脚本表格规则。

用于检查段落长度、音频路径格式、资源字段填写规则、资源类型和表演素材码是否合法，
确保 Markdown 讲解脚本可稳定转换为 JSON 并用于后续音频生成。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

AUDIO_URL_RE = re.compile(r"^http://172\.16\.1\.138:8089/PresetMeetingData/([^/]+)/audio/audio_\d{3}_\d{2}\.mp3$")
VALID_RESOURCE_TYPES = {"image", "ppt", "video", "webpage", "-"}
VALID_PERFORMANCE = {
    "-", "", "wave", "point", "nod", "shake_head", "smile", "laugh",
    "cover_mouth_laugh",
}
PERFORMANCE_DURATIONS = {
    "wave": 4,
    "point": 4,
    "nod": 4,
    "shake_head": 4,
    "smile": 5,
    "laugh": 3,
    "cover_mouth_laugh": 4,
}


def rows(path: Path) -> list[list[str]]:
    parsed: list[list[str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not cells or cells[0] in {"章节ID", "--------"}:
            continue
        if len(cells) == 14:
            parsed.append(cells)
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("script_md")
    parser.add_argument("--meeting-id", default=None, help="当前会议 booking_id；提供后会校验音频 URL 中的会议 ID")
    parser.add_argument("--require-durations", action="store_true", help="要求时长(s)和推送间隔(s)已根据真实音频回填")
    args = parser.parse_args()

    path = Path(args.script_md)
    issues: list[str] = []
    parsed = rows(path)
    last_chapter = None

    for idx, row in enumerate(parsed, start=1):
        chapter_id, _topic, segment_id, text, duration, resource_type, resource_url, resource_params, resource_desc, audio, perf_code, perf_duration, push_interval, _perf_desc = row
        duration_value: float | None = None
        perf_duration_value: float | None = None
        if len(text) < 30:
            issues.append(f"row {idx}: 文本内容少于 30 字: {len(text)}")
        if len(text) > 90:
            issues.append(f"row {idx}: 文本内容超过 90 字: {len(text)}")
        if duration in {"", "-"}:
            if args.require_durations:
                issues.append(f"row {idx}: 时长(s)必须在音频生成后回填")
        else:
            try:
                duration_value = float(duration)
            except ValueError:
                issues.append(f"row {idx}: 时长(s)必须填写数字或生成前占位 -")
            else:
                if duration_value <= 0:
                    issues.append(f"row {idx}: 时长(s)必须大于 0: {duration}")
        audio_match = AUDIO_URL_RE.match(audio)
        if not audio_match:
            issues.append(f"row {idx}: 音频文件必须是完整 HTTP 地址: {audio}")
        elif args.meeting_id and audio_match.group(1) != args.meeting_id:
            issues.append(f"row {idx}: 音频 URL 中的会议 ID 应为 {args.meeting_id}: {audio_match.group(1)}")
        if resource_type not in VALID_RESOURCE_TYPES:
            issues.append(f"row {idx}: 资源类型非法: {resource_type}")
        if perf_code not in VALID_PERFORMANCE:
            issues.append(f"row {idx}: 表演素材码非法: {perf_code}")
        expected_perf_duration = PERFORMANCE_DURATIONS.get(perf_code)
        if expected_perf_duration is None:
            if perf_duration not in {"", "-"}:
                issues.append(f"row {idx}: 未使用表演素材时素材时长(s)应为 -")
        else:
            try:
                perf_duration_value = float(perf_duration)
            except ValueError:
                issues.append(f"row {idx}: 素材时长(s)必须填写数字: {perf_duration}")
            else:
                if perf_duration_value != expected_perf_duration:
                    issues.append(f"row {idx}: 素材时长(s)应为 {expected_perf_duration}: {perf_duration}")
        if push_interval in {"", "-"}:
            if args.require_durations:
                issues.append(f"row {idx}: 推送间隔(s)必须在音频生成后回填")
        else:
            try:
                push_interval_value = float(push_interval)
            except ValueError:
                issues.append(f"row {idx}: 推送间隔(s)必须填写数字或生成前占位 -")
            else:
                if duration_value is not None:
                    expected_push_interval = duration_value + (perf_duration_value or 0)
                    if push_interval_value != expected_push_interval:
                        issues.append(f"row {idx}: 推送间隔(s)应为 时长(s)+素材时长(s)={expected_push_interval:g}: {push_interval}")
        if not chapter_id.isdigit():
            issues.append(f"row {idx}: 章节ID不是整数: {chapter_id}")
        if not segment_id.isdigit():
            issues.append(f"row {idx}: 段落ID不是整数: {segment_id}")
        if segment_id != "1" and chapter_id == last_chapter:
            for name, value in [("资源类型", resource_type), ("资源URL", resource_url), ("资源参数", resource_params), ("资源描述", resource_desc)]:
                if value != "-":
                    issues.append(f"row {idx}: 同章节后续段落{name}应为 -")
        if segment_id == "1" and resource_type == "-":
            issues.append(f"row {idx}: 章节第一段必须填写资源类型")
        last_chapter = chapter_id

    print(json.dumps({
        "valid": not issues,
        "row_count": len(parsed),
        "issues": issues,
    }, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
