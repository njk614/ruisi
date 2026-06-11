#!/usr/bin/env python3
"""
反馈推送器
负责通过 XMPP 向指定设备推送控制反馈消息
"""

import json
import sys
import requests
import yaml
from pathlib import Path

# 加载配置文件
CONFIG_PATH = Path(__file__).parent.parent / 'config.yaml'

def load_config():
    """加载配置文件"""
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def send_feedback(zone, message):
    """
    向指定区域的反馈设备推送消息

    Args:
        zone: 区域 (entrance/meeting-room-large/main-hall)
        message: 反馈消息内容

    Returns:
        dict: {"success": bool, "message": str, "sent_to": list}
    """
    try:
        config = load_config()
        zone_config = config['zones'].get(zone)

        if not zone_config:
            return {"success": False, "message": f"未知区域: {zone}"}

        # 获取该区域的反馈目标设备
        feedback_targets = zone_config.get('feedback_targets', [])
        if not feedback_targets:
            return {"success": False, "message": "该区域没有配置反馈设备"}

        # XMPP 配置
        xmpp_config = config['xmpp']
        devices_config = config['devices']

        sent_to = []
        failed = []

        # 向每个目标设备发送消息
        for target in feedback_targets:
            jid = devices_config.get(target)
            if not jid:
                failed.append(target)
                continue

            try:
                payload = {
                    'jid': jid,
                    'body': message,
                    'from': xmpp_config['from_account']
                }

                response = requests.post(
                    xmpp_config['api_url'],
                    json=payload,
                    timeout=xmpp_config['timeout_seconds']
                )

                if response.status_code == 200:
                    result = response.json()
                    if result.get('success'):
                        sent_to.append(target)
                    else:
                        failed.append(target)
                else:
                    failed.append(target)

            except Exception as e:
                failed.append(target)

        # 返回结果
        if sent_to:
            return {
                "success": True,
                "message": f"消息已发送至 {', '.join(sent_to)}",
                "sent_to": sent_to,
                "failed": failed
            }
        else:
            return {
                "success": False,
                "message": f"所有设备发送失败: {', '.join(failed)}",
                "sent_to": [],
                "failed": failed
            }

    except Exception as e:
        return {
            "success": False,
            "message": f"推送错误: {str(e)}"
        }

def main():
    """命令行入口"""
    if len(sys.argv) < 3:
        print(json.dumps({
            "success": False,
            "message": "用法: send_feedback.py <zone> <message>"
        }))
        sys.exit(1)

    try:
        zone = sys.argv[1]
        message = sys.argv[2]

        result = send_feedback(zone, message)
        print(json.dumps(result, ensure_ascii=False))

    except Exception as e:
        print(json.dumps({
            "success": False,
            "message": f"执行错误: {str(e)}"
        }))
        sys.exit(1)

if __name__ == '__main__':
    main()
