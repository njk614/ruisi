#!/usr/bin/env python3
"""检查指定会议的数据目录状态。

用于判断会议目录是否不存在、是否为空目录、是否已经包含客户画像、演示文稿、
讲解脚本或脚本 JSON 等核心文件，从而决定继续生成、补齐缺失文件或询问用户覆盖。
"""

from __future__ import annotations

import argparse
import json

from common import core_files, data_root, meeting_dir, rel


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("meeting_id")
    parser.add_argument("--data-root", default=None)
    args = parser.parse_args()

    root = data_root(args.data_root)
    base = meeting_dir(root, args.meeting_id)
    files = core_files(root, args.meeting_id)
    existing = [p for p in files if p.exists()]
    missing = [p for p in files if not p.exists()]

    if not base.exists():
        status = "missing_directory"
        action = "create_and_continue"
    elif not existing:
        status = "directory_without_core_files"
        action = "continue"
    else:
        status = "directory_with_core_files"
        action = "ask_user"

    print(json.dumps({
        "meeting_id": args.meeting_id,
        "directory": str(base),
        "status": status,
        "recommended_action": action,
        "existing_core_files": [rel(p, base) for p in existing],
        "missing_core_files": [rel(p, base) for p in missing],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
