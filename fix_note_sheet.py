"""シートに登録済みだがタイトルが空の記事を、編集ページから正しいタイトルを取得して更新する。
その後、タイトル変更対象があれば変更する。
"""
from __future__ import annotations

import os
import time

from dotenv import load_dotenv
load_dotenv()

import sheets
from note_image_replace import _get_articles_from_sheet
from note_publish import _launch_browser, _close_browser


# ── タイトル変更対象: {現タイトル(完全一致): 新タイトル} ──
TITLE_CHANGES: dict[str, str] = {
    "オルカンでいいのか揺れる夜に、思い出したいこと": "オルカンでいいのか迷ったら、最初の理由を一行書く",
    "NASDAQ100が目につく夜、実は揺れているのは心": "NASDAQ100が気になるとき、揺れているのは数字より心",
    "「他の投資の方が伸びてる」という夜の不安が、実は当たり前の理由": "他の投資が伸びて見えるのは、仕組みの問題",
    "取り崩しまで20年あるのに、夜眠れなくなるのはなぜ": "取り崩しまで20年あるのに不安になる理由",
    "「自分だけ遅い」と感じる夜に、比較を少し静かにする考え方": "「自分だけ遅い」と感じたら、比較を静かにする",
}


def _get_title_from_edit_page(page, key: str) -> str:
    """記事の編集ページからタイトルを取得する。"""
    edit_url = f"https://editor.note.com/notes/{key}/edit/"
    page.goto(edit_url)
    page.wait_for_load_state("networkidle")
    time.sleep(2)

    try:
        title_el = page.wait_for_selector(
            'textarea[placeholder="記事タイトル"]', timeout=10000
        )
        return title_el.evaluate("el => el.value").strip()
    except Exception:
        return ""


def _update_title_on_note(page, key: str, new_title: str) -> str:
    """記事のタイトルを変更して下書き保存する。"""
    edit_url = f"https://editor.note.com/notes/{key}/edit/"
    page.goto(edit_url)
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    try:
        title_el = page.wait_for_selector(
            'textarea[placeholder="記事タイトル"]', timeout=10000
        )
        current = title_el.evaluate("el => el.value")
        print(f"    旧: {current[:55]}")
        print(f"    新: {new_title[:55]}")

        if current == new_title:
            print(f"    → スキップ（変更不要）")
            return "skip"

        title_el.click()
        title_el.evaluate("el => el.select()")
        time.sleep(0.5)
        page.keyboard.press("Backspace")
        time.sleep(0.5)
        title_el.fill(new_title)
        time.sleep(1)

        save_btn = page.wait_for_selector(
            'button:has-text("下書き保存"), button:has-text("一時保存")',
            timeout=10000,
        )
        save_btn.click()
        time.sleep(3)

        print(f"    → OK（下書き保存）")
        return "ok"
    except Exception as e:
        print(f"    → FAIL: {e}")
        return "fail"


def main():
    pw, context, page = _launch_browser(headless=False)

    # ── Step 1: タイトルが空の記事を特定し、編集ページからタイトルを取得 ──
    print("=== Step 1: シートのタイトル空欄を修復 ===")
    all_articles = _get_articles_from_sheet()
    empty_title_articles = [a for a in all_articles if not a["title"].strip()]

    print(f"  シート登録: {len(all_articles)}件、タイトル空: {len(empty_title_articles)}件")

    if empty_title_articles:
        sheet_id = os.getenv("YOUTUBE_SHEET_ID", "")
        service = sheets.get_service()
        updates = []

        for a in empty_title_articles:
            title = _get_title_from_edit_page(page, a["key"])
            if title:
                print(f"  #{a['no']:2d} {a['key']} → {title[:50]}")
                # シートのF列（タイトル）を更新。行番号 = No + 1（ヘッダー分）
                row = a["no"] + 1
                updates.append({
                    "range": f"{sheets.NOTE_SHEET_NAME}!F{row}",
                    "values": [[title]],
                })
                a["title"] = title  # メモリ上も更新
            else:
                print(f"  #{a['no']:2d} {a['key']} → タイトル取得失敗")

        if updates:
            service.spreadsheets().values().batchUpdate(
                spreadsheetId=sheet_id,
                body={"valueInputOption": "RAW", "data": updates},
            ).execute()
            print(f"\n  → {len(updates)}件のタイトルをシートに反映\n")

    # ── Step 2: タイトル変更 ──
    print("=== Step 2: タイトル変更 ===")
    targets = []
    for a in all_articles:
        if a["title"] in TITLE_CHANGES:
            targets.append((a["key"], a["title"], TITLE_CHANGES[a["title"]]))

    if not targets:
        print("  変更対象はありません。")
    else:
        print(f"  変更対象: {len(targets)}件\n")
        ok = fail = skip = 0
        for key, old_title, new_title in targets:
            print(f"  {key}:")
            result = _update_title_on_note(page, key, new_title)
            if result == "ok":
                ok += 1
            elif result == "skip":
                skip += 1
            else:
                fail += 1

        # 変更後のタイトルもシートに反映
        if ok > 0:
            sheet_id = os.getenv("YOUTUBE_SHEET_ID", "")
            service = sheets.get_service()
            title_updates = []
            for a in all_articles:
                if a["title"] in TITLE_CHANGES:
                    row = a["no"] + 1
                    title_updates.append({
                        "range": f"{sheets.NOTE_SHEET_NAME}!F{row}",
                        "values": [[TITLE_CHANGES[a["title"]]]],
                    })
            if title_updates:
                service.spreadsheets().values().batchUpdate(
                    spreadsheetId=sheet_id,
                    body={"valueInputOption": "RAW", "data": title_updates},
                ).execute()

        print(f"\n  完了: OK={ok}, SKIP={skip}, FAIL={fail}")

    print("\n=== 全工程完了 ===")
    _close_browser(pw, context)


if __name__ == "__main__":
    main()
