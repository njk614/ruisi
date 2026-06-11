#!/usr/bin/env python3
"""根据段落文本长度估算模拟讲解时长。

当前系统尚不支持真实音频生成，因此讲解脚本生成阶段需要先给每个段落写入
模拟时长。本脚本提供统一估算规则：按文本长度计算，并将结果限制在 8 到 25 秒。
"""

from __future__ import annotations

import argparse
import json
import math


def estimate_duration(text: str) -> int:
    """Return a simulated duration in seconds, clamped to 8..25."""
    compact = "".join(ch for ch in text.strip() if not ch.isspace())
    # 中文口播约 4 字/秒；短句给足停顿，长句上限控制在 25 秒。
    seconds = math.ceil(len(compact) / 4) + 2
    return max(8, min(25, seconds))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("text")
    args = parser.parse_args()
    value = estimate_duration(args.text)
    print(json.dumps({"text": args.text, "duration": value}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
