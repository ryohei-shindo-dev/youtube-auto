"""repair_top_cards.py — 冒頭に誤挿入されたカードリンクを削除する暫定対応スクリプト。

障害: _append_card_links() がカーソル冒頭のまま URL をペーストし、
      関連リンクカードが記事冒頭に挿入された（3/27: 24記事、3/28: 1記事）。

使い方:
    python repair_top_cards.py              # 全影響記事を修正
    python repair_top_cards.py --dry-run    # 確認のみ（修正しない）
    python repair_top_cards.py --sheet 78   # 特定記事のみ
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).parent.resolve()
load_dotenv(SCRIPT_DIR / ".env")

from note_publish import _launch_browser, _close_browser
from ops_note import SEL, handle_draft_dialog, handle_multi_edit_dialog

MANIFEST_PATH = SCRIPT_DIR / "note_manifest.json"
STATE_PATH = SCRIPT_DIR / "note_body_update_state.json"

# 3/27 + 3/28 に _append_card_links で追加された記事
AFFECTED_SHEETS = [
    32, 38, 39, 40, 46, 65, 67, 69, 70, 71, 72, 73, 74, 76,
    78, 82, 88, 90, 91, 92, 103, 104, 105, 106, 107,
]


def _load_manifest() -> dict:
    rows = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest = {}
    for row in rows:
        if row.get("sheet_no") is not None:
            manifest[int(row["sheet_no"])] = row
    return manifest


def _count_top_cards(page) -> int:
    """エディタ冒頭のカードリンク数を数える。

    ProseMirror の最初の子要素から連続する figure/iframe（カード）を数える。
    テキスト段落が来たら止める。
    """
    return page.evaluate("""() => {
        const editor = document.querySelector('.ProseMirror[role="textbox"]');
        if (!editor) return 0;
        let count = 0;
        for (const child of editor.children) {
            const tag = child.tagName.toLowerCase();
            // カード系要素: figure, iframe を含むdiv
            if (tag === 'figure' || child.querySelector('iframe') || child.querySelector('[data-embed-card]')) {
                count++;
            } else if (tag === 'p' && !child.textContent.trim()) {
                // 空段落はスキップ
                continue;
            } else {
                // テキスト段落に到達したら終了
                break;
            }
        }
        return count;
    }""")


def _delete_top_cards(page, count: int):
    """エディタ冒頭のカード count 個を削除する。"""
    body = page.locator(SEL["body"])
    body.click()
    time.sleep(0.3)

    # 先頭にカーソル移動
    page.keyboard.press("Meta+ArrowUp")
    time.sleep(0.3)

    for i in range(count):
        # 先頭の要素を選択して削除
        # figure/embed は1回の ArrowDown + Backspace or Delete で消える
        page.keyboard.press("ArrowDown")
        time.sleep(0.2)
        page.keyboard.press("Backspace")
        time.sleep(0.5)

        # 削除後に残った空段落も消す
        remaining_empty = page.evaluate("""() => {
            const editor = document.querySelector('.ProseMirror[role="textbox"]');
            if (!editor || !editor.firstChild) return false;
            const first = editor.firstChild;
            return first.tagName === 'P' && !first.textContent.trim();
        }""")
        if remaining_empty:
            page.keyboard.press("Meta+ArrowUp")
            time.sleep(0.1)
            page.keyboard.press("Delete")
            time.sleep(0.3)

    time.sleep(0.5)


def _save_article(page) -> str:
    """記事を保存する。"""
    page.keyboard.press("Escape")
    time.sleep(1)
    publish_nav = page.wait_for_selector(
        'button:has-text("公開に進む")', timeout=10000
    )
    publish_nav.click()
    page.wait_for_load_state("networkidle")
    time.sleep(2)
    save_btn = page.wait_for_selector(
        'button:has-text("更新する"), button:has-text("予約投稿")',
        timeout=10000,
    )
    btn_text = save_btn.text_content().strip()
    save_btn.click()
    time.sleep(5)
    return btn_text


def repair_one(page, art: dict, expected_cards: int, dry_run: bool) -> str:
    """1記事の冒頭カードを修正する。"""
    key = art["note_key"]
    edit_url = f"https://editor.note.com/notes/{key}/edit/"

    page.goto(edit_url)
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    handle_draft_dialog(page)
    handle_multi_edit_dialog(page)

    page.wait_for_selector(SEL["body"], timeout=10000)
    time.sleep(1)

    top_cards = _count_top_cards(page)
    if top_cards == 0:
        return "skip:no_top_cards"

    print(f"    冒頭にカード {top_cards} 個検出（想定 {expected_cards} 個）")

    if dry_run:
        return f"dry_run:found_{top_cards}"

    _delete_top_cards(page, top_cards)

    # 確認
    remaining = _count_top_cards(page)
    if remaining > 0:
        print(f"    [警告] まだ冒頭に {remaining} 個残っています")
        return "partial"

    btn_text = _save_article(page)
    print(f"    修正完了（{btn_text}）")
    return "ok"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sheet", type=int, help="特定の sheet_no のみ修正")
    args = parser.parse_args()

    manifest = _load_manifest()
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    cards_state = state.get("cards", {})

    targets = [args.sheet] if args.sheet else AFFECTED_SHEETS

    print(f"対象: {len(targets)} 記事{'（dry-run）' if args.dry_run else ''}")

    pw, context, page = _launch_browser(headless=False)
    try:
        ok = skip = fail = 0
        for i, sn in enumerate(targets, 1):
            art = manifest.get(sn)
            if not art or not art.get("note_key"):
                print(f"[{i}/{len(targets)}] #{sn}: manifest にないためスキップ")
                skip += 1
                continue

            expected = len(cards_state.get(str(sn), []))
            title = art.get("sheet_title", art.get("title", ""))[:50]
            print(f"[{i}/{len(targets)}] #{sn} {title}… (+{expected}カード)")

            try:
                result = repair_one(page, art, expected, args.dry_run)
                if "ok" in result:
                    ok += 1
                elif "skip" in result or "dry_run" in result:
                    skip += 1
                    print(f"    → {result}")
                else:
                    fail += 1
            except Exception as e:
                print(f"    エラー: {e}")
                fail += 1

        print(f"\n完了: 修正 {ok} / スキップ {skip} / 失敗 {fail}")
    finally:
        _close_browser(pw, context)


if __name__ == "__main__":
    main()
