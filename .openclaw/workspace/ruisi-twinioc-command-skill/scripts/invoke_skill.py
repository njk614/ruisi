#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
孪易指令执行 Skill

职责：
1. 解析 AI 生成的指令串（--agent-output）。
2. 下发前用本地 references/entity_names.json 校验名称类参数（纯本地，不读库）。
3. 生成用户可见计划文本，并把指令下发到孪易平台。

实体名称的智能匹配由加载 SKILL.md 的 AI 完成；本脚本只做最终的本地存在性校验，
作为兜住 AI 幻觉的安全网。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

import httpx


# ============================================================================
# 配置与常量
# ============================================================================

CURRENT_DIR = Path(__file__).resolve().parent
ENTITY_NAMES_FILE = CURRENT_DIR.parent / "references" / "entity_names.json"
DEFAULT_BASE_URL = "http://test.twinioc.net"
# 孪易指令下发的固定路径后缀（拼在 base_url 之后）
SEND_INSTRUCTION_PATH = "/api/editor/v1/location/SendInstruction"

# 无参数固定指令的中文标准语义。下发孪易前，裸指令码（如 A03）会展开为
# 完整形式（如 A03：层级切换：下一层），与原 skill_runtime 的归一化行为对齐。
NO_ARG_COMMAND_TEXT: dict[str, str] = {
    "A03": "层级切换：下一层",
    "A04": "层级切换：上一层",
    "A05": "层级切换：第一层",
    "A06": "层级切换：最后一层",
    "A09": "场景复位",
    "A13": "时间轴：播放",
    "A14": "时间轴：暂停",
    "A20": "图层全部显示",
    "A21": "图层全部隐藏",
    "A31": "停止演示",
    "A32": "暂停演示",
    "A33": "上一步演示",
    "A34": "下一步演示",
    "A35": "重新演示",
    "A36": "告警信息：当前",
    "A37": "告警信息：历史",
    "A38": "告警信息选中",
    "B03": "取消选中",
    "B04": "对象下钻",
    "B05": "对象上卷",
    "E05": "视频：视频上一页",
    "E06": "视频：视频下一页",
    "E08": "视频：下一个视频",
    "E09": "视频：上一个视频",
    "E10": "视频：第一个视频",
    "E11": "视频：末一个视频",
    "E17": "事件：下一个事件",
    "E18": "事件：上一个事件",
    "E19": "事件：第一个事件",
    "E20": "事件：末一个事件",
    "E22": "回放：暂停",
    "E23": "回放：播放",
    "E28": "单路云台：左转",
    "E29": "单路云台：右转",
    "E30": "单路云台：抬头",
    "E31": "单路云台：低头",
    "E32": "单路云台：拉近",
    "E33": "单路云台：拉远",
}

# 消息文本
MESSAGES = {
    "zh-CN": {
        "no_match_found": "场景中没有找到匹配的信息",
        "video_no_match": "视频中没有找到匹配的信息",
        "plan_prefix": "根据最优策略，已经为您规划如下执行计划：",
        "missing_token": "未检测到有效场景 token，请先输入孪易场景 token 再发送指令",
    },
    "en-US": {
        "no_match_found": "No matching information found in the scene",
        "video_no_match": "No matching information found in the video",
        "plan_prefix": "Based on the optimal strategy, I have prepared the following execution plan:",
        "missing_token": "No valid scene token detected. Please enter a TwinIOC scene token before sending instructions.",
    },
}

# 名称类参数指令的本地校验规则。
# 值为一个可调用，接收已加载的 entity_names 配置，返回该指令参数允许的名称集合。
# 未列入此表的指令（无参数指令、枚举值指令、自由文本指令如 C02/D01/B06）不做名称校验。
_NAME_VALIDATION_SPEC: dict[str, Any] = {
    "A02": lambda cfg: cfg.get("levels", []),
    "A18": lambda cfg: cfg.get("layers", []),
    "A19": lambda cfg: cfg.get("layers", []),
    "A23": lambda cfg: cfg.get("charts", []),
    "A24": lambda cfg: cfg.get("charts", []),
    "A30": lambda cfg: cfg.get("presentations", []),
    "B01": lambda cfg: _all_twin_entities(cfg),
    "B02": lambda cfg: _all_twin_entities(cfg),
    "B07": lambda cfg: cfg.get("twin_categories", {}).get("智能开关", []),
    "B08": lambda cfg: cfg.get("twin_categories", {}).get("智能开关", []),
    "B09": lambda cfg: cfg.get("twin_categories", {}).get("温控器", []),
    "B10": lambda cfg: cfg.get("twin_categories", {}).get("温控器", []),
    "C01": lambda cfg: cfg.get("themes", []),
    "E34": lambda cfg: cfg.get("twin_categories", {}).get("摄像头", []),
    "E35": lambda cfg: cfg.get("twin_categories", {}).get("摄像头", []),
}

# 视频（E 系列）指令使用视频相关的未匹配提示
_VIDEO_CODES = {"E34", "E35"}


# ============================================================================
# 工具函数
# ============================================================================

def _detect_locale(text: str | None) -> str:
    """检测语言"""
    value = str(text or "")
    if re.search(r"[A-Za-z]", value) and not re.search(r"[一-鿿]", value):
        return "en-US"
    return "zh-CN"


def _message(locale: str, key: str) -> str:
    """获取消息文本"""
    return MESSAGES.get(locale, MESSAGES["zh-CN"]).get(key) or MESSAGES["zh-CN"][key]


def load_entity_names() -> dict[str, Any]:
    """加载实体名称配置文件"""
    if not ENTITY_NAMES_FILE.exists():
        raise FileNotFoundError(f"配置文件不存在: {ENTITY_NAMES_FILE}")

    with open(ENTITY_NAMES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _all_twin_entities(config: dict[str, Any]) -> list[str]:
    """汇总所有孪生体分类下的实例名称（用于 B01/B02 对象校验）"""
    names: list[str] = []
    for entities in config.get("twin_categories", {}).values():
        if isinstance(entities, list):
            names.extend(entities)
    return names


def _normalize_name(name: str) -> str:
    """归一化名称用于比较：去除首尾空白"""
    return str(name or "").strip()


def _command_prefix(command: str) -> str:
    """取指令码前缀（前 3 个字符，如 A03/B07/E34）"""
    return str(command or "").strip()[:3]


def _normalize_base_url(base_url: str | None) -> str:
    """归一化 base_url：去掉末尾斜杠与可能误带的 /api/editor 等路径后缀。

    与原 skill_runtime._normalize_base_url 行为对齐，保证后续拼接
    SEND_INSTRUCTION_PATH 时不会出现重复路径或双斜杠。
    """
    normalized = str(base_url or DEFAULT_BASE_URL).strip().rstrip("/")
    for suffix in ("/api/editor/v1", "/api/editor/mcp", "/api/editor"):
        if normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized.rstrip("/")


def _expand_instruction_order(instruction_order: str) -> str:
    """
    下发孪易前展开无参数固定指令。

    与原 skill_runtime 的归一化行为对齐：裸指令码（如 A03）展开为完整中文语义
    （如 A03：层级切换：下一层），其余指令原样保留。instruction_order 以 $ 分隔。
    """
    if not instruction_order:
        return ""

    expanded = []
    for cmd in instruction_order.split("$"):
        cmd = cmd.strip()
        if not cmd:
            continue
        prefix = _command_prefix(cmd)
        if prefix in NO_ARG_COMMAND_TEXT and "：" not in cmd:
            expanded.append(f"{prefix}：{NO_ARG_COMMAND_TEXT[prefix]}")
        else:
            expanded.append(cmd)
    return "$".join(expanded)


def parse_instruction_string(instruction_str: str) -> list[dict[str, str]]:
    """
    解析指令字符串
    例如: "[A02：层级切换：楼层20&B01：聚焦对象：环境传感器1]"
    返回: [{"code": "A02", "action": "层级切换", "param": "楼层20"}, ...]
    """
    # 去掉方括号
    instruction_str = instruction_str.strip("[]")

    # 按 & 分割多个指令
    instructions = instruction_str.split("&")

    parsed = []
    for inst in instructions:
        inst = inst.strip()
        if not inst:
            continue

        # 分割指令码、动作、参数
        parts = inst.split("：", 2)
        code = parts[0].strip()
        action = parts[1].strip() if len(parts) > 1 else ""
        param = parts[2].strip() if len(parts) > 2 else ""
        parsed.append({"code": code, "action": action, "param": param})

    return parsed


def validate_instructions(
    instructions: list[dict[str, str]],
    entity_config: dict[str, Any],
    locale: str,
) -> tuple[bool, str | None]:
    """
    下发前本地校验名称类参数是否存在于 entity_names.json。

    Returns:
        (是否全部通过, 失败时的提示消息)
    """
    for inst in instructions:
        code = inst.get("code", "")
        spec = _NAME_VALIDATION_SPEC.get(code)
        if spec is None:
            continue

        valid_names = {_normalize_name(n) for n in spec(entity_config)}

        # E35（摄像头列表）参数为多个名称，按中文逗号拆分逐个校验
        if code == "E35":
            candidates = [
                _normalize_name(p)
                for p in re.split(r"[，,]", inst.get("param", ""))
                if _normalize_name(p)
            ]
        else:
            param = _normalize_name(inst.get("param", ""))
            candidates = [param] if param else []

        for candidate in candidates:
            if candidate not in valid_names:
                msg_key = "video_no_match" if code in _VIDEO_CODES else "no_match_found"
                return False, _message(locale, msg_key)

    return True, None


def generate_plan_text(instructions: list[dict[str, str]], locale: str) -> str:
    """生成用户可见的计划文本（去掉指令编码）"""
    plan_lines = []

    for idx, inst in enumerate(instructions, 1):
        action = inst["action"]
        param = inst["param"]

        if action and param:
            line = f"{idx}、{action}：{param}"
        elif action:
            line = f"{idx}、{action}"
        else:
            # 无参数固定指令（仅指令码，如 A03/A09），动作语义由 AI 在文本中补全
            continue

        plan_lines.append(line)

    prefix = _message(locale, "plan_prefix")
    return f"{prefix}\n" + "\n".join(plan_lines)


async def send_instruction_to_twinioc(
    token: str,
    instruction_order: str,
    query: str,
    plan_text: str,
    base_url: str
) -> dict[str, Any]:
    """发送指令到孪易平台

    端点固定为 {base_url}/api/editor/v1/location/SendInstruction，
    与原 send_instruction_worker.py / skill_runtime.py 保持一致。
    """
    url = f"{_normalize_base_url(base_url)}{SEND_INSTRUCTION_PATH}"

    # 将 & 替换为 $ 作为孪易平台的分隔符，并把裸指令码展开为完整中文语义
    instruction_order_formatted = _expand_instruction_order(
        instruction_order.replace("&", "$")
    )

    # 构建 jsonData: instruction_order$&query$&plan_text
    json_data = f"{instruction_order_formatted}$&{query}$&{plan_text}"

    payload = {
        "token": token,
        "jsonData": json_data
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            response = await client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json", "Accept": "text/plain"},
            )
            response.raise_for_status()
            # 孪易可能返回 text/plain，优先尝试 JSON 解析，失败则回退为原始文本
            try:
                body: Any = response.json()
            except (json.JSONDecodeError, ValueError):
                body = response.text
            return {"success": True, "response": body}
        except httpx.HTTPError as e:
            return {
                "success": False,
                "error": f"API 调用失败: {str(e)}"
            }


# ============================================================================
# 主处理逻辑
# ============================================================================

async def execute_command(
    token: str,
    query: str,
    agent_output: str | None,
    execute_instruction: bool,
    debug: bool,
    locale: str,
    base_url: str | None
) -> dict[str, Any]:
    """
    执行指令

    Args:
        token: 孪易场景 token
        query: 用户自然语言指令
        agent_output: AI 生成的指令串（如 "[A02：层级切换：楼层20]"）
        execute_instruction: 是否实际执行指令
        debug: 是否输出调试信息
        locale: 语言环境
        base_url: 孪易服务基础地址

    Returns:
        执行结果字典
    """
    base_url = base_url or DEFAULT_BASE_URL

    # 校验场景 token：缺失时返回友好提示（而非 argparse 崩溃）
    if not (token or "").strip():
        return {
            "success": False,
            "error": "missing_token",
            "plan_text": _message(locale, "missing_token"),
        }

    # 如果没有提供 agent_output，说明这是一个需要 AI 处理的请求
    if not agent_output:
        return {
            "success": False,
            "error": "需要 AI 生成指令串（--agent-output）",
            "plan_text": ""
        }

    # 解析指令串
    try:
        instructions = parse_instruction_string(agent_output)
    except Exception as e:
        return {
            "success": False,
            "error": f"指令解析失败: {str(e)}",
            "plan_text": ""
        }

    # 下发前本地校验名称类参数
    try:
        entity_config = load_entity_names()
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return {
            "success": False,
            "error": f"实体配置加载失败: {str(e)}",
            "plan_text": ""
        }

    valid, validation_message = validate_instructions(instructions, entity_config, locale)
    if not valid:
        # 校验未通过：不下发，直接把未匹配提示作为最终回复返回
        return {
            "success": False,
            "error": "name_validation_failed",
            "plan_text": validation_message or _message(locale, "no_match_found")
        }

    # 生成计划文本
    plan_text = generate_plan_text(instructions, locale)

    # 执行指令
    execution_result = None
    if execute_instruction:
        # 去掉方括号，保留原始指令串格式
        instruction_order = agent_output.strip("[]")

        execution_result = await send_instruction_to_twinioc(
            token=token,
            instruction_order=instruction_order,
            query=query,
            plan_text=plan_text,
            base_url=base_url
        )

        if not execution_result.get("success", False):
            return {
                "success": False,
                "error": execution_result.get("error", "未知错误"),
                "plan_text": plan_text
            }

    return {
        "success": True,
        "plan_text": plan_text,
        "execution_result": execution_result
    }


# ============================================================================
# 命令行接口
# ============================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="孪易指令执行 Skill")
    parser.add_argument("--token", default=None, help="孪易场景 token（缺失时返回友好提示，由 execute_command 校验）")
    parser.add_argument("--base-url", default=None, help="孪易服务基础地址，默认 http://test.twinioc.net")
    parser.add_argument("--query", default=None, help="用户自然语言指令")
    parser.add_argument(
        "--agent-output",
        help="AI 已生成的指令串，如 [A02：层级切换：楼层8&B02：选中对象：摄像头01]"
    )
    parser.add_argument("--no-execute", action="store_true", help="只生成指令与展示文本，不调用 SendInstruction")
    parser.add_argument("--debug", action="store_true", help="输出调试信息")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()

    try:
        original_query = args.query.strip() if args.query else ""
        locale = _detect_locale(original_query)

        result = await execute_command(
            token=args.token,
            query=args.query,
            agent_output=args.agent_output,
            execute_instruction=not args.no_execute,
            debug=args.debug,
            locale=locale,
            base_url=args.base_url,
        )

        if args.debug:
            print(json.dumps(result, ensure_ascii=False, indent=2), file=sys.stderr)

        # 只输出 message 的纯文本内容，供上游原样转发给用户
        print(result.get("plan_text", ""))
        return 0 if result.get("success") else 1

    except Exception as e:
        # 异常时也只输出一句纯文本提示，保持输出形态一致
        print(str(e))
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
