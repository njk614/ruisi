#!/usr/bin/env python3
"""读取真实音频时长并回填到 PresentationScript.md 和 JSON。

PresentationScript.md/JSON 中的 audio 字段可以是完整 HTTP URL，但该 URL
只用于最终脚本对外访问。读取时长时只取 URL 中的文件名，并始终从
本地 <meeting_dir>/audio/ 目录读取 MP3。

音频时长统一向上取整：1.1 秒、1.9 秒都回填为 2 秒。
`推送间隔(s)` / `push_interval` 按 `音频时长 + 素材时长` 计算。
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


AUDIO_FILE_RE = re.compile(r"^audio_\d{3}_\d{2}\.mp3$")


def duration_seconds(path: Path) -> float | None:
    try:
        import mutagen  # type: ignore
        audio = mutagen.File(str(path))
        if audio and audio.info:
            return float(audio.info.length)
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
        return float(result.stdout.strip())
    except Exception:
        return None


def ceil_duration(value: float) -> int:
    return max(1, int(math.ceil(value)))


def numeric_or_zero(value: Any) -> float:
    if value in {None, "", "-"}:
        return 0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0


def fmt_number(value: float | int) -> str:
    number = float(value)
    return str(int(number)) if number.is_integer() else str(number)


def normalized_number(value: float | int) -> float | int:
    number = float(value)
    return int(number) if number.is_integer() else number


def audio_local_path(meeting_dir: Path, audio_value: str) -> Path:
    parsed = urlparse(audio_value)
    if parsed.scheme in {"http", "https"}:
        filename = Path(parsed.path).name
    else:
        filename = Path(audio_value).name
    if not AUDIO_FILE_RE.match(filename):
        raise ValueError(f"invalid audio file name: {audio_value}")
    return meeting_dir / "audio" / filename


def update_markdown_table(path: Path, duration_by_audio: dict[str, int], performance_by_audio: dict[str, Any]) -> int:
    if not path.exists():
        return 0
    updated_lines: list[str] = []
    changed = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            updated_lines.append(line)
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not cells or cells[0] in {"章节ID", "--------"} or len(cells) != 14:
            updated_lines.append(line)
            continue
        audio = cells[9]
        duration = duration_by_audio.get(audio)
        if duration is None:
            updated_lines.append(line)
            continue
        performance_duration = numeric_or_zero(cells[11])
        if audio in performance_by_audio:
            performance_duration = numeric_or_zero(performance_by_audio[audio])
        cells[4] = fmt_number(duration)
        cells[12] = fmt_number(duration + performance_duration)
        updated_lines.append("| " + " | ".join(cells) + " |")
        changed += 1
    path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("script_json")
    parser.add_argument("--meeting-dir", required=True)
    parser.add_argument("--script-md", default=None)
    args = parser.parse_args()

    script_path = Path(args.script_json)
    meeting_dir = Path(args.meeting_dir)
    script_md_path = Path(args.script_md) if args.script_md else meeting_dir / "PresentationScript.md"
    data = json.loads(script_path.read_text(encoding="utf-8"))
    missing: list[str] = []
    unreadable: list[str] = []
    duration_by_audio: dict[str, int] = {}
    performance_by_audio: dict[str, Any] = {}
    updated_json = 0

    for chapter in data.get("chapters", []):
        for segment in chapter.get("segments", []):
            audio_rel = segment.get("audio")
            if not audio_rel:
                continue
            try:
                audio_path = audio_local_path(meeting_dir, str(audio_rel))
            except ValueError:
                unreadable.append(str(audio_rel))
                continue
            if not audio_path.exists():
                missing.append(audio_rel)
                continue
            value = duration_seconds(audio_path)
            if value is None:
                unreadable.append(audio_rel)
                continue
            duration = ceil_duration(value)
            performance_duration = numeric_or_zero(segment.get("performance_duration"))
            segment["duration"] = duration
            segment["push_interval"] = normalized_number(duration + performance_duration)
            duration_by_audio[audio_rel] = duration
            performance_by_audio[audio_rel] = segment.get("performance_duration")
            updated_json += 1

    script_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    updated_md = update_markdown_table(script_md_path, duration_by_audio, performance_by_audio)
    print(json.dumps({
        "updated_json": str(script_path),
        "updated_json_segments": updated_json,
        "updated_md": str(script_md_path) if script_md_path.exists() else None,
        "updated_md_rows": updated_md,
        "missing_audio": missing,
        "unreadable_audio": unreadable,
    }, ensure_ascii=False, indent=2))
    return 0 if not missing and not unreadable else 1


if __name__ == "__main__":
    raise SystemExit(main())
