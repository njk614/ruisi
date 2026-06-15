#!/usr/bin/env python3
"""将 PresentationScript.md 表格转换为 PresentationScript.json。

用于把讲解脚本 Markdown 中的章节、资源和段落信息解析成结构化 JSON，
保证脚本 JSON 与 Markdown 脚本内容保持一致。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

PERFORMANCE_DURATIONS = {
    "wave": 4,
    "point": 4,
    "nod": 4,
    "shake_head": 4,
    "smile": 5,
    "laugh": 3,
    "cover_mouth_laugh": 4,
}


def parse_duration(value: str) -> float | int | None:
    value = value.strip()
    if not value or value == "-":
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def parse_performance_duration(value: str, performance_code: str) -> float | int | None:
    value = value.strip()
    if not performance_code or performance_code == "-":
        return None
    if value and value != "-":
        try:
            number = float(value)
        except ValueError:
            pass
        else:
            return int(number) if number.is_integer() else number
    return PERFORMANCE_DURATIONS.get(performance_code)


def parse_push_interval(value: str, duration: float | int | None, performance_duration: float | int | None) -> float | int | None:
    value = value.strip()
    if value and value != "-":
        try:
            number = float(value)
        except ValueError:
            pass
        else:
            return int(number) if number.is_integer() else number
    if duration is None:
        return None
    total = float(duration) + float(performance_duration or 0)
    return int(total) if total.is_integer() else total


def parse_params(value: str) -> Any:
    value = value.strip()
    if not value or value == "-":
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def table_rows(path: Path) -> list[list[str]]:
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
    parser.add_argument("--output", required=True)
    parser.add_argument("--title", default="会议讲解脚本")
    args = parser.parse_args()

    rows = table_rows(Path(args.script_md))
    chapters: list[dict[str, Any]] = []
    by_chapter: dict[int, dict[str, Any]] = {}

    for row in rows:
        chapter_id_s, chapter_topic, segment_id_s, text, duration_s, resource_type, resource_url, resource_params, resource_desc, audio, perf_code, perf_duration_s, push_interval_s, perf_desc = row
        chapter_id = int(chapter_id_s)
        segment_id = int(segment_id_s)
        chapter = by_chapter.get(chapter_id)
        if chapter is None:
            resource = None
            if resource_type != "-":
                resource = {
                    "type": resource_type,
                    "url": resource_url,
                    "params": parse_params(resource_params),
                    "description": resource_desc,
                }
            chapter = {
                "chapter_id": chapter_id,
                "chapter_topic": chapter_topic,
                "resource": resource,
                "segments": [],
            }
            by_chapter[chapter_id] = chapter
            chapters.append(chapter)

        duration = parse_duration(duration_s)
        performance_duration = parse_performance_duration(perf_duration_s, perf_code)
        chapter["segments"].append({
            "segment_id": segment_id,
            "text": text,
            "duration": duration,
            "audio": audio,
            "performance_code": None if perf_code in {"", "-"} else perf_code,
            "performance_duration": performance_duration,
            "push_interval": parse_push_interval(push_interval_s, duration, performance_duration),
            "performance_desc": None if perf_desc in {"", "-"} else perf_desc,
        })

    output = {
        "script_title": args.title,
        "chapters": chapters,
    }
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
