#!/usr/bin/env python3
"""校验 PresentationScript.md 是否符合讲解脚本表格规则。

用于检查段落长度、音频路径格式、资源字段填写规则、资源类型和表演素材码是否合法，
确保 Markdown 讲解脚本可稳定转换为 JSON 并用于后续音频生成。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from estimate_duration import estimate_duration


AUDIO_RE = re.compile(r"^audio/audio_\d{3}_\d{2}\.mp3$")
VALID_RESOURCE_TYPES = {"image", "ppt", "video", "webpage", "-"}
VALID_PERFORMANCE = {
    "-", "", "wave", "nod", "shake_head", "point", "spread_hands", "thumbs_up",
    "clap", "bow", "heart", "ok", "neutral", "smile", "laugh",
    "cover_mouth_laugh", "awkward", "surprise", "puzzled", "serious", "blink",
    "wink",
}


def rows(path: Path) -> list[list[str]]:
    parsed: list[list[str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not cells or cells[0] in {"章节ID", "--------"}:
            continue
        if len(cells) == 12:
            parsed.append(cells)
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("script_md")
    args = parser.parse_args()

    path = Path(args.script_md)
    issues: list[str] = []
    parsed = rows(path)
    last_chapter = None

    for idx, row in enumerate(parsed, start=1):
        chapter_id, _topic, segment_id, text, duration, resource_type, resource_url, resource_params, resource_desc, audio, perf_code, _perf_desc = row
        if len(text) > 60:
            issues.append(f"row {idx}: 文本内容超过 60 字: {len(text)}")
        try:
            duration_value = float(duration)
        except ValueError:
            issues.append(f"row {idx}: 时长(s)必须填写 8 到 25 之间的模拟秒数")
        else:
            if duration_value < 8 or duration_value > 25:
                issues.append(f"row {idx}: 时长(s)超出 8 到 25 秒范围: {duration}")
            expected = estimate_duration(text)
            if abs(duration_value - expected) > 3:
                issues.append(f"row {idx}: 时长(s)与文本长度估算差异较大，建议约 {expected}s")
        if not AUDIO_RE.match(audio):
            issues.append(f"row {idx}: 音频文件格式错误: {audio}")
        if resource_type not in VALID_RESOURCE_TYPES:
            issues.append(f"row {idx}: 资源类型非法: {resource_type}")
        if perf_code not in VALID_PERFORMANCE:
            issues.append(f"row {idx}: 表演素材码非法: {perf_code}")
        if not chapter_id.isdigit():
            issues.append(f"row {idx}: 章节ID不是整数: {chapter_id}")
        if not segment_id.isdigit():
            issues.append(f"row {idx}: 段落ID不是整数: {segment_id}")
        if segment_id != "1" and chapter_id == last_chapter:
            for name, value in [("资源类型", resource_type), ("资源URL", resource_url), ("资源参数", resource_params), ("资源描述", resource_desc)]:
                if value != "-":
                    issues.append(f"row {idx}: 同章节后续段落{name}应为 -")
        if segment_id == "1" and resource_type == "-":
            issues.append(f"row {idx}: 章节第一段必须填写资源类型")
        last_chapter = chapter_id

    print(json.dumps({
        "valid": not issues,
        "row_count": len(parsed),
        "issues": issues,
    }, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
