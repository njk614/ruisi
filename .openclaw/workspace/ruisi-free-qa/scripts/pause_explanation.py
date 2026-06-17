#!/usr/bin/env python3
"""调用 ruisi-explanation-service 消息入口，触发暂停讲解。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import eprint, json_dumps, load_config


def candidate_message_service_scripts() -> list[Path]:
    """按优先级列出 send_message.py 可能所在的位置，覆盖常见部署布局。

    free-qa 与 explanation-service 在不同机器上可能是同级 skill 目录，也可能
    被平铺到同一个 skills/scripts/ 下，且顶层 workspace 目录名（如 workspace、
    workspace_a01）并不固定，因此这里枚举多个候选，由调用方取第一个存在的。
    """
    script_dir = Path(__file__).resolve().parent           # .../ruisi-free-qa/scripts
    skill_dir = script_dir.parent                           # .../ruisi-free-qa
    skills_root = skill_dir.parent                          # .../skills 或 .../workspace

    candidates = [
        # 每 skill 独立子目录：.../<skills_root>/ruisi-explanation-service/scripts/send_message.py
        skills_root / "ruisi-explanation-service" / "scripts" / "send_message.py",
        # 平铺布局：与本脚本同在 .../scripts/send_message.py
        script_dir / "send_message.py",
        skills_root / "scripts" / "send_message.py",
    ]

    seen: set[Path] = set()
    unique: list[Path] = []
    for path in candidates:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def resolve_message_service_script(config: dict[str, Any]) -> Path:
    section = config.get("explanation_service", {})
    configured = str(section.get("message_service_script", "")).strip()
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        resolved = path.resolve()
        # 配置路径存在就直接用；不存在则退回候选探测，避免单一硬编码路径
        # 在换部署环境（workspace 目录名不同、布局不同）时直接失败。
        if resolved.exists():
            return resolved

    for candidate in candidate_message_service_scripts():
        if candidate.exists():
            return candidate

    # 都不存在时，返回首个候选作为报错路径，交给上层 exists() 检查统一报错。
    return candidate_message_service_scripts()[0]


def build_command(script_path: Path, config: dict[str, Any]) -> list[str]:
    section = config.get("explanation_service", {})
    pause_message = str(section.get("pause_message", "暂停")).strip() or "暂停"
    return [sys.executable, str(script_path), "--payload", pause_message]


def fast_touch_pause_flag(script_path: Path) -> None:
    """在拉起 send_message.py 之前，先就地写下 demo_pause.flag 做快速止血。

    free-qa 暂停链路最大的延迟在“再启动一层 Python + 加载配置 + 解析意图”，
    而后台 run_demo_sequence.py 只认 runtime/demo_pause.flag 是否存在。这里
    从 send_message.py 路径推导出同级 runtime 目录，第一时间写下 flag，让后台
    在下一个检查点（≤0.2s）就能停住；随后照常走 subprocess 调用，由
    send_message.py 用它自己计算的 RUNTIME_DIR 再写一遍，形成双保险。

    纯 best-effort：路径推导或写入失败都不抛错，不影响后续正规暂停流程。
    """
    try:
        # script_path 形如 .../ruisi-explanation-service/scripts/send_message.py
        runtime_dir = script_path.resolve().parent.parent / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        flag_path = runtime_dir / "demo_pause.flag"
        flag_path.write_text(
            datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            encoding="utf-8",
        )
    except OSError as exc:
        eprint(f"fast_touch_pause_flag 跳过（不影响主流程）：{exc}")


def parse_json_stdout(stdout: str) -> dict[str, Any] | None:
    if not stdout:
        return None
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def is_no_running_demo_result(stdout: str) -> bool:
    payload = parse_json_stdout(stdout)
    if not payload:
        return False
    message = str(payload.get("message", ""))
    return payload.get("status") == "failed" and "当前没有正在运行的演示" in message


def main() -> int:
    parser = argparse.ArgumentParser(description="触发 ruisi-explanation-service 执行暂停讲解。")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        config = load_config()
        script_path = resolve_message_service_script(config)
        command = build_command(script_path, config)
        if args.dry_run:
            print(json_dumps({"status": "success", "message": "dry-run", "command": command}))
            return 0

        if not script_path.exists():
            raise FileNotFoundError(f"ruisi-explanation-service 入口脚本不存在: {script_path}")

        # 先就地写下暂停标记快速止血，再走正规 subprocess 调用。
        fast_touch_pause_flag(script_path)

        result = subprocess.run(command, capture_output=True, text=True, check=False)
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        if result.returncode != 0:
            if is_no_running_demo_result(stdout):
                print(json_dumps({"status": "success", "message": "当前无演示，无需暂停", "detail": stdout}))
                return 0
            detail = stderr or stdout or f"exit={result.returncode}"
            raise RuntimeError(detail)

        print(json_dumps({"status": "success", "message": "已触发 ruisi-explanation-service 暂停", "detail": stdout}))
        return 0
    except (OSError, RuntimeError, ValueError, FileNotFoundError) as exc:
        eprint(f"pause_explanation 执行失败：{exc}")
        print(json_dumps({"status": "failed", "message": f"暂停触发 ruisi-explanation-service 失败：{exc}"}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
