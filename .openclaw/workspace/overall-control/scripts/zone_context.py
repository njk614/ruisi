#!/usr/bin/env python3
"""
区域上下文管理器
负责读取和更新当前区域上下文
"""

import json
import sys
from pathlib import Path
import yaml

# 加载配置文件
CONFIG_PATH = Path(__file__).parent.parent / 'config.yaml'

def load_config():
    """加载配置文件"""
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def get_current_zone():
    """
    获取当前区域

    Returns:
        dict: {"success": bool, "zone": str or None, "zone_name": str or None}
    """
    try:
        config = load_config()
        context_file = Path(config['context']['file_path'])

        # 展开相对路径
        if not context_file.is_absolute():
            context_file = (Path(__file__).parent.parent / context_file).resolve()

        if not context_file.exists():
            return {
                "success": True,
                "zone": None,
                "zone_name": None,
                "message": "上下文文件不存在"
            }

        with open(context_file, 'r', encoding='utf-8') as f:
            context = json.load(f)

        zone = context.get('current_zone')

        # 获取区域中文名
        zone_name = None
        if zone:
            zone_config = config['zones'].get(zone)
            if zone_config:
                zone_name = zone_config.get('zone_name')

        return {
            "success": True,
            "zone": zone,
            "zone_name": zone_name
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"读取上下文错误: {str(e)}"
        }

def set_current_zone(zone):
    """
    设置当前区域

    Args:
        zone: 区域ID

    Returns:
        dict: {"success": bool, "message": str}
    """
    try:
        config = load_config()

        # 验证区域是否有效
        if zone not in config['zones']:
            return {
                "success": False,
                "message": f"无效的区域: {zone}"
            }

        context_file = Path(config['context']['file_path'])

        # 展开相对路径
        if not context_file.is_absolute():
            context_file = (Path(__file__).parent.parent / context_file).resolve()

        # 确保目录存在
        context_file.parent.mkdir(parents=True, exist_ok=True)

        # 写入上下文
        context = {"current_zone": zone}
        with open(context_file, 'w', encoding='utf-8') as f:
            json.dump(context, f, ensure_ascii=False, indent=2)

        return {
            "success": True,
            "message": f"已设置当前区域: {zone}"
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"写入上下文错误: {str(e)}"
        }

def main():
    """命令行入口"""
    if len(sys.argv) < 2:
        print(json.dumps({
            "success": False,
            "message": "用法: zone_context.py <get|set> [zone]"
        }))
        sys.exit(1)

    try:
        action = sys.argv[1]

        if action == "get":
            result = get_current_zone()
        elif action == "set":
            if len(sys.argv) < 3:
                result = {
                    "success": False,
                    "message": "set 操作需要提供区域参数"
                }
            else:
                zone = sys.argv[2]
                result = set_current_zone(zone)
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
