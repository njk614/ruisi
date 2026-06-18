#!/usr/bin/env python3
"""ruisi-gesture-control 的手势事件分发脚本。

接收 AE01 转发的手势/姿势事件 JSON，识别手势意图后按映射表执行两类动作：
- 演示控制（command）：直接调用同 Agent 下 ruisi-explanation-service 的
  send_message.py 执行真实演示控制（开始演示 / 暂停）。
- 文本推送（push_text）：通过 HTTP API 把提示文本推送到 P01 设备。

映射规则：
- OK 手势     -> 开始演示（转发讲解服务） + 推送 "开始演示" 到 P01
- X 交叉手势  -> 暂停（转发讲解服务）     + 推送 "暂停演示" 到 P01
- 举手        -> 暂停（转发讲解服务）     + 推送 "您好，有什么可以帮助您的？" 到 P01

本脚本不直接跑演示、不直连内容展示器，只做"识别 -> 映射 -> 转发/推送"。
转发讲解服务的 stdout 原样透传（演示控制成功时静默，符合讲解服务约定）。
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


# 允许触发的事件类型：手势 / 姿势。不接受 enter（那是 perceptionflow 的职责）。
TRIGGER_EVENTS = {"gesture", "posture"}

# AE01 上报的手势字段名（实测为 gesture_type）。兼容旧字段名 gesture。
GESTURE_FIELDS = ("gesture_type", "gesture")

# P01 文本推送默认配置（HTTP API，对齐 ruisi-free-qa）。可用 CLI / 环境变量覆盖。
DEFAULT_PUSH_API_URL = "http://127.0.0.1:18900/send"
DEFAULT_PUSH_JID = "niujunke@im.tuguan.net"
DEFAULT_PUSH_FROM = "test-a01@im.tuguan.net"
DEFAULT_PUSH_TIMEOUT = 5.0

# 手势取值 -> 动作。取值统一转小写后匹配，便于兼容大小写差异。
# command  : 演示控制词，转发给讲解服务执行；为 None 表示该手势不做演示控制。
# push_text: 推送到 P01 的提示文本；为 None 表示不推送。
# priority : 多手势组合时的择一优先级，数值越小越优先（举手 > X交叉手势 > OK）。
# AE01 实测上报值为 "OK" / "X交叉手势" / "举手"；其余为兼容性别名。
# 上报值可能是用 "、" 分隔的组合（如 "OK、举手"），按 priority 只取其一。
# 若 AE01 上报值有变，只需调整本映射表。
GESTURE_ACTIONS = {
    "ok": {"command": "开始演示", "push_text": "开始演示", "priority": 2},
    "ok_sign": {"command": "开始演示", "push_text": "开始演示", "priority": 2},
    "okay": {"command": "开始演示", "push_text": "开始演示", "priority": 2},
    "x交叉手势": {"command": "暂停", "push_text": "暂停演示", "priority": 1},
    "x交叉": {"command": "暂停", "push_text": "暂停演示", "priority": 1},
    "交叉手势": {"command": "暂停", "push_text": "暂停演示", "priority": 1},
    "cross": {"command": "暂停", "push_text": "暂停演示", "priority": 1},
    "x": {"command": "暂停", "push_text": "暂停演示", "priority": 1},
    "cross_arms": {"command": "暂停", "push_text": "暂停演示", "priority": 1},
    "crossed": {"command": "暂停", "push_text": "暂停演示", "priority": 1},
    "举手": {"command": "暂停", "push_text": "您好，有什么可以帮助您的？", "priority": 0},
    "raise_hand": {"command": "暂停", "push_text": "您好，有什么可以帮助您的？", "priority": 0},
    "hand_up": {"command": "暂停", "push_text": "您好，有什么可以帮助您的？", "priority": 0},
    "raise": {"command": "暂停", "push_text": "您好，有什么可以帮助您的？", "priority": 0},
}

# 组合手势的分隔符（AE01 用中文顿号；兼容英文逗号 / 斜杠）。
GESTURE_SEPARATORS = ("、", ",", "，", "/")

# 同 Agent 部署时，两个 skill 同级位于 skills/ 目录下。
# 默认按相对位置定位 explanation-service 的入口脚本；可用 --send-script 覆盖。
DEFAULT_SEND_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "ruisi-explanation-service"
    / "scripts"
    / "send_message.py"
)


def result(status, message, **extra):
    """统一输出一个 JSON 对象到 stdout。"""
    payload = {"status": status, "message": message}
    payload.update(extra)
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def parse_args():
    parser = argparse.ArgumentParser(
        description="接收 AE01 手势/姿势事件，映射为演示控制词并转发给讲解服务。"
    )
    parser.add_argument(
        "--payload",
        help="手势事件 JSON 字符串。省略时从 stdin 读取。",
    )
    parser.add_argument(
        "--send-script",
        default=str(DEFAULT_SEND_SCRIPT),
        help="ruisi-explanation-service/send_message.py 的路径。",
    )
    parser.add_argument(
        "--push-url",
        default=os.environ.get("XMPP_SEND_API_URL") or DEFAULT_PUSH_API_URL,
        help="P01 文本推送的 HTTP API 地址。",
    )
    parser.add_argument(
        "--push-jid",
        default=os.environ.get("P01_JID") or DEFAULT_PUSH_JID,
        help="推送目标 JID（默认 niujunke@im.tuguan.net）。",
    )
    parser.add_argument(
        "--push-from",
        default=os.environ.get("XMPP_FROM_ACCOUNT") or DEFAULT_PUSH_FROM,
        help="推送来源账号（默认 test-a01@im.tuguan.net）。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只解析与映射，不实际转发/推送。",
    )
    return parser.parse_args()


def parse_event(raw):
    """解析并校验事件 JSON。返回 (event_obj, error_message)。"""
    if not raw or not raw.strip():
        return None, "无效的事件内容"
    try:
        obj = json.loads(raw.strip())
    except (ValueError, TypeError):
        return None, "事件内容不是合法 JSON"
    if not isinstance(obj, dict):
        return None, "事件内容不是 JSON 对象"
    return obj, None


def get_gesture_value(event):
    """从事件中取手势值，兼容 gesture_type / gesture 两种字段名。"""
    for field in GESTURE_FIELDS:
        value = event.get(field)
        if value not in (None, ""):
            return value
    return None


def validate_trigger(event):
    """严格触发判定。返回 error_message（None 表示通过）。"""
    if event.get("event") not in TRIGGER_EVENTS:
        return "事件类型不匹配（需为 gesture / posture）"
    for field in ("zone", "timestamp"):
        if field not in event or event.get(field) in (None, ""):
            return "缺少必填字段：{}".format(field)
    if get_gesture_value(event) is None:
        return "缺少必填字段：gesture_type"
    return None


def map_gesture(gesture):
    """手势取值 -> 动作字典 {command, push_text}。无法识别返回 None。

    取值可能是用 "、"（兼容 , ， /）分隔的组合，如 "OK、举手"。
    只识别其中一个，按 priority 择一（举手 > X交叉手势 > OK），其余忽略。
    """
    if not isinstance(gesture, str):
        return None
    raw = gesture
    for sep in GESTURE_SEPARATORS[1:]:
        raw = raw.replace(sep, GESTURE_SEPARATORS[0])
    best = None
    for token in raw.split(GESTURE_SEPARATORS[0]):
        action = GESTURE_ACTIONS.get(token.strip().lower())
        if action is None:
            continue
        if best is None or action["priority"] < best["priority"]:
            best = action
    return best


def push_text_to_p01(text, url, jid, from_account, timeout=DEFAULT_PUSH_TIMEOUT):
    """通过 HTTP API 把提示文本推送到 P01。带一次重试。返回 (ok, detail)。"""
    payload = {"jid": jid, "body": text, "from": from_account}
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    last_error = None
    for attempt in range(2):
        try:
            request = urllib.request.Request(
                url, data=body, headers={"Content-Type": "application/json"}, method="POST"
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                content = response.read().decode("utf-8", errors="replace")
            if not content:
                return True, {}
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                return True, {"raw": content}
            if not isinstance(data, dict) or data.get("success") is not False:
                return True, data
            last_error = data.get("error") or data
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            last_error = str(exc)
        if attempt == 0:
            time.sleep(0.3)
    return False, last_error


def forward_command(command, send_script):
    """调用 explanation-service 的 send_message.py 执行控制词，透传其 stdout。"""
    script_path = Path(send_script)
    if not script_path.is_file():
        return False, "讲解服务脚本不存在：{}".format(script_path)
    try:
        completed = subprocess.run(
            [sys.executable, str(script_path), "--payload", command],
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return False, "调用讲解服务失败：{}".format(exc)
    # 透传 stdout（控制类成功时讲解服务静默，stdout 可能为空，这是预期行为）。
    out = completed.stdout.strip()
    if out:
        print(out)
    if completed.returncode != 0:
        err = completed.stderr.strip() or "讲解服务返回非零状态"
        return False, err
    return True, out


def main():
    args = parse_args()
    raw = args.payload if args.payload is not None else sys.stdin.read()

    event, error = parse_event(raw)
    if error:
        result("ignored", error, reason="invalid_json")
        return 0

    error = validate_trigger(event)
    if error:
        result("ignored", error, reason="ignored_event")
        return 0

    gesture_value = get_gesture_value(event)
    action = map_gesture(gesture_value)
    if action is None:
        result(
            "noop",
            "无法识别的手势：{}".format(gesture_value),
            reason="unknown_gesture",
        )
        return 0

    command = action.get("command")
    push_text = action.get("push_text")

    if args.dry_run:
        result("success", "已映射动作", command=command, push_text=push_text)
        return 0

    failures = []

    # 1) 演示控制：转发讲解服务执行（举手类无 command，跳过）。
    if command:
        ok, detail = forward_command(command, args.send_script)
        if not ok:
            failures.append("转发讲解服务失败：{}".format(detail))

    # 2) 文本推送：通过 HTTP API 推送到 P01。
    if push_text:
        ok, detail = push_text_to_p01(
            push_text, args.push_url, args.push_jid, args.push_from
        )
        if not ok:
            failures.append("推送 P01 失败：{}".format(detail))

    if failures:
        result(
            "failed",
            "；".join(failures),
            command=command,
            push_text=push_text,
        )
        return 1
    # 全部成功：讲解服务对控制类指令静默，本脚本也保持静默以对齐其约定。
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
