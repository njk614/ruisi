#!/usr/bin/env python3
"""检索本地 KnowledgeBase 文件并返回相关片段。

用于根据客户公司、会议主题、兴趣点或产品关键词，在本地知识库中查找可作为
客户画像和演示文稿生成依据的文本片段。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from common import data_root


def snippets(text: str, keyword: str, window: int) -> list[str]:
    results: list[str] = []
    for match in re.finditer(re.escape(keyword), text, flags=re.IGNORECASE):
        start = max(match.start() - window, 0)
        end = min(match.end() + window, len(text))
        snippet = re.sub(r"\s+", " ", text[start:end]).strip()
        if snippet and snippet not in results:
            results.append(snippet)
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--query", action="append", required=True)
    parser.add_argument("--max-results", type=int, default=20)
    parser.add_argument("--window", type=int, default=120)
    args = parser.parse_args()

    root = data_root(args.data_root)
    kb_dir = root / "KnowledgeBase"
    if not kb_dir.exists():
        raise SystemExit(f"知识库目录不存在: {kb_dir}")

    results: list[dict[str, str]] = []
    files = [p for p in kb_dir.rglob("*") if p.is_file()]
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for keyword in args.query:
            for item in snippets(text, keyword, args.window):
                results.append({
                    "file": str(path),
                    "keyword": keyword,
                    "snippet": item,
                })
                if len(results) >= args.max_results:
                    print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
                    return 0

    print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
