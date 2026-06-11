#!/usr/bin/env python3
"""检查配置的 OpenClaw 知识库文件是否存在。"""

from __future__ import annotations

import argparse
import sys

from common import eprint, json_dumps, load_config, resolve_skill_path


def main() -> int:
    parser = argparse.ArgumentParser(description="检查配置的知识库文件。")
    parser.add_argument("--query", default="")
    args = parser.parse_args()

    try:
        config = load_config()
        knowledge = config.get("knowledge", {})
        file_path_value = str(knowledge.get("file_path", "")).strip()
        if not file_path_value:
            raise ValueError("必须配置 knowledge.file_path")

        knowledge_file = resolve_skill_path(file_path_value, "")
        if not knowledge_file.exists():
            raise FileNotFoundError(f"知识库文件不存在：{knowledge_file}")

        print(json_dumps({"exists": True, "path": str(knowledge_file), "query": args.query}))
        return 0
    except (OSError, ValueError) as exc:
        eprint(f"knowledge_retriever 执行失败：{exc}")
        print(json_dumps({"exists": False, "message": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
