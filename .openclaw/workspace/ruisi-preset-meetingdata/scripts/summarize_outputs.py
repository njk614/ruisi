#!/usr/bin/env python3
"""汇总指定会议已生成的核心产物。

用于生成结果摘要阶段，检查客户画像、演示文稿、讲解脚本、脚本 JSON 和音频目录是否存在，
并输出路径与音频数量，方便向用户展示确认信息。
"""

from __future__ import annotations

import argparse
import json

from common import data_root, meeting_dir, rel


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("meeting_id")
    parser.add_argument("--data-root", default=None)
    args = parser.parse_args()

    root = data_root(args.data_root)
    base = meeting_dir(root, args.meeting_id)
    targets = [
        base / "customer_profile" / "CustomerProfile.md",
        base / "PresentationDocument.md",
        base / "PresentationScript.md",
        base / "PresentationScript.json",
    ]
    audio_dir = base / "audio"
    audio_files = sorted(audio_dir.glob("*.mp3")) if audio_dir.exists() else []

    print(json.dumps({
        "meeting_id": args.meeting_id,
        "directory": str(base),
        "files": [{"path": str(p), "relative": rel(p, base), "exists": p.exists()} for p in targets],
        "audio_dir": str(audio_dir),
        "audio_count": len(audio_files),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
