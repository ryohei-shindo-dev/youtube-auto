"""note記事の高レベルワークフロー。

note_ops.py の低レベル操作を組み合わせて、
投稿・更新・リンク修正などの業務手順を提供する。

使い方:
    from note_workflows import publish_article, rewrite_body, replace_links, verify_article
"""
from __future__ import annotations

import json
import pathlib
import time
from typing import Optional

from playwright.sync_api import Page

from note_ops import (
    SEL,
    open_editor,
    dismiss_modals,
    handle_draft_dialog,
    handle_multi_edit_dialog,
    go_to_publish,
    finalize,
    find_card,
    replace_card,
    cleanup_empty_paragraphs,
)
from note_publish import (
    _launch_browser,
    _close_browser,
    _split_body_into_blocks,
    _insert_body_blocks,
    _validate_card_links,
    _split_body_for_note,
)

SCRIPT_DIR = pathlib.Path(__file__).parent
MANIFEST_PATH = SCRIPT_DIR / "note_manifest.json"


# ── 検証 ──

def verify_article(page: Page, note_id: str) -> dict:
    """公開ページを検証して問題を検出する。

    Returns:
        {"ok": bool, "issues": list[str], "cards": list[str], "title": str}
    """
    page.goto(f"https://note.com/gachiho_motive/n/{note_id}")
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    issues = []

    # 「この記事は閲覧できません」チェック
    blocked = page.locator('text=この記事は閲覧できません').count()
    if blocked > 0:
        issues.append(f"「閲覧できません」カード: {blocked}個")

    # カードURL一覧
    cards = []
    elements = page.evaluate("""
        () => {
            const article = document.querySelector('.note-common-styles__textnote-body') || document.body;
            const cards = [];
            article.querySelectorAll('figure').forEach(fig => {
                const iframe = fig.querySelector('iframe');
                if (iframe && iframe.src) {
                    const m = iframe.src.match(/notes\\/(n[a-f0-9]+)/);
                    if (m) cards.push(m[1]);
                }
            });
            return cards;
        }
    """)
    cards = elements

    # 有料記事リンクチェック
    body_text = page.inner_text("body")
    try:
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            manifest = json.load(f)
        paid_keys = [
            a.get("note_key") for a in manifest
            if (a.get("content_type") == "paid" or "paid" in (a.get("md_path") or ""))
            and a.get("note_key")
        ]
        for pk in paid_keys:
            if pk in body_text:
                issues.append(f"有料記事URL残存: {pk}")
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # カード前後の空段落チェック
    dom_elements = page.evaluate("""
        () => {
            const article = document.querySelector('.note-common-styles__textnote-body') || document.body;
            const result = [];
            const walk = (node) => {
                for (const child of node.children) {
                    if (child.tagName === 'FIGURE') {
                        result.push({type: 'CARD'});
                    } else if (child.tagName === 'P') {
                        result.push({type: child.textContent.trim() ? 'P' : 'EMPTY'});
                    } else if (child.children && child.children.length > 0) {
                        walk(child);
                    }
                }
            };
            walk(article);
            return result;
        }
    """)
    for i, el in enumerate(dom_elements):
        if el["type"] == "CARD":
            if i > 0 and dom_elements[i - 1]["type"] == "EMPTY":
                issues.append("カード前に空段落")
                break
            if i < len(dom_elements) - 1 and dom_elements[i + 1]["type"] == "EMPTY":
                # カード後の空段落はカード連続の間は許容
                if i + 1 < len(dom_elements) - 1 and dom_elements[i + 2].get("type") != "CARD":
                    issues.append("カード後に空段落")
                    break

    title = page.title().split("｜")[0].strip()

    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "cards": cards,
        "title": title,
    }


def verify_and_report(page: Page, note_id: str) -> bool:
    """検証して結果を表示。問題なければTrue。"""
    result = verify_article(page, note_id)
    if result["ok"]:
        print(f"  ✅ 検証OK: {result['title'][:30]} (カード{len(result['cards'])}本)")
        return True
    else:
        print(f"  ❌ 検証NG: {result['title'][:30]}")
        for issue in result["issues"]:
            print(f"    - {issue}")
        return False
