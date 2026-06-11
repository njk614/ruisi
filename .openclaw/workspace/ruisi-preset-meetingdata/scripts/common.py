#!/usr/bin/env python3
"""预置会议数据生成 Skill 的公共工具函数。

本文件不直接作为命令行脚本使用，主要为其他脚本提供统一的数据根目录解析、
JSON 读写、文本读写、会议目录定位和核心文件路径计算能力。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_DATA_ROOT = Path("/home/clawd/.openclaw/workspace/SimulatedData")


def data_root(value: str | None) -> Path:
    return Path(value).expanduser().resolve() if value else DEFAULT_DATA_ROOT


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def meeting_dir(root: Path, meeting_id: str) -> Path:
    return root / "PresetMeetingData" / meeting_id


def core_files(root: Path, meeting_id: str) -> list[Path]:
    base = meeting_dir(root, meeting_id)
    return [
        base / "customer_profile" / "CustomerProfile.md",
        base / "PresentationDocument.md",
        base / "PresentationScript.md",
        base / "PresentationScript.json",
    ]


def rel(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()
