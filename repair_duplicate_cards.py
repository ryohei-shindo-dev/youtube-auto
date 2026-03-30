"""repair_duplicate_cards.py — 末尾の重複カード・余分な空白行を削除する（追加はしない）。

方針:
- 末尾の重複カードのみ削除（同じURLのカードが2つあれば1つに）
- 余分な空白行を整理
- カードの追加は一切しない
- 本文途中は触らない

使い方:
    python repair_duplicate_cards.py --dry-run    # 検出のみ（修正しない）
    python repair_duplicate_cards.py              # 全影響記事を修復
    python repair_duplicate_cards.py --sheet 78   # 特定記事のみ
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

MANIFEST_PATH = SCRIPT_DIR / "data" / "manifests" / "note_manifest.json"
STATE_PATH = SCRIPT_DIR / "data" / "state" / "note_body_update_state.json"
DEBUG_DIR = SCRIPT_DIR / "debug"

# 影響記事（3/27〜28 の _append_card_links 対象）
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


def _analyze_cards(page) -> dict:
    """エディタ内の全カード（iframe/embed）の位置とURLを分析する。"""
    return page.evaluate("""() => {
        const editor = document.querySelector('.ProseMirror[role="textbox"]');
        if (!editor) return {cards: [], totalChildren: 0, trailingBlanks: 0};

        const children = Array.from(editor.children);
        const cards = [];

        children.forEach((child, idx) => {
            // iframe を持つ要素はカード
            const iframe = child.querySelector('iframe');
            if (iframe) {
                const src = iframe.getAttribute('src') || '';
                // note の embed URL からキーを抽出
                const match = src.match(/note\\.com\\/embed\\/notes\\/(n[a-f0-9]+)/);
                cards.push({
                    index: idx,
                    noteKey: match ? match[1] : null,
                    src: src,
                    isTop: idx < children.length / 2,
                });
            }
            // data-embed-card 属性を持つ要素
            const embed = child.querySelector('[data-embed-card]');
            if (embed && !iframe) {
                cards.push({
                    index: idx,
                    noteKey: null,
                    src: embed.getAttribute('data-embed-card') || '',
                    isTop: idx < children.length / 2,
                });
            }
        });

        // 末尾の空行数
        let trailingBlanks = 0;
        for (let i = children.length - 1; i >= 0; i--) {
            const tag = children[i].tagName.toLowerCase();
            if (tag === 'p' && !children[i].textContent.trim()) {
                trailingBlanks++;
            } else {
                break;
            }
        }

        return {
            cards: cards,
            totalChildren: children.length,
            trailingBlanks: trailingBlanks,
        };
    }""")


def _find_duplicates(cards: list) -> list[int]:
    """重複カードのインデックスを特定する（後ろにあるものを削除対象にする）。"""
    seen = {}
    duplicates = []
    for card in cards:
        key = card.get("noteKey") or card.get("src")
        if not key:
            continue
        if key in seen:
            # 後の方を削除対象に
            duplicates.append(card["index"])
        else:
            seen[key] = card["index"]
    return duplicates


def _delete_elements_by_index(page, indices: list[int]):
    """指定インデックスの要素を削除する（後ろから削除してインデックスずれを防ぐ）。"""
    # 後ろから削除
    for idx in sorted(indices, reverse=True):
        page.evaluate("""(idx) => {
            const editor = document.querySelector('.ProseMirror[role="textbox"]');
            if (!editor || idx >= editor.children.length) return;
            editor.children[idx].remove();
        }""", idx)
        time.sleep(0.3)


def _trim_trailing_blanks(page, keep: int = 1):
    """末尾の空白行を整理する（keep個だけ残す）。"""
    page.evaluate("""(keep) => {
        const editor = document.querySelector('.ProseMirror[role="textbox"]');
        if (!editor) return;
        let removed = 0;
        while (editor.lastChild) {
            const last = editor.lastChild;
            if (last.tagName && last.tagName.toLowerCase() === 'p' && !last.textContent.trim()) {
                // 空のp要素
                // keepの数だけ残す
                const remaining = Array.from(editor.children).filter(
                    c => c.tagName.toLowerCase() === 'p' && !c.textContent.trim()
                );
                // 末尾連続の空行のみカウント
                let trailingCount = 0;
                for (let i = editor.children.length - 1; i >= 0; i--) {
                    const c = editor.children[i];
                    if (c.tagName.toLowerCase() === 'p' && !c.textContent.trim()) {
                        trailingCount++;
                    } else {
                        break;
                    }
                }
                if (trailingCount > keep) {
                    last.remove();
                    removed++;
                } else {
                    break;
                }
            } else {
                break;
            }
        }
        return removed;
    }""", keep)


def _trigger_prosemirror_change(page):
    """ProseMirrorにDOM変更を検知させる（更新ボタンを出すため）。"""
    page.evaluate("""() => {
        const editor = document.querySelector('.ProseMirror[role="textbox"]');
        if (!editor) return;
        // ダミー入力→削除で変更フラグを立てる
        const event = new InputEvent('input', {bubbles: true, inputType: 'insertText', data: ' '});
        editor.dispatchEvent(event);
    }""")
    time.sleep(0.3)
    # 実際にスペース入力→削除
    body = page.locator(SEL["body"])
    body.click()
    time.sleep(0.2)
    page.keyboard.press("Meta+ArrowDown")
    time.sleep(0.2)
    page.keyboard.type(" ")
    time.sleep(0.2)
    page.keyboard.press("Backspace")
    time.sleep(0.3)


def _save_article(page) -> str:
    """記事を保存する。"""
    page.keyboard.press("Escape")
    time.sleep(1)
    publish_nav = page.wait_for_selector(
        'button:has-text("公開に進む")', timeout=10000
    )
    publish_nav.click()
    page.wait_for_load_state("domcontentloaded")
    time.sleep(2)
    save_btn = page.wait_for_selector(
        'button:has-text("更新する"), button:has-text("予約投稿")',
        timeout=10000,
    )
    btn_text = save_btn.text_content().strip()
    save_btn.click()
    time.sleep(5)
    return btn_text


def repair_one(page, art: dict, dry_run: bool) -> str:
    """1記事の重複カード・空白行を修復する。"""
    key = art["note_key"]
    edit_url = f"https://editor.note.com/notes/{key}/edit/"

    page.goto(edit_url)
    page.wait_for_load_state("domcontentloaded")
    time.sleep(3)

    handle_draft_dialog(page)
    handle_multi_edit_dialog(page)

    page.wait_for_selector(SEL["body"], timeout=10000)
    time.sleep(1)

    # 分析
    analysis = _analyze_cards(page)
    cards = analysis["cards"]
    trailing = analysis["trailingBlanks"]

    duplicates = _find_duplicates(cards)
    needs_blank_trim = trailing > 1

    if not duplicates and not needs_blank_trim:
        return "skip:clean"

    issues = []
    if duplicates:
        issues.append(f"重複カード{len(duplicates)}個")
    if needs_blank_trim:
        issues.append(f"末尾空白{trailing}行→1行に")

    print(f"    問題: {', '.join(issues)}")

    if dry_run:
        return f"dry_run:{'_'.join(issues)}"

    # 修復実行
    if duplicates:
        print(f"    重複カード削除中（{len(duplicates)}個）...")
        _delete_elements_by_index(page, duplicates)
        time.sleep(0.5)

    if needs_blank_trim:
        print(f"    末尾空白行を整理中...")
        _trim_trailing_blanks(page, keep=1)
        time.sleep(0.3)

    # ProseMirrorに変更を検知させる
    _trigger_prosemirror_change(page)
    time.sleep(0.5)

    # 保存
    btn_text = _save_article(page)
    print(f"    保存完了（{btn_text}）")

    # 修復後検証
    time.sleep(2)
    page.goto(edit_url)
    page.wait_for_load_state("domcontentloaded")
    time.sleep(3)
    handle_draft_dialog(page)
    handle_multi_edit_dialog(page)
    page.wait_for_selector(SEL["body"], timeout=10000)
    time.sleep(1)

    post_analysis = _analyze_cards(page)
    post_dupes = _find_duplicates(post_analysis["cards"])
    if post_dupes:
        print(f"    [警告] まだ重複が{len(post_dupes)}個残っています")
        return "partial"

    return "ok"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="検出のみ（修正しない）")
    parser.add_argument("--sheet", type=int, help="特定の sheet_no のみ修正")
    args = parser.parse_args()

    manifest = _load_manifest()
    targets = [args.sheet] if args.sheet else AFFECTED_SHEETS
    DEBUG_DIR.mkdir(exist_ok=True)

    print(f"対象: {len(targets)} 記事{'（dry-run）' if args.dry_run else ''}")
    print("方針: 重複カード削除 + 空白行整理のみ。カード追加はしない。\n")

    if not args.dry_run:
        pw, context, page = _launch_browser(headless=False)
    else:
        # dry-run でもブラウザが必要（分析のため）
        pw, context, page = _launch_browser(headless=False)

    try:
        ok = skip = fail = 0
        for i, sn in enumerate(targets, 1):
            art = manifest.get(sn)
            if not art or not art.get("note_key"):
                print(f"[{i}/{len(targets)}] #{sn}: manifest にないためスキップ")
                skip += 1
                continue

            title = art.get("sheet_title", "")[:50]
            print(f"[{i}/{len(targets)}] #{sn} {title}")

            try:
                result = repair_one(page, art, args.dry_run)
                if "ok" in result:
                    ok += 1
                elif "skip" in result:
                    skip += 1
                    print(f"    → 正常（修正不要）")
                elif "dry_run" in result:
                    skip += 1
                else:
                    fail += 1
            except Exception as e:
                print(f"    エラー: {e}")
                fail += 1

            if i < len(targets):
                time.sleep(3)

        print(f"\n完了: 修正 {ok} / 正常 {skip} / 失敗 {fail}")
    finally:
        _close_browser(pw, context, wait_for_user=False)


if __name__ == "__main__":
    main()
