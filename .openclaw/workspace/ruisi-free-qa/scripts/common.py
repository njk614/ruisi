#!/usr/bin/env python3
"""ruisi-free-qa Skill 脚本共用工具函数。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent


def eprint(message: str) -> None:
    print(message, file=sys.stderr)


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value[0:1] in {'"', "'"} and value[-1:] == value[0]:
        return value[1:-1]
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none"}:
        return None
    if value.startswith("[") and value.endswith("]"):
        try:
            return json.loads(value.replace("'", '"'))
        except json.JSONDecodeError:
            return [item.strip().strip('"').strip("'") for item in value[1:-1].split(",") if item.strip()]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _minimal_yaml_load(text: str) -> dict[str, Any]:
    """在未安装 PyYAML 时，解析本 Skill 配置会用到的简化 YAML 子集。"""
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        line = raw_line.split(" #", 1)[0].rstrip()
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip().strip('"').strip("'")
        value = value.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if value == "":
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _parse_scalar(value)
    return root


def read_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except ImportError:
        return _minimal_yaml_load(path.read_text(encoding="utf-8"))


def load_config() -> dict[str, Any]:
    config_value = os.environ.get("RUISI_FREE_QA_CONFIG") or os.environ.get("FREE_QA_CONFIG")
    config_path = Path(config_value or SKILL_DIR / "config.yaml").expanduser()
    if not config_path.is_absolute():
        config_path = SKILL_DIR / config_path
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在：{config_path}")
    return read_yaml(config_path)


def expand_path_placeholders(raw_path: str | os.PathLike[str] | None) -> str:
    text = str(raw_path or "")
    user = os.environ.get("OPENCLAW_USER") or os.environ.get("USER") or os.environ.get("USERNAME") or "用户"
    text = text.replace("${OPENCLAW_USER}", user).replace("${USER}", user).replace("{user}", user)
    text = text.replace("/home/用户/", f"/home/{user}/")
    return os.path.expandvars(text)


def resolve_skill_path(raw_path: str | os.PathLike[str] | None, default: str) -> Path:
    expanded = expand_path_placeholders(raw_path or default)
    path = Path(expanded).expanduser()
    if not path.is_absolute() and not expanded.startswith("/"):
        path = SKILL_DIR / path
    return path


def json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def empty_profile() -> dict[str, Any]:
    return {"visit_count": 0, "projects": [], "interests": []}
