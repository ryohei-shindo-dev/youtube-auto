"""Markdown → note HTML 変換ユーティリティ.

Playwright に依存しない純粋な変換関数を提供する。
"""
from __future__ import annotations

import re
from html import escape as _html_escape

_URL_LINE_RE_PUBLISH = re.compile(r"^https?://\S+$")
_QUOTE_RE = re.compile(r"^>\s*(.+)$")
_LIST_RE = re.compile(r"^[-*]\s+(.+)$")


def _markdown_to_note_html(body: str) -> str:
    """Markdown を note エディタの HTML に変換する（後方互換）。

    URL行もHTMLに含む。insertHTML専用で使う場合のみ。
    新規投稿では _split_body_for_note() を推奨。
    """
    html, _ = _split_body_for_note(body)
    return html


def _split_body_for_note(body: str) -> tuple[str, list[str]]:
    """Markdown本文をHTML部分とURL行リストに分離する。

    Returns:
        (html, url_lines): htmlはinsertHTML用、url_linesはpress_sequentially用
    """
    parts: list[str] = []
    url_lines: list[str] = []

    for raw_line in body.split("\n"):
        line = raw_line.rstrip()
        stripped = line.strip()

        # URL行は分離（カード変換用にpress_sequentiallyで入力する）
        if _URL_LINE_RE_PUBLISH.match(stripped):
            url_lines.append(stripped)
            continue

        # --- → 区切り線
        if re.match(r"^-{3,}$", stripped):
            parts.append("<hr>")
            continue
        # ## 見出し → h3
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            heading = re.sub(r"\*\*(.+?)\*\*", r"\1", m.group(1))
            parts.append(f"<h3>{_html_escape(heading)}</h3>")
            continue
        # > 引用 → blockquote
        m_quote = _QUOTE_RE.match(stripped)
        if m_quote:
            escaped = _html_escape(m_quote.group(1))
            text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
            parts.append(f"<blockquote><p>{text}</p></blockquote>")
            continue
        # - リスト → ul/li（連続する - 行をまとめる）
        m_list = _LIST_RE.match(stripped)
        if m_list:
            escaped = _html_escape(m_list.group(1))
            text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
            # 直前がliなら同じulに追加、そうでなければ新しいulを開始
            if parts and parts[-1].endswith("</li></ul>"):
                # 既存ulの末尾に追加
                parts[-1] = parts[-1][:-5] + f"<li>{text}</li></ul>"
            else:
                parts.append(f"<ul><li>{text}</li></ul>")
            continue
        # 空行は段落区切りとして扱い、明示的な <p><br></p> は作らない。
        # note 側の段落余白だけで十分で、ここで空段落を作ると
        # 公開面で不自然な大きい空白になる。
        if not stripped:
            continue
        # 太字 → b タグ、通常行 → p
        escaped = _html_escape(line)
        text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
        parts.append(f"<p>{text}</p>")

    html = "\n".join(parts)
    return html.strip(), url_lines


def _split_body_into_blocks(body: str) -> list[dict]:
    """本文を note 挿入用の小ブロック列に分解する。

    URL行が見出しや本文と同じ空行ブロックに混在していても、
    順序を保ったまま html / card に分割する。
    """
    blocks: list[dict] = []
    text_buffer: list[str] = []

    def flush_text() -> None:
        if not text_buffer:
            return
        html, _ = _split_body_for_note("\n".join(text_buffer).strip())
        if html.strip():
            blocks.append({"type": "html", "html": html})
        text_buffer.clear()

    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if _URL_LINE_RE_PUBLISH.match(stripped):
            flush_text()
            blocks.append({"type": "card", "url": stripped})
            continue

        if not stripped:
            if text_buffer:
                text_buffer.append("")
            continue

        text_buffer.append(line)

    flush_text()
    return blocks
