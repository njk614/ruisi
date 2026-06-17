#!/usr/bin/env python3
"""通过 XMPP 发送接口向 P02 发送回答消息。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

from common import eprint, json_dumps, load_config


def compact_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def build_p02_body(kind: str, message: str = "") -> str:
    if kind == "answer":
        if not message.strip():
            raise ValueError("回答消息为空")
        return message
    raise ValueError(f"不支持的消息类型：{kind}")


def post_json(url: str, payload: dict[str, Any], token: str | None, timeout: float) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        content = response.read().decode("utf-8", errors="replace")
    if not content:
        return {}
    try:
        data = json.loads(content)
        return data if isinstance(data, dict) else {"raw": data}
    except json.JSONDecodeError:
        return {"raw": content}


def p02_config(config: dict[str, Any]) -> dict[str, Any]:
    p02 = config.get("p02", {})
    dry_run_env = str(os.environ.get("P02_DRY_RUN", "")).lower() in {"1", "true", "yes", "on"}
    return {
        "api_url": os.environ.get("XMPP_SEND_API_URL") or p02.get("api_url") or "http://127.0.0.1:18900/send",
        "to_jid": os.environ.get("P02_JID") or p02.get("to_jid") or "p01@im.tuguan.net",
        "from_account": os.environ.get("XMPP_FROM_ACCOUNT")
        or p02.get("from_account")
        or "a01@im.tuguan.net",
        "token": os.environ.get("XMPP_SEND_API_TOKEN") or p02.get("token") or None,
        "timeout": float(p02.get("timeout_seconds", 5)),
        "dry_run": dry_run_env or bool(p02.get("dry_run", False)),
    }


def send_p02_body(body: str, config: dict[str, Any] | None = None, dry_run: bool = False) -> tuple[bool, Any]:
    cfg = p02_config(config or load_config())
    request_payload = {"jid": cfg["to_jid"], "body": body, "from": cfg["from_account"]}

    if dry_run or cfg["dry_run"]:
        return True, {"dry_run": True, "request": request_payload}

    last_error: Any = None
    for attempt in range(2):
        try:
            response = post_json(str(cfg["api_url"]), request_payload, token=cfg["token"], timeout=cfg["timeout"])
            if response.get("success") is True:
                return True, response
            if not response:
                return True, response
            last_error = response.get("error") or response
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            last_error = str(exc)
        if attempt == 0:
            time.sleep(0.3)
    return False, last_error


def main() -> int:
    parser = argparse.ArgumentParser(description="向 P02 发送格式化的 ruisi-free-qa 消息。")
    parser.add_argument("--message-kind", required=True, choices=["answer"])
    parser.add_argument("--message", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        body = build_p02_body(args.message_kind, args.message)
        ok, detail = send_p02_body(body, dry_run=args.dry_run)
        if not ok:
            raise RuntimeError(detail)
        print(json_dumps({"status": "success", "message": "已发送到P02", "body": body}))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        eprint(f"send_to_device 执行失败：{exc}")
        print(json_dumps({"status": "failed", "message": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
