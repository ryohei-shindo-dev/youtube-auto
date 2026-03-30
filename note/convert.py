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
        # 空行
        if not stripped:
            parts.append("<p><br></p>")
            continue
        # 太字 → b タグ、通常行 → p
        escaped = _html_escape(line)
        text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
        parts.append(f"<p>{text}</p>")

    html = "\n".join(parts)
    # 連続する空段落を最大2個に制限
    empty = "<p><br></p>"
    while f"{empty}\n{empty}\n{empty}" in html:
        html = html.replace(f"{empty}\n{empty}\n{empty}", f"{empty}\n{empty}")
    return html.strip(), url_lines


def _split_body_into_blocks(body: str) -> list[dict]:
    """本文を空行区切りの小ブロック列に分解する。

    URL単独行は {"type": "card", "url": "..."} に、
    それ以外は段落単位で {"type": "html", "html": "..."} にする。
    巨大htmlブロックを避け、insertHTML後のカーソル位置ズレを防ぐ。
    """
    blocks: list[dict] = []
    raw_blocks = re.split(r"\n\s*\n", body.strip())

    for raw in raw_blocks:
        text = raw.strip()
        if not text:
            continue

        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

        # URL単独行はcard
        if len(lines) == 1 and _URL_LINE_RE_PUBLISH.match(lines[0]):
            blocks.append({"type": "card", "url": lines[0]})
            continue

        # 複数行のURL連続（あわせて読みたいの2本等）を個別cardに分解
        if all(_URL_LINE_RE_PUBLISH.match(ln) for ln in lines):
            for ln in lines:
                blocks.append({"type": "card", "url": ln})
            continue

        # 通常テキスト → HTML変換
        html, _ = _split_body_for_note(text)
        if html.strip():
            blocks.append({"type": "html", "html": html})

    return blocks
