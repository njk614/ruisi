#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MQTT 设备控制器
负责通过 MQTT 发送设备控制指令（灯光、空调）
"""

import json
import sys
import time
import paho.mqtt.client as mqtt
import yaml
import os
from pathlib import Path

# 加载配置文件
CONFIG_PATH = Path(__file__).parent.parent / 'config.yaml'

def load_config():
    """加载配置文件"""
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def publish_mqtt_message(topic, payload, mqtt_config):
    """
    发布 MQTT 消息

    Args:
        topic: MQTT topic
        payload: 消息内容（字符串或字典）
        mqtt_config: MQTT 配置

    Returns:
        dict: {"success": bool, "message": str}
    """
    try:
        # 创建 MQTT 客户端
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

        # 设置认证
        if mqtt_config.get('username'):
            client.username_pw_set(mqtt_config['username'], mqtt_config.get('password', ''))

        # 连接到 broker
        client.connect(mqtt_config['broker'], mqtt_config['port'], mqtt_config['keepalive'])

        # 如果 payload 是字典，转换为 JSON
        # 格式要求: { "key":"value", "key2":"value2" }
        # { 后有空格, , 后有空格, } 前有空格, : 后无空格
        if isinstance(payload, dict):
            # 先生成紧凑 JSON
            compact_json = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
            # 手动添加必需的空格: { 后, , 后, } 前
            # {"key":"value","key2":"value2"} → { "key":"value", "key2":"value2" }
            payload_str = compact_json.replace('{', '{ ').replace(',', ', ').replace('}', ' }')
        else:
            payload_str = str(payload)

        # 发布消息
        result = client.publish(topic, payload_str)

        # 等待消息发送完成
        result.wait_for_publish(timeout=5)

        # 断开连接
        client.disconnect()

        if result.is_published():
            return {
                "success": True,
                "message": f"指令已发送: {topic}",
                "topic": topic,
                "payload": payload
            }
        else:
            return {
                "success": False,
                "message": "消息发送失败"
            }

    except Exception as e:
        return {
            "success": False,
            "message": f"MQTT 发送错误: {str(e)}"
        }

def control_lighting(zone, action, device_ids=None, all_devices=False):
    """
    控制灯光

    协议：office/control/light
    格式：{ "devsId": "设备ID", "status": "on/off" }

    Args:
        zone: 区域
        action: 动作 (on/off)
        device_ids: 设备ID列表（可选）
        all_devices: 是否控制所有设备
    """
    config = load_config()
    mqtt_config = config['mqtt']
    zone_config = config['zones'].get(zone)

    if not zone_config:
        return {"success": False, "message": f"未知区域: {zone}"}

    # 如果是全部设备，使用区域配置中的所有灯光设备
    if all_devices:
        device_ids = zone_config.get('lighting', [])

    if not device_ids:
        return {"success": False, "message": "未指定设备"}

    # 确保 action 是 on 或 off
    if action not in ['on', 'off']:
        return {"success": False, "message": f"无效的动作: {action}，必须是 on 或 off"}

    # 获取 topic
    topic = mqtt_config['topics']['lighting']

    # 逐个发送控制指令
    results = []
    for dev_id in device_ids:
        payload = {
            "devsId": dev_id,
            "status": action
        }

        result = publish_mqtt_message(topic, payload, mqtt_config)
        results.append({
            "device_id": dev_id,
            "success": result["success"],
            "message": result.get("message", "")
        })

    # 汇总结果
    success_count = sum(1 for r in results if r["success"])
    if success_count == len(results):
        return {
            "success": True,
            "message": f"成功控制 {success_count} 个灯光设备",
            "results": results
        }
    elif success_count > 0:
        return {
            "success": True,
            "message": f"部分成功：{success_count}/{len(results)} 个设备",
            "results": results
        }
    else:
        return {
            "success": False,
            "message": "所有设备控制失败",
            "results": results
        }

def control_hvac_switch(zone, action, device_ids=None, all_devices=False):
    """
    控制空调开关

    协议：office/control/wkq
    格式：{ "devsId": "设备ID", "status": "on/off" }

    Args:
        zone: 区域
        action: 动作 (on/off)
        device_ids: 设备ID列表（可选）
        all_devices: 是否控制所有设备
    """
    config = load_config()
    mqtt_config = config['mqtt']
    zone_config = config['zones'].get(zone)

    if not zone_config:
        return {"success": False, "message": f"未知区域: {zone}"}

    # 如果是全部设备，使用区域配置中的所有空调设备
    if all_devices:
        device_ids = zone_config.get('hvac', [])

    if not device_ids:
        return {"success": False, "message": "未指定设备"}

    # 确保 action 是 on 或 off
    if action not in ['on', 'off']:
        return {"success": False, "message": f"无效的动作: {action}，必须是 on 或 off"}

    # 获取 topic
    topic = mqtt_config['topics']['hvac_switch']

    # 逐个发送控制指令
    results = []
    for dev_id in device_ids:
        payload = {
            "devsId": dev_id,
            "status": action
        }

        result = publish_mqtt_message(topic, payload, mqtt_config)
        results.append({
            "device_id": dev_id,
            "success": result["success"],
            "message": result.get("message", "")
        })

    # 汇总结果
    success_count = sum(1 for r in results if r["success"])
    if success_count == len(results):
        return {
            "success": True,
            "message": f"成功控制 {success_count} 个空调设备",
            "results": results
        }
    elif success_count > 0:
        return {
            "success": True,
            "message": f"部分成功：{success_count}/{len(results)} 个设备",
            "results": results
        }
    else:
        return {
            "success": False,
            "message": "所有设备控制失败",
            "results": results
        }

def control_hvac_temperature(zone, temperature, device_ids=None, all_devices=False):
    """
    控制空调温度

    协议：office/control/{devsId}/temp
    格式：直接发送温度值（字符串）

    Args:
        zone: 区域
        temperature: 温度值
        device_ids: 设备ID列表（可选）
        all_devices: 是否控制所有设备
    """
    config = load_config()
    mqtt_config = config['mqtt']
    zone_config = config['zones'].get(zone)

    if not zone_config:
        return {"success": False, "message": f"未知区域: {zone}"}

    # 如果是全部设备，使用区域配置中的所有空调设备
    if all_devices:
        device_ids = zone_config.get('hvac', [])

    if not device_ids:
        return {"success": False, "message": "未指定设备"}

    # 验证温度范围
    try:
        temp_value = int(temperature)
        if not (16 <= temp_value <= 30):
            return {"success": False, "message": "温度值必须在16-30℃之间"}
    except (ValueError, TypeError):
        return {"success": False, "message": f"无效的温度值: {temperature}"}

    # 获取 topic 模板
    topic_template = mqtt_config['topics']['hvac_temp']

    # 逐个发送控制指令
    results = []
    for dev_id in device_ids:
        # 替换 topic 中的设备ID
        topic = topic_template.replace('{devsId}', dev_id)

        # payload 直接是温度值
        payload = str(temp_value)

        result = publish_mqtt_message(topic, payload, mqtt_config)
        results.append({
            "device_id": dev_id,
            "success": result["success"],
            "message": result.get("message", "")
        })

    # 汇总结果
    success_count = sum(1 for r in results if r["success"])
    if success_count == len(results):
        return {
            "success": True,
            "message": f"成功设置 {success_count} 个空调温度为 {temp_value}℃",
            "results": results
        }
    elif success_count > 0:
        return {
            "success": True,
            "message": f"部分成功：{success_count}/{len(results)} 个设备设置为 {temp_value}℃",
            "results": results
        }
    else:
        return {
            "success": False,
            "message": "所有设备温度设置失败",
            "results": results
        }

def control_hvac(zone, action, temperature=None, device_ids=None, all_devices=False):
    """
    控制空调（统一入口）

    Args:
        zone: 区域
        action: 动作 (on/off/set_temperature)
        temperature: 温度值（当action为set_temperature时必填）
        device_ids: 设备ID列表（可选）
        all_devices: 是否控制所有设备
    """
    if action == 'set_temperature':
        if temperature is None:
            return {"success": False, "message": "设置温度需要提供温度值"}
        return control_hvac_temperature(zone, temperature, device_ids, all_devices)
    elif action in ['on', 'off']:
        return control_hvac_switch(zone, action, device_ids, all_devices)
    else:
        return {"success": False, "message": f"未知的空调操作: {action}"}

def main():
    """命令行入口"""
    if len(sys.argv) < 2:
        print(json.dumps({
            "success": False,
            "message": "用法: mqtt_controller.py <json_command>"
        }, ensure_ascii=False))
        sys.exit(1)

    try:
        # 解析命令行参数
        command_json = sys.argv[1]
        command = json.loads(command_json)

        device_type = command.get('device_type')
        zone = command.get('zone')

        # 根据设备类型调用相应的控制函数
        if device_type == 'lighting':
            result = control_lighting(
                zone=zone,
                action=command.get('action'),
                device_ids=command.get('device_ids'),
                all_devices=command.get('all', False)
            )
        elif device_type == 'hvac':
            result = control_hvac(
                zone=zone,
                action=command.get('action'),
                temperature=command.get('temperature'),
                device_ids=command.get('device_ids'),
                all_devices=command.get('all', False)
            )
        else:
            result = {"success": False, "message": f"未知设备类型: {device_type}"}

        print(json.dumps(result, ensure_ascii=False))

    except json.JSONDecodeError as e:
        print(json.dumps({
            "success": False,
            "message": f"JSON 解析错误: {str(e)}"
        }, ensure_ascii=False))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({
            "success": False,
            "message": f"执行错误: {str(e)}"
        }, ensure_ascii=False))
        sys.exit(1)

if __name__ == '__main__':
    main()
