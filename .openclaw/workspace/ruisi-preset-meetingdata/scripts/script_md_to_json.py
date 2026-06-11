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

from estimate_duration import estimate_duration


def parse_duration(value: str, text: str) -> float | int:
    value = value.strip()
    if not value or value == "-":
        return estimate_duration(text)
    try:
        number = float(value)
    except ValueError:
        return estimate_duration(text)
    return int(number) if number.is_integer() else number


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
        if len(cells) == 12:
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
        chapter_id_s, chapter_topic, segment_id_s, text, duration_s, resource_type, resource_url, resource_params, resource_desc, audio, perf_code, perf_desc = row
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

        chapter["segments"].append({
            "segment_id": segment_id,
            "text": text,
            "duration": parse_duration(duration_s, text),
            "audio": audio,
            "performance_code": None if perf_code in {"", "-"} else perf_code,
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
