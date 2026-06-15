#!/usr/bin/env python3
"""根据 PresentationScript.json 调用 TTS 接口并生成段落音频。

PresentationScript.json 中的 audio 字段可以是完整 HTTP URL，但该 URL
只用于最终脚本对外访问。生成音频时只取 URL 中的文件名，并始终写入
本地 <meeting_dir>/audio/ 目录。

支持两种接口形态：

1. OpenAI-compatible TTS endpoint：
   POST <endpoint>
   {"model":"tts-1","input":"文本","voice":"Timbre1","response_format":"mp3","speed":1,"stream":false}

2. 页面代理 /api/tts：
   POST <endpoint>
   {"text":"文本","ttsSession":{"sessionId":"...","segmentIndex":1,"segmentCount":N}}

默认只做 dry-run 并输出生成计划；只有显式传入 --request 才会真实请求 TTS 服务。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse
from pathlib import Path
from typing import Any


DEFAULT_MODEL = "tts-1"
DEFAULT_VOICE = "Timbre1"
DEFAULT_RESPONSE_FORMAT = "mp3"
DEFAULT_SPEED = 1.0
DEFAULT_ENDPOINT = "https://api-tts.tuguan.net/v1/audio/speech"
DEFAULT_API_TOKEN = "thisisaapitoken987656789"
SESSION_ID_RE = re.compile(r"[^A-Za-z0-9_-]+")
AUDIO_FILE_RE = re.compile(r"^audio_\d{3}_\d{2}\.mp3$")


def clean_session_id(value: str) -> str:
    cleaned = SESSION_ID_RE.sub("_", value.strip())[:80].strip("_")
    return cleaned or "tts_session"


def read_script(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_segments(data: dict[str, Any]) -> list[dict[str, Any]]:
    planned: list[dict[str, Any]] = []
    for chapter in data.get("chapters", []):
        chapter_id = chapter.get("chapter_id")
        for segment in chapter.get("segments", []):
            text = str(segment.get("text") or "").strip()
            audio = str(segment.get("audio") or "").strip()
            if not text or not audio:
                continue
            planned.append({
                "chapter_id": chapter_id,
                "segment_id": segment.get("segment_id"),
                "text": text,
                "audio": audio,
                "duration": segment.get("duration"),
                "push_interval": segment.get("push_interval"),
            })
    return planned


def audio_local_path(meeting_dir: Path, audio_value: str) -> Path:
    parsed = urlparse(audio_value)
    if parsed.scheme in {"http", "https"}:
        filename = Path(parsed.path).name
    else:
        filename = Path(audio_value).name
    if not AUDIO_FILE_RE.match(filename):
        raise ValueError(f"invalid audio file name: {audio_value}")
    return meeting_dir / "audio" / filename


def http_post_json(endpoint: str, body: dict[str, Any], headers: dict[str, str], timeout: float) -> tuple[bytes, dict[str, str], int]:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(endpoint, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read(), dict(response.headers.items()), response.status
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"TTS request failed: HTTP {exc.code} {error_body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"TTS request failed: {exc.reason}") from exc


def openai_body(text: str, args: argparse.Namespace) -> dict[str, Any]:
    return {
        "model": args.model,
        "input": text,
        "voice": DEFAULT_VOICE,
        "response_format": args.response_format,
        "speed": args.speed,
        "stream": False,
    }


def proxy_body(text: str, session_id: str, index: int, count: int) -> dict[str, Any]:
    return {
        "text": text,
        "ttsSession": {
            "sessionId": session_id,
            "segmentIndex": index,
            "segmentCount": count,
        },
    }


def request_audio(segment: dict[str, Any], args: argparse.Namespace, session_id: str, index: int, count: int) -> tuple[bytes, dict[str, str], dict[str, Any]]:
    headers = {"Content-Type": "application/json"}
    if args.mode == "openai":
        body = openai_body(segment["text"], args)
        if args.api_token:
            headers["Authorization"] = f"Bearer {args.api_token}"
    else:
        body = proxy_body(segment["text"], session_id, index, count)
    audio, response_headers, status = http_post_json(args.endpoint, body, headers, args.timeout)
    return audio, response_headers, {
        "status": status,
        "request_body": body,
        "response_headers": response_headers,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("script_json")
    parser.add_argument("--meeting-dir", required=True)
    parser.add_argument("--mode", choices=["openai", "proxy"], default=os.environ.get("TTS_MODE", "openai"))
    parser.add_argument("--endpoint", default=os.environ.get("CHAT_TTS_ENDPOINT") or os.environ.get("TTS_API_URL") or DEFAULT_ENDPOINT)
    parser.add_argument("--api-token", default=os.environ.get("CHAT_TTS_API_TOKEN") or os.environ.get("TTS_API_TOKEN") or DEFAULT_API_TOKEN)
    parser.add_argument("--model", default=os.environ.get("CHAT_TTS_MODEL", DEFAULT_MODEL))
    parser.add_argument("--response-format", default=os.environ.get("CHAT_TTS_RESPONSE_FORMAT", DEFAULT_RESPONSE_FORMAT))
    parser.add_argument("--speed", type=float, default=float(os.environ.get("CHAT_TTS_SPEED", DEFAULT_SPEED)))
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--request", action="store_true", help="真实调用 TTS 接口并写入音频文件")
    parser.add_argument("--overwrite", action="store_true", help="覆盖已存在的音频文件")
    args = parser.parse_args()

    data = read_script(Path(args.script_json))
    meeting_dir = Path(args.meeting_dir)
    audio_dir = meeting_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    segments = iter_segments(data)
    session_id = clean_session_id(args.session_id or f"tts_{meeting_dir.name}")

    planned = []
    for index, segment in enumerate(segments, start=1):
        target_path = audio_local_path(meeting_dir, segment["audio"])
        planned.append({
            **segment,
            "target_path": str(target_path),
            "exists": target_path.exists(),
        })

    if not args.request:
        print(json.dumps({
            "status": "dry_run",
            "mode": args.mode,
            "endpoint": args.endpoint,
            "voice": DEFAULT_VOICE if args.mode == "openai" else None,
            "session_id": session_id if args.mode == "proxy" else None,
            "audio_dir": str(audio_dir),
            "planned_audio": planned,
        }, ensure_ascii=False, indent=2))
        return 0

    if not args.endpoint:
        print("TTS endpoint is required. Use --endpoint or CHAT_TTS_ENDPOINT/TTS_API_URL.", file=sys.stderr)
        return 2
    if args.speed <= 0:
        print("--speed must be positive", file=sys.stderr)
        return 2

    results = []
    for index, segment in enumerate(segments, start=1):
        target_path = audio_local_path(meeting_dir, segment["audio"])
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.exists() and not args.overwrite:
            results.append({**segment, "target_path": str(target_path), "status": "skipped_exists"})
            continue
        try:
            audio, response_headers, meta = request_audio(segment, args, session_id, index, len(segments))
            target_path.write_bytes(audio)
            results.append({
                **segment,
                "target_path": str(target_path),
                "status": "generated",
                "bytes": len(audio),
                "content_type": response_headers.get("Content-Type") or response_headers.get("content-type"),
                "trace_id": response_headers.get("X-ChatTTS-Trace-Id"),
                "tts_session_id": response_headers.get("X-TTS-Session-Id"),
                "request_status": meta["status"],
            })
        except Exception as exc:
            results.append({**segment, "target_path": str(target_path), "status": "error", "error": str(exc)})
            print(json.dumps({
                "status": "failed",
                "mode": args.mode,
                "endpoint": args.endpoint,
                "audio_dir": str(audio_dir),
                "results": results,
            }, ensure_ascii=False, indent=2))
            return 1

    print(json.dumps({
        "status": "generated",
        "mode": args.mode,
        "endpoint": args.endpoint,
        "audio_dir": str(audio_dir),
        "results": results,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
