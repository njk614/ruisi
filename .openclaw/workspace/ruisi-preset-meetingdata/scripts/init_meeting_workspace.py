#!/usr/bin/env python3
"""初始化指定会议的数据目录结构。

用于在 PresetMeetingData/会议ID 下创建 customer_profile 和 audio 子目录，
为后续生成客户画像、演示文稿、讲解脚本、JSON 和音频资源做准备。
"""

from __future__ import annotations

import argparse
import json

from common import data_root, meeting_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("meeting_id")
    parser.add_argument("--data-root", default=None)
    args = parser.parse_args()

    root = data_root(args.data_root)
    base = meeting_dir(root, args.meeting_id)
    (base / "customer_profile").mkdir(parents=True, exist_ok=True)
    (base / "audio").mkdir(parents=True, exist_ok=True)

    print(json.dumps({
        "meeting_id": args.meeting_id,
        "directory": str(base),
        "customer_profile_dir": str(base / "customer_profile"),
        "audio_dir": str(base / "audio"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
