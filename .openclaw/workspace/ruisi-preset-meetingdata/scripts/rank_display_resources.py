#!/usr/bin/env python3
"""根据关键词匹配度推荐展示资源。

用于读取 DisplayResourceLibrary/resource_catalog.json，并按会议主题、客户关注点、
产品关键词等信息对展示资源排序，避免后续生成内容时编造不存在的资源路径。
"""

from __future__ import annotations

import argparse
import json
import re

from common import data_root, read_json


def tokenize(values: list[str]) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        for part in re.split(r"[\s,，、/|;；:：()（）\-]+", value):
            part = part.strip().lower()
            if part:
                tokens.add(part)
    return tokens


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--query", action="append", required=True)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    root = data_root(args.data_root)
    catalog_path = root / "DisplayResourceLibrary" / "resource_catalog.json"
    if not catalog_path.exists():
        raise SystemExit(f"展示资源库不存在: {catalog_path}")

    catalog = read_json(catalog_path)
    resources = catalog.get("resources", []) if isinstance(catalog, dict) else []
    query_tokens = tokenize(args.query)
    ranked = []

    for resource in resources:
        fields: list[str] = [
            str(resource.get("resource_id", "")),
            str(resource.get("type", "")),
            str(resource.get("description", "")),
        ]
        fields.extend(str(x) for x in resource.get("keywords", []))
        fields.extend(str(x) for x in resource.get("related_products", []))
        fields.extend(str(x) for x in resource.get("scene_tags", []))
        resource_tokens = tokenize(fields)
        joined = " ".join(fields).lower()
        score = len(query_tokens & resource_tokens)
        score += sum(1 for q in args.query if q.lower() in joined)
        if score > 0:
            item = dict(resource)
            item["score"] = score
            item["resource_url"] = resource.get("file_path", "")
            ranked.append(item)

    ranked.sort(key=lambda x: x["score"], reverse=True)
    print(json.dumps({"resources": ranked[:args.limit]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
