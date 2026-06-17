#!/usr/bin/env python3
"""根据关键词匹配度推荐标准模板和展示资源。

用于读取 DisplayResourceLibrary/resource_catalog.json，并按会议主题、客户画像、
客户关注点、产品关键词等信息先匹配标准模板，再对展示资源排序，避免后续生成
内容时改写固定模板或编造不存在的资源路径。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from common import data_root, read_json


def tokenize(values: list[str]) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        for part in re.split(r"[\s,，、/|;；:：()（）\-]+", value):
            part = part.strip().lower()
            if part:
                tokens.add(part)
    return tokens


def score_fields(fields: list[str], query_tokens: set[str], queries: list[str]) -> int:
    item_tokens = tokenize(fields)
    joined = " ".join(fields).lower()
    score = len(query_tokens & item_tokens)
    score += sum(1 for q in queries if q.lower() in joined)
    return score


def template_score(template: dict, query_tokens: set[str], queries: list[str]) -> int:
    triggers = [str(x) for x in template.get("triggers", [])]
    fields: list[str] = [
        str(template.get("template_id", "")),
        str(template.get("name", "")),
        str(template.get("description", "")),
        str(template.get("position", "")),
    ]
    fields.extend(triggers)
    score = score_fields(fields, query_tokens, queries)
    for query in queries:
        query_text = query.strip().lower()
        if not query_text:
            continue
        for trigger in triggers:
            trigger_text = trigger.strip().lower()
            if trigger_text and (trigger_text in query_text or query_text in trigger_text):
                score += 5
    return score


def resource_score(resource: dict, query_tokens: set[str], queries: list[str]) -> int:
    fields: list[str] = [
        str(resource.get("resource_id", "")),
        str(resource.get("type", "")),
        str(resource.get("description", "")),
    ]
    fields.extend(str(x) for x in resource.get("keywords", []))
    fields.extend(str(x) for x in resource.get("related_products", []))
    fields.extend(str(x) for x in resource.get("scene_tags", []))
    return score_fields(fields, query_tokens, queries)


def resolve_catalog_path(root: Path, catalog_path_arg: str | None) -> Path:
    if catalog_path_arg:
        return Path(catalog_path_arg).expanduser().resolve()
    return root / "DisplayResourceLibrary" / "resource_catalog.json"


def resolve_template_path(catalog_path: Path, file_path: str) -> Path:
    path = Path(file_path)
    if path.is_absolute():
        return path
    return (catalog_path.parent / path).resolve()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--catalog-path", default=None, help="Override resource_catalog.json path.")
    parser.add_argument("--query", action="append", required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--template-limit", type=int, default=5)
    parser.add_argument("--include-template-content", action="store_true")
    args = parser.parse_args()

    root = data_root(args.data_root)
    catalog_path = resolve_catalog_path(root, args.catalog_path)
    if not catalog_path.exists():
        raise SystemExit(f"展示资源库不存在: {catalog_path}")

    catalog = read_json(catalog_path)
    templates = catalog.get("templates", []) if isinstance(catalog, dict) else []
    resources = catalog.get("resources", []) if isinstance(catalog, dict) else []
    query_tokens = tokenize(args.query)
    ranked_templates = []
    ranked_resources = []

    for template in templates:
        if not isinstance(template, dict):
            continue
        score = template_score(template, query_tokens, args.query)
        if score <= 0:
            continue
        item = dict(template)
        item["score"] = score
        file_path = str(template.get("file_path", ""))
        if file_path:
            template_path = resolve_template_path(catalog_path, file_path)
            item["template_path"] = str(template_path)
            item["template_exists"] = template_path.exists()
            if args.include_template_content and template_path.exists():
                item["template_content"] = template_path.read_text(encoding="utf-8")
        ranked_templates.append(item)

    for resource in resources:
        if not isinstance(resource, dict):
            continue
        score = resource_score(resource, query_tokens, args.query)
        if score > 0:
            item = dict(resource)
            item["score"] = score
            item["resource_url"] = resource.get("file_path", "")
            ranked_resources.append(item)

    ranked_templates.sort(key=lambda x: x["score"], reverse=True)
    ranked_resources.sort(key=lambda x: x["score"], reverse=True)
    print(json.dumps({
        "templates": ranked_templates[:args.template_limit],
        "resources": ranked_resources[:args.limit],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
