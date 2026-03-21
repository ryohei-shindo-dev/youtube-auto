# [廃止予定] note_tool.py + note_ops.py に統合済み。このファイルは互換性のため残しているが、新規利用禁止。
"""
fix_note_link_cards.py
予約投稿中のnote記事のリンクをカード化する修正スクリプト。

方式: 本文全体を再投入（末尾だけの部分削除はしない）
1. scheduled_notes.json のIDで直接編集URLを開く
2. Ctrl+A で全選択 → 削除
3. ローカルmdファイルから本文全体を再投入（URL行はカード化）
4. 保存前に検証（文字数・先頭テキスト・カード数）
5. 下書き保存

使い方:
    python fix_note_link_cards.py --test       # 1本だけテスト
    python fix_note_link_cards.py --fix-all    # 全予約記事を修正
    python fix_note_link_cards.py --id nXXX    # 特定IDだけ修正
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import time

from playwright.sync_api import Page

from note_publish import _launch_browser, _close_browser
from note_publish_additional import (
    _URL_LINE_RE, _EMBED_SELECTORS, _count_embed_cards,
    _upload_header_image, _go_publish,
)

SCRIPT_DIR = pathlib.Path(__file__).parent
SCHEDULED_FILE = SCRIPT_DIR / "scheduled_notes.json"
ARTICLES_DIR = SCRIPT_DIR / "note_articles"

# カード修正不要のID（新方式で投稿済み）
SKIP_IDS = {"ne16fb9dfd529"}

# 保存前の安全チェック閾値
MIN_BODY_LENGTH = 200  # 本文がこれ以下なら保存しない


def _load_scheduled_notes() -> list[dict]:
    with open(SCHEDULED_FILE, encoding="utf-8") as f:
        data = json.load(f)
    return [n for n in data.get("notes", []) if n["id"] not in SKIP_IDS]


def _find_article_file(title: str) -> pathlib.Path | None:
    """タイトルからローカルのmdファイルを特定する。
    タイトル部分一致 → ファイル名キーワード一致の順で検索。
    """
    # 1. タイトル部分一致（先頭15文字）
    for md_file in ARTICLES_DIR.glob("*.md"):
        text = md_file.read_text(encoding="utf-8")
        file_title = ""
        for line in text.split("\n"):
            if line.startswith("# "):
                file_title = line[2:].strip()
                break
        if file_title and (title[:15] in file_title or file_title[:15] in title):
            return md_file

    # 2. ファイル名にタイトルのキーワードが含まれるか
    keywords = [w for w in re.split(r"[。、｜\s]+", title) if len(w) >= 3]
    for md_file in ARTICLES_DIR.glob("*.md"):
        fname = md_file.stem
        if any(kw in fname for kw in keywords):
            return md_file

    return None


def _parse_article(md_file: pathlib.Path) -> tuple[str, str]:
    """mdファイルからタイトルと本文を分離する。"""
    text = md_file.read_text(encoding="utf-8")
    title = ""
    body_lines = []
    for line in text.split("\n"):
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        else:
            body_lines.append(line)
    return title, "\n".join(body_lines).strip()


def _dismiss_modals(page: Page):
    for selector in [
        'div[role="dialog"] button[aria-label="閉じる"]',
        'div[role="dialog"] button:has-text("閉じる")',
        'div.o-userPopup button',
        'button:has-text("あとで")',
    ]:
        try:
            el = page.locator(selector)
            if el.count() > 0:
                el.first.click(force=True)
                time.sleep(0.5)
        except Exception:
            pass


def _fill_editor_with_cards(page: Page, body_text: str) -> int:
    """本文をエディタに入力する。URL行はカード化する。

    Returns: カード化成功数
    """
    body = page.locator('div.ProseMirror[role="textbox"]')
    body.click()

    card_count = 0
    for line in body_text.splitlines():
        stripped = line.strip()

        if _URL_LINE_RE.match(stripped):
            before = _count_embed_cards(page)
            body.press_sequentially(stripped, delay=15)
            body.press("Enter")

            # カード変換待ち（最大5秒）
            deadline = time.time() + 5
            embedded = False
            while time.time() < deadline:
                for sel in _EMBED_SELECTORS:
                    if page.locator(sel).count() > before:
                        embedded = True
                        break
                if embedded:
                    break
                time.sleep(0.3)

            if embedded:
                card_count += 1
                print(f"      カード変換成功: {stripped[:50]}")
            else:
                print(f"      [警告] カード変換未確認: {stripped[:50]}")
                body.press("Enter")
                time.sleep(1)
        else:
            if line:
                body.press_sequentially(line, delay=3)
            body.press("Enter")

    return card_count


def _fix_one_article(page: Page, note_id: str, title: str, md_file: pathlib.Path) -> bool:
    """1記事を全文再投入で修正する。"""
    file_title, body_text = _parse_article(md_file)

    # URL数を事前カウント
    expected_urls = sum(1 for l in body_text.splitlines() if _URL_LINE_RE.match(l.strip()))

    edit_url = f"https://editor.note.com/notes/{note_id}/edit/"
    print(f"    編集画面を開きます...")
    page.goto(edit_url)
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    _dismiss_modals(page)

    # 「公開した時点の記事」「最新の下書き」の選択ダイアログが出る場合
    try:
        published_btn = page.locator('text="公開した時点の記事"')
        if published_btn.count() > 0:
            published_btn.click()
            time.sleep(2)
            print("    「公開した時点の記事」を選択")
    except Exception:
        pass

    body = page.locator('div.ProseMirror[role="textbox"]')
    if body.count() == 0:
        print("    [エラー] エディタが見つかりません")
        return False

    # 元の本文を取得（検証用）
    original_text = body.inner_text().strip()
    original_length = len(original_text)
    original_head = original_text[:50]
    print(f"    元の本文: {original_length}文字, 先頭: {original_head[:30]}...")

    # 既にカードが十分あるかチェック
    existing_cards = _count_embed_cards(page)
    if existing_cards >= expected_urls:
        print(f"    [スキップ] 既にカード{existing_cards}個（期待{expected_urls}個）")
        return True

    # --- 全選択 → 削除 → 再投入 ---
    print(f"    全文再投入開始（URL{expected_urls}個をカード化）...")

    # タイトルは変更しない。本文だけ全選択→削除
    body.click()
    page.keyboard.press("Meta+a")
    time.sleep(0.3)
    page.keyboard.press("Backspace")
    time.sleep(0.5)

    # 本文を再投入
    card_count = _fill_editor_with_cards(page, body_text)

    # --- 保存前検証 ---
    time.sleep(1)
    new_text = body.inner_text().strip()
    new_length = len(new_text)
    new_cards = _count_embed_cards(page)

    print(f"    検証: 文字数 {original_length} → {new_length}, カード {existing_cards} → {new_cards}")

    # 安全チェック
    if new_length < MIN_BODY_LENGTH:
        print(f"    [中断] 本文が短すぎます（{new_length}文字 < {MIN_BODY_LENGTH}）。保存しません。")
        print(f"    ブラウザで手動確認してください。")
        page.pause()
        return False

    if "あわせて読みたい" not in new_text and expected_urls > 0:
        print(f"    [中断] 「あわせて読みたい」が見つかりません。保存しません。")
        page.pause()
        return False

    # 「公開に進む」→ 予約日時維持 → 「予約投稿」で正式保存
    try:
        # まずEscapeでエディタからフォーカスを外す
        page.keyboard.press("Escape")
        time.sleep(1)

        publish_nav = page.wait_for_selector('button:has-text("公開に進む")', timeout=10000)
        publish_nav.click()
        page.wait_for_load_state("networkidle")
        time.sleep(3)
        print(f"    公開設定画面へ遷移")

        # 予約投稿ボタンをクリック（予約日時は既に設定済みなのでそのまま）
        final_btn = page.wait_for_selector(
            'button:has-text("予約投稿")',
            timeout=10000,
        )
        final_btn.click()
        time.sleep(5)
        print(f"    予約投稿完了（{new_length}文字, カード{new_cards}個）")
        return True
    except Exception as e:
        print(f"    [エラー] 保存失敗: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="予約投稿のリンクカード修正")
    parser.add_argument("--test", action="store_true", help="最初の1本だけテスト")
    parser.add_argument("--fix-all", action="store_true", help="全予約記事を修正")
    parser.add_argument("--id", type=str, help="特定のnote IDだけ修正")
    args = parser.parse_args()

    if not args.test and not args.fix_all and not args.id:
        parser.print_help()
        return

    notes = _load_scheduled_notes()
    print(f"予約記事: {len(notes)}本")

    if args.id:
        notes = [n for n in notes if n["id"] == args.id]
        if not notes:
            print(f"[エラー] ID {args.id} が見つかりません")
            return
    elif args.test:
        notes = notes[:1]

    # mdファイルとの紐付けを事前確認
    targets = []
    for note in notes:
        md_file = _find_article_file(note["title"])
        if md_file:
            targets.append({"note": note, "md_file": md_file})
            print(f"  {note['id']} | {note['title'][:35]} | {md_file.name[:30]}")
        else:
            print(f"  {note['id']} | {note['title'][:35]} | [ファイルなし - スキップ]")

    if not targets:
        print("\n修正対象がありません。")
        return

    print(f"\n修正対象: {len(targets)}本")

    pw, context, page = _launch_browser(headless=False)
    success = 0
    fail = 0

    try:
        for i, t in enumerate(targets, 1):
            note = t["note"]
            md_file = t["md_file"]
            print(f"\n{'=' * 50}")
            print(f"  [{i}/{len(targets)}] {note['title'][:40]}")
            print(f"  ID: {note['id']}")
            print(f"{'=' * 50}")

            if _fix_one_article(page, note["id"], note["title"], md_file):
                success += 1
            else:
                fail += 1

            time.sleep(2)

        print(f"\n{'=' * 50}")
        print(f"  完了: 成功{success}本, 失敗{fail}本")
        print(f"{'=' * 50}")

        if args.test:
            print("\nテストモード: ブラウザで結果を確認してください。")
            print("確認が終わったらブラウザを閉じてください。")
            try:
                context.pages[0].wait_for_event("close", timeout=0)
            except Exception:
                pass

    finally:
        try:
            context.close()
            pw.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
