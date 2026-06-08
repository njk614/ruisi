#!/usr/bin/env python3
"""检查配置的 OpenClaw 客户画像文件是否存在。"""

from __future__ import annotations

import argparse
import os
import sys

from common import eprint, json_dumps, load_config, resolve_skill_path


def main() -> int:
    parser = argparse.ArgumentParser(description="检查配置的客户画像文件。")
    parser.add_argument("--customer-name", default="")
    args = parser.parse_args()

    try:
        config = load_config()
        customer = config.get("customer", {})
        customer_name = (
            args.customer_name
            or os.environ.get("FREE_QA_CUSTOMER_NAME", "")
            or str(customer.get("default_name", "")).strip()
        )
        profile_file_value = str(customer.get("profile_file", "")).strip()
        if not profile_file_value:
            raise ValueError("必须配置 customer.profile_file")

        profile_file = resolve_skill_path(profile_file_value, "")
        if not profile_file.exists():
            raise FileNotFoundError(f"客户画像文件不存在：{profile_file}")

        print(json_dumps({"exists": True, "path": str(profile_file), "customer_name": customer_name}))
        return 0
    except (OSError, ValueError) as exc:
        eprint(f"profile_queries 执行失败：{exc}")
        print(json_dumps({"exists": False, "message": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
