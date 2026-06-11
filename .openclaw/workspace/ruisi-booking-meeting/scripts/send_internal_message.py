"""记录内部会议提醒消息。

本脚本是发送会议提醒的本地占位实现。它校验接收人、平台和消息内容，
并为 ruisi-booking-meeting 的提醒流程写出 JSON 发送记录。
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


SUPPORTED_PLATFORMS = {"local", "email", "wecom"}


def main():
    parser = argparse.ArgumentParser(description="Send an internal message placeholder.")
    parser.add_argument("--platform", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--message", required=True)
    parser.add_argument("--output-path", required=True)
    args = parser.parse_args()

    try:
        if args.platform not in SUPPORTED_PLATFORMS:
            raise ValueError(f"unsupported platform: {args.platform}")
        if not args.user_id.strip():
            raise ValueError("user_id must not be empty")
        if not args.message.strip():
            raise ValueError("message must not be empty")

        record = {
            "platform": args.platform,
            "user_id": args.user_id,
            "message": args.message,
            "sent": True,
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }
        result = {"status": "success", "sent": True, "message": "message recorded", "record": record}
    except Exception as exc:
        result = {"status": "failed", "sent": False, "message": str(exc)}

    output_path = Path(args.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    print(json.dumps({"status": result["status"], "sent": result["sent"], "message": result["message"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
