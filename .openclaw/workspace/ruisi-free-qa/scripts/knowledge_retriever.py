#!/usr/bin/env python3
"""对 OpenClaw 知识库文件做轻量检索，返回与问题最相关的若干片段。

设计约束（与本 Skill 其余脚本一致）：
- 只用 Python 标准库，不依赖 jieba/embedding/向量库等第三方组件；
- 知识库是一份中文为主的纯文本文档（如 DH初始知识库.txt），由
  `----------------------------------------` 分隔线切成多个顶级主题块，
  每块标题位于分隔线的上一行，常带【...】；
- 通过“顶级块切分 + 大块二次切片 + 字符 bigram 打分（标题加权）”挑出
  top_k 片段，避免把整篇知识库塞进大模型 prompt，从而显著缩短推理耗时。

输出 JSON：
    {
      "exists": true,
      "path": "...",
      "query": "...",
      "chunk_count": 3,
      "chunks": [
        {"score": 12.0, "title": "【孪易产品简介】", "text": "...原文..."},
        ...
      ]
    }
检索不到任何命中时降级返回开头的公司概述片段兜底，保证 chunks 不为空。
"""

from __future__ import annotations

import argparse
import re
import sys
from typing import Any

from common import eprint, json_dumps, load_config, resolve_skill_path


# 顶级主题分隔线：连续的短横线（允许首尾空白），单独成行。
SEPARATOR_RE = re.compile(r"^\s*-{6,}\s*$")
# 提取标题中的【...】用于额外加权与展示。
BRACKET_TITLE_RE = re.compile(r"【[^】]*】")
# 英文/数字词，用于英文场景的匹配补充。
WORD_RE = re.compile(r"[a-zA-Z0-9]+")
# 中文字符范围（含扩展），用于抽取参与 bigram 的“有效字符”。
CJK_RE = re.compile(r"[㐀-鿿豈-﫿]")

DEFAULT_TOP_K = 3
DEFAULT_CHUNK_CHARS = 500
DEFAULT_OVERLAP_CHARS = 50


def _to_int(value: Any, default: int) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    return result if result > 0 else default


def split_top_blocks(text: str) -> list[dict[str, str]]:
    """按 ---- 分隔线切顶级块，并把分隔线上一行识别为该块标题。

    返回 [{"title": str, "body": str}, ...]。标题尽量取分隔线上一行的非空文本，
    没有则回退到块正文第一行。
    """
    lines = text.splitlines()
    blocks: list[dict[str, str]] = []
    buffer: list[str] = []

    def flush(title_hint: str) -> None:
        body = "\n".join(buffer).strip("\n")
        if body.strip():
            blocks.append({"title": title_hint.strip(), "body": body})

    pending_title = ""
    for line in lines:
        if SEPARATOR_RE.match(line):
            # 分隔线上一行（buffer 末尾最后一条非空行）作为“下一块”的标题；
            # 同时它通常也是“上一块”的收尾，这里把它从当前 buffer 弹出，
            # 既不重复计入正文，也作为新块标题。
            title_line = ""
            while buffer and not buffer[-1].strip():
                buffer.pop()
            if buffer:
                title_line = buffer.pop()
            flush(pending_title)
            buffer = []
            pending_title = title_line
        else:
            buffer.append(line)
    flush(pending_title)

    # 没有任何分隔线时，整篇作为一个块。
    if not blocks and text.strip():
        blocks.append({"title": "", "body": text.strip()})
    return blocks


def _split_long_body(body: str, chunk_chars: int, overlap_chars: int) -> list[str]:
    """把超长正文按空行优先、长度兜底切成多个片段，片段间留 overlap。"""
    body = body.strip("\n")
    if len(body) <= chunk_chars:
        return [body] if body.strip() else []

    # 先按空行拆成自然段。
    paragraphs = [p.strip("\n") for p in re.split(r"\n\s*\n", body) if p.strip()]
    pieces: list[str] = []
    current = ""
    for para in paragraphs:
        if not current:
            current = para
        elif len(current) + 1 + len(para) <= chunk_chars:
            current = f"{current}\n{para}"
        else:
            pieces.append(current)
            current = para
        # 单个自然段就超长：按字符硬切（带 overlap）。
        while len(current) > chunk_chars:
            pieces.append(current[:chunk_chars])
            current = current[max(0, chunk_chars - overlap_chars):]
    if current.strip():
        pieces.append(current)
    return [p for p in pieces if p.strip()]


def build_chunks(text: str, chunk_chars: int, overlap_chars: int) -> list[dict[str, str]]:
    """生成检索片段：每个片段继承所属顶级块的标题。"""
    chunks: list[dict[str, str]] = []
    for block in split_top_blocks(text):
        title = block["title"]
        for piece in _split_long_body(block["body"], chunk_chars, overlap_chars):
            chunks.append({"title": title, "text": piece})
    return chunks


def _char_bigrams(text: str) -> list[str]:
    """抽取参与匹配的字符序列后生成相邻 bigram。

    仅保留中文字符与英文数字（小写），去掉标点/空白，避免噪声拉低区分度。
    """
    tokens: list[str] = []
    for ch in text:
        if CJK_RE.match(ch):
            tokens.append(ch)
        elif ch.isalnum():
            tokens.append(ch.lower())
    if len(tokens) < 2:
        return tokens[:]  # 太短就退化为单字（unigram）
    return ["".join(pair) for pair in zip(tokens, tokens[1:])]


def _words(text: str) -> list[str]:
    return [w.lower() for w in WORD_RE.findall(text)]


def score_chunk(query: str, query_bigrams: list[str], query_words: list[str], chunk: dict[str, str]) -> float:
    """对单个片段打分：bigram 重叠 + 标题命中加权 + 整串命中加权 + 英文词命中。"""
    title = chunk.get("title", "")
    body = chunk.get("text", "")

    score = 0.0

    # 1) 正文 bigram 重叠（核心信号）。
    body_bigrams = _char_bigrams(body)
    if query_bigrams and body_bigrams:
        body_set = set(body_bigrams)
        hit = sum(1 for bg in query_bigrams if bg in body_set)
        score += hit  # 每个命中的 bigram +1

    # 2) 标题命中：标题里出现 query 的 bigram，权重更高（标题是强主题信号）。
    title_bigrams = set(_char_bigrams(title))
    if query_bigrams and title_bigrams:
        title_hit = sum(1 for bg in query_bigrams if bg in title_bigrams)
        score += title_hit * 4.0

    # 3) query 原串（去标点）整体出现在标题/正文里，强加权（精确主题匹配）。
    compact_query = "".join(
        ch for ch in query if CJK_RE.match(ch) or ch.isalnum()
    ).lower()
    if len(compact_query) >= 2:
        compact_title = "".join(
            ch.lower() for ch in title if CJK_RE.match(ch) or ch.isalnum()
        )
        compact_body = "".join(
            ch.lower() for ch in body if CJK_RE.match(ch) or ch.isalnum()
        )
        if compact_query in compact_title:
            score += 8.0
        elif compact_query in compact_body:
            score += 4.0

    # 4) 英文/数字词命中（产品英文名、版本号等）。
    if query_words:
        body_words = set(_words(body))
        title_words = set(_words(title))
        for w in query_words:
            if w in title_words:
                score += 3.0
            elif w in body_words:
                score += 1.0

    return score


def retrieve(text: str, query: str, top_k: int, chunk_chars: int, overlap_chars: int) -> list[dict[str, Any]]:
    chunks = build_chunks(text, chunk_chars, overlap_chars)
    if not chunks:
        return []

    query = query.strip()
    if not query:
        # 没有 query：返回前 top_k 个片段（通常是公司概述/愿景），作为通用兜底。
        return [
            {"score": 0.0, "title": c["title"], "text": c["text"]}
            for c in chunks[:top_k]
        ]

    query_bigrams = _char_bigrams(query)
    query_words = _words(query)

    scored: list[dict[str, Any]] = []
    for c in chunks:
        s = score_chunk(query, query_bigrams, query_words, c)
        scored.append({"score": round(s, 2), "title": c["title"], "text": c["text"]})

    scored.sort(key=lambda item: item["score"], reverse=True)
    top = [item for item in scored if item["score"] > 0][:top_k]

    # 降级：一个都没命中时，返回开头片段兜底，避免大模型无素材可用。
    if not top:
        top = [
            {"score": 0.0, "title": c["title"], "text": c["text"]}
            for c in chunks[:top_k]
        ]
    return top


def main() -> int:
    parser = argparse.ArgumentParser(description="对知识库文件做轻量检索，返回 top_k 相关片段。")
    parser.add_argument("--query", default="")
    parser.add_argument("--top-k", type=int, default=0, help="覆盖 config.yaml 中的 knowledge.top_k")
    args = parser.parse_args()

    try:
        config = load_config()
        knowledge = config.get("knowledge", {})
        file_path_value = str(knowledge.get("file_path", "")).strip()
        if not file_path_value:
            raise ValueError("必须配置 knowledge.file_path")

        knowledge_file = resolve_skill_path(file_path_value, "")
        if not knowledge_file.exists():
            raise FileNotFoundError(f"知识库文件不存在：{knowledge_file}")

        top_k = args.top_k if args.top_k > 0 else _to_int(knowledge.get("top_k"), DEFAULT_TOP_K)
        chunk_chars = _to_int(knowledge.get("chunk_chars"), DEFAULT_CHUNK_CHARS)
        overlap_chars = _to_int(knowledge.get("overlap_chars"), DEFAULT_OVERLAP_CHARS)
        if overlap_chars >= chunk_chars:
            overlap_chars = DEFAULT_OVERLAP_CHARS

        text = knowledge_file.read_text(encoding="utf-8", errors="replace")
        chunks = retrieve(text, args.query, top_k, chunk_chars, overlap_chars)

        print(
            json_dumps(
                {
                    "exists": True,
                    "path": str(knowledge_file),
                    "query": args.query,
                    "chunk_count": len(chunks),
                    "chunks": chunks,
                }
            )
        )
        return 0
    except (OSError, ValueError) as exc:
        eprint(f"knowledge_retriever 执行失败：{exc}")
        print(json_dumps({"exists": False, "message": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
