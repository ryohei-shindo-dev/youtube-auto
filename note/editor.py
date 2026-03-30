"""note エディタへのブロック挿入操作.

Playwright に依存する UI操作関数を提供する。
"""
from __future__ import annotations

import json
import pathlib
import re
import time

from playwright.sync_api import Page

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent.parent
MANIFEST_PATH = SCRIPT_DIR / "data" / "manifests" / "note_manifest.json"

# note埋め込みカード検出用セレクタ
_EMBED_SELECTORS = [
    'div.ProseMirror iframe',
    'div.ProseMirror [data-embed-card]',
    'div.ProseMirror .embed-card',
    'div.ProseMirror [class*="embed"]',
]


def _validate_card_links(blocks: list[dict]):
    """cardブロックのリンク先が公開済み無料記事かを検証する。

    有料記事・未公開記事へのリンクカードは「この記事は閲覧できません」になるため、
    事前にブロックして事故を防ぐ。
    """
    try:
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            manifest = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return  # manifestがない場合はスキップ

    # note_key → 記事情報のマッピング
    key_to_info = {}
    for a in manifest:
        key = a.get("note_key") or ""
        if key:
            key_to_info[key] = {
                "title": (a.get("sheet_title") or "")[:40],
                "url": a.get("url") or "",
                "content_type": a.get("content_type") or "",
                "md_path": a.get("md_path") or "",
            }

    for block in blocks:
        if block["type"] != "card":
            continue
        url = block["url"]
        # URLからnote_keyを抽出
        m = re.search(r"/n/(n[a-f0-9]+)", url)
        if not m:
            continue
        note_key = m.group(1)
        info = key_to_info.get(note_key)
        if not info:
            continue

        # 有料記事チェック
        if info["content_type"] == "paid" or "paid" in info["md_path"]:
            raise ValueError(
                f"有料記事へのリンクカードは「閲覧できません」になります: "
                f"{note_key} ({info['title']})"
            )

        # 未公開チェック（URLが空 = 未公開）
        if not info["url"]:
            raise ValueError(
                f"未公開記事へのリンクカードは「閲覧できません」になります: "
                f"{note_key} ({info['title']})"
            )


def _focus_body_end(page, body_sel: str = 'div.ProseMirror[role="textbox"]'):
    """本文エディタ末尾にカーソルを確実に移動する。"""
    try:
        body_loc = page.locator(body_sel)
        body_loc.click()
        time.sleep(0.15)
        page.keyboard.press("Meta+ArrowDown")
        time.sleep(0.15)
        # フォールバック: 最終段落にフォーカス
        page.evaluate("""() => {
            const editor = document.querySelector('div.ProseMirror[role="textbox"]');
            if (!editor) return;
            const last = editor.lastElementChild;
            if (last) {
                const sel = window.getSelection();
                const range = document.createRange();
                range.selectNodeContents(last);
                range.collapse(false);
                sel.removeAllRanges();
                sel.addRange(range);
            }
        }""")
        time.sleep(0.15)
    except Exception:
        page.keyboard.press("Meta+ArrowDown")
        time.sleep(0.2)


def _verify_card_order(page, expected_urls: list[str]) -> bool:
    """挿入後のカード順序が期待通りか検証する。"""
    if not expected_urls:
        return True

    try:
        actual_urls = page.evaluate("""() => {
            const editor = document.querySelector('div.ProseMirror[role="textbox"]');
            if (!editor) return [];
            const urls = [];
            // iframe src からURL抽出
            editor.querySelectorAll('iframe').forEach(iframe => {
                const src = iframe.getAttribute('src') || '';
                const m = src.match(/note\\.com\\/[^/]+\\/n\\/[a-z0-9]+/);
                if (m) urls.push('https://' + m[0]);
            });
            // data-embed-card / href からURL抽出
            if (urls.length === 0) {
                editor.querySelectorAll('[data-embed-card], [class*="embed"] a').forEach(el => {
                    const href = el.getAttribute('href') || el.getAttribute('data-embed-card') || '';
                    if (href.includes('note.com')) urls.push(href);
                });
            }
            return urls;
        }""")

        if len(actual_urls) != len(expected_urls):
            print(f"  [検証警告] カード数不一致: 期待{len(expected_urls)}本, 実際{len(actual_urls)}本")
            return False

        for i, (expected, actual) in enumerate(zip(expected_urls, actual_urls)):
            exp_key = expected.rstrip("/").split("/")[-1]
            if exp_key not in actual:
                print(f"  [検証警告] カード{i+1}位置ずれ: 期待={exp_key}, 実際={actual[:60]}")
                return False

        print(f"  カード順序検証OK（{len(expected_urls)}本）")
        return True

    except Exception as e:
        print(f"  [検証警告] カード順序検証失敗: {e}")
        return False


def _count_embed_cards(page) -> int:
    """現在の埋め込みカード数を返す（複数セレクタの最大値）。"""
    max_count = 0
    for sel in _EMBED_SELECTORS:
        count = page.locator(sel).count()
        max_count = max(max_count, count)
    return max_count


def _wait_for_embed_card(page, before_count: int, timeout: int = 5000) -> bool:
    """埋め込みカードが新たに出現したかを判定する。"""
    deadline = time.time() + timeout / 1000
    while time.time() < deadline:
        for sel in _EMBED_SELECTORS:
            if page.locator(sel).count() > before_count:
                return True
        time.sleep(0.3)
    return False


# --- ブロック境界の空白規則 ---
# html → html : Enter で改段落
# html → card : Enter で改段落（カードの前に空行）
# card → html : Enter 不要（カード変換後に自動で空段落が入る）
# card → card : Enter 不要（同上）


def _insert_body_blocks(page, blocks: list[dict]):
    """ブロック列を出現順どおりに挿入する。

    htmlブロックはinsertHTMLで、cardブロックはpress_sequentiallyでカード変換。
    挿入後にカード順序を検証する。
    """
    # リンク先の事前バリデーション
    _validate_card_links(blocks)

    body_sel = 'div.ProseMirror[role="textbox"]'
    expected_card_urls = [b["url"] for b in blocks if b["type"] == "card"]

    try:
        body_loc = page.locator(body_sel)
        body_loc.wait_for(timeout=10000)
        body_loc.click()

        prev_type = None
        for i, block in enumerate(blocks):
            if block["type"] == "html":
                if prev_type != "card" and i > 0:
                    page.keyboard.press("Enter")
                    time.sleep(0.2)
                page.evaluate(
                    """html => {
                        document.execCommand('insertHTML', false, html);
                    }""",
                    block["html"],
                )
                time.sleep(0.5)
                _focus_body_end(page, body_sel)

            elif block["type"] == "card":
                before_count = _count_embed_cards(page)
                if prev_type != "card":
                    page.keyboard.press("Enter")
                    time.sleep(0.3)
                body_loc.press_sequentially(block["url"], delay=15)
                body_loc.press("Enter")

                embedded = _wait_for_embed_card(page, before_count, timeout=8000)
                if embedded:
                    print(f"    カード変換成功: {block['url'][:50]}")
                else:
                    print(f"    [警告] カード変換未確認: {block['url'][:50]}")
                    time.sleep(1)

            prev_type = block["type"]

        time.sleep(1)
        print(f"  ブロック挿入完了（{len(blocks)}ブロック）")
        _verify_card_order(page, expected_card_urls)

    except Exception as e:
        print(f"  [エラー] ブロック挿入失敗: {e}")
        raise


def _insert_body_with_cards(page: Page, body_html: str, url_lines: list[str]):
    """本文をinsertHTML + URL行をカード変換で入力する（互換レイヤ）。"""
    blocks: list[dict] = []
    if body_html.strip():
        blocks.append({"type": "html", "html": body_html})
    for url in (url_lines or []):
        blocks.append({"type": "card", "url": url})

    _insert_body_blocks(page, blocks)
