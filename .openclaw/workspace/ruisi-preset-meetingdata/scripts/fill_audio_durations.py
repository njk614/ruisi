#!/usr/bin/env python3
"""读取音频文件时长并回填到脚本 JSON。

用于在真实 MP3 文件生成后，逐一读取每段音频的实际时长，并写回
PresentationScript.json；Markdown 表格的时长字段可由调用方据此同步更新。
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def duration_seconds(path: Path) -> float | None:
    try:
        import mutagen  # type: ignore
        audio = mutagen.File(str(path))
        if audio and audio.info:
            return round(float(audio.info.length), 2)
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
        return round(float(result.stdout.strip()), 2)
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("script_json")
    parser.add_argument("--meeting-dir", required=True)
    args = parser.parse_args()

    script_path = Path(args.script_json)
    meeting_dir = Path(args.meeting_dir)
    data = json.loads(script_path.read_text(encoding="utf-8"))
    missing: list[str] = []

    for chapter in data.get("chapters", []):
        for segment in chapter.get("segments", []):
            audio_rel = segment.get("audio")
            if not audio_rel:
                continue
            audio_path = meeting_dir / audio_rel
            if not audio_path.exists():
                missing.append(audio_rel)
                continue
            value = duration_seconds(audio_path)
            if value is not None:
                segment["duration"] = value

    script_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"updated": str(script_path), "missing_audio": missing}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
