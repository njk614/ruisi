#!/usr/bin/env python3
"""TTS 音频生成接口占位脚本。

当前 TTS 服务尚未实现，本脚本只读取 PresentationScript.json 并输出待生成音频清单，
为后续接入真实文本转语音服务预留统一入口。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("script_json")
    parser.add_argument("--meeting-dir", required=True)
    parser.add_argument("--dry-run", action="store_true", default=True)
    args = parser.parse_args()

    data = json.loads(Path(args.script_json).read_text(encoding="utf-8"))
    meeting_dir = Path(args.meeting_dir)
    audio_dir = meeting_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    planned = []
    for chapter in data.get("chapters", []):
        for segment in chapter.get("segments", []):
            planned.append({
                "text": segment.get("text"),
                "audio": segment.get("audio"),
                "target_path": str(meeting_dir / segment.get("audio", "")),
            })

    print(json.dumps({
        "status": "tts_not_implemented",
        "message": "TTS 服务暂未实现，本脚本仅输出待生成音频清单。",
        "audio_dir": str(audio_dir),
        "planned_audio": planned,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
