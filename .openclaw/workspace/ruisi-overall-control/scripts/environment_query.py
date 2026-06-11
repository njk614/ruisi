#!/usr/bin/env python3
"""
环境数据查询器（用于自动调节模式）
查询模拟的环境传感器数据
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

def query_environment(zone):
    """
    查询指定区域的环境数据

    Args:
        zone: 区域ID

    Returns:
        dict: {"success": bool, "temperature": float, "humidity": float}
    """
    try:
        config = load_config()
        env_config = config['environment']

        # 调用环境数据接口（模拟）
        url = f"{env_config['api_url']}?zone={zone}"

        try:
            response = requests.get(url, timeout=5)

            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "temperature": data.get('temperature'),
                    "humidity": data.get('humidity'),
                    "zone": zone
                }
            else:
                # 返回模拟数据作为降级
                return {
                    "success": True,
                    "temperature": 24,
                    "humidity": 60,
                    "zone": zone,
                    "simulated": True,
                    "message": "使用模拟数据（API不可用）"
                }

        except requests.RequestException:
            # 网络错误，返回模拟数据
            return {
                "success": True,
                "temperature": 24,
                "humidity": 60,
                "zone": zone,
                "simulated": True,
                "message": "使用模拟数据（网络错误）"
            }

    except Exception as e:
        return {
            "success": False,
            "message": f"查询环境数据错误: {str(e)}"
        }

def check_adjustment_needed(temperature):
    """
    根据温度判断是否需要调节

    Args:
        temperature: 当前温度

    Returns:
        dict: {"needed": bool, "reason": str, "target_temp": int}
    """
    try:
        config = load_config()
        threshold = config['environment']['temperature_threshold']

        min_temp = threshold['min']
        max_temp = threshold['max']
        target_temp = threshold['target']

        if temperature < min_temp:
            return {
                "needed": True,
                "reason": f"温度过低（{temperature}°C < {min_temp}°C）",
                "target_temp": target_temp,
                "action": "heat"
            }
        elif temperature > max_temp:
            return {
                "needed": True,
                "reason": f"温度过高（{temperature}°C > {max_temp}°C）",
                "target_temp": target_temp,
                "action": "cool"
            }
        else:
            return {
                "needed": False,
                "reason": f"温度正常（{min_temp}°C ≤ {temperature}°C ≤ {max_temp}°C）",
                "target_temp": None,
                "action": None
            }

    except Exception as e:
        return {
            "needed": False,
            "message": f"判断错误: {str(e)}"
        }

def main():
    """命令行入口"""
    if len(sys.argv) < 3:
        print(json.dumps({
            "success": False,
            "message": "用法: environment_query.py <query|check> <zone>"
        }))
        sys.exit(1)

    try:
        action = sys.argv[1]
        zone = sys.argv[2]

        if action == "query":
            result = query_environment(zone)
        elif action == "check":
            env_result = query_environment(zone)
            if env_result['success']:
                temp = env_result['temperature']
                adjustment = check_adjustment_needed(temp)
                result = {**env_result, "adjustment": adjustment}
            else:
                result = env_result
        else:
            result = {
                "success": False,
                "message": f"未知操作: {action}"
            }

        print(json.dumps(result, ensure_ascii=False))

    except Exception as e:
        print(json.dumps({
            "success": False,
            "message": f"执行错误: {str(e)}"
        }))
        sys.exit(1)

if __name__ == '__main__':
    main()
