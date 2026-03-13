"""
note_image_replace.py
既存note記事のヘッダー画像を一括差し替えするスクリプト。
note管理シートからNo.とURLを取得し、対応する画像をアップロードする。

使い方:
    python note_image_replace.py --replace         # 全記事
    python note_image_replace.py --replace --no 1   # 1記事だけ
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import time

from dotenv import load_dotenv
from playwright.sync_api import Page

from note_publish import _launch_browser, _close_browser

load_dotenv(pathlib.Path(__file__).parent / ".env")

SCRIPT_DIR = pathlib.Path(__file__).parent
IMAGES_DIR = SCRIPT_DIR / "note_images"


def _get_image_path(no: int) -> pathlib.Path | None:
    path = IMAGES_DIR / f"note_{no:02d}.png"
    return path if path.exists() else None


def _get_articles_from_sheet() -> list[dict]:
    """note管理シートからNo.・タイトル・URLを取得する。

    Returns: [{"no": 1, "title": "...", "url": "https://note.com/.../nXXX", "key": "nXXX"}, ...]
    """
    import sheets

    sheet_id = os.getenv("YOUTUBE_SHEET_ID", "")
    if not sheet_id:
        print("YOUTUBE_SHEET_ID が未設定です。")
        return []

    service = sheets.get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"{sheets.NOTE_SHEET_NAME}!A:I",
    ).execute()

    rows = result.get("values", [])
    articles = []
    for row in rows[1:]:  # ヘッダー行スキップ
        if len(row) < 9:
            continue
        no_str = row[0]
        title = row[5] if len(row) > 5 else ""
        url = row[8] if len(row) > 8 else ""
        if not no_str or not url:
            continue

        # URLから記事キーを抽出（例: https://note.com/gachiho_motive/n/nab06c9c68ffa → nab06c9c68ffa）
        m = re.search(r"/n/(n[a-zA-Z0-9]+)", url)
        if not m:
            continue

        try:
            no = int(no_str)
        except ValueError:
            continue

        articles.append({
            "no": no,
            "title": title,
            "url": url,
            "key": m.group(1),
        })

    return articles


def _replace_one(page: Page, article: dict) -> str:
    """1記事の編集ページを開き、画像を差し替える。

    Returns: "ok", "fail"
    """
    no = article["no"]
    key = article["key"]
    title = article["title"]

    image_path = _get_image_path(no)
    if not image_path:
        print(f"    画像なし: note_{no:02d}.png")
        return "fail"

    edit_url = f"https://editor.note.com/notes/{key}/edit/"
    page.goto(edit_url)
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    print(f"  #{no:2d} {title[:40]}")

    try:
        # Step 1: 既存画像を削除（×ボタン = span[aria-label="削除"]の親button）
        delete_span = page.query_selector('span[aria-label="削除"]')
        if delete_span:
            parent = delete_span.evaluate_handle('el => el.closest("button")')
            parent.as_element().click()
            time.sleep(2)

        # Step 2: 「画像を追加」
        add_btn = page.wait_for_selector(
            'button[aria-label="画像を追加"]', timeout=5000
        )
        add_btn.click()
        time.sleep(1)

        # Step 3: 「画像をアップロード」→ ファイル選択
        with page.expect_file_chooser() as fc_info:
            page.wait_for_selector(
                'button:has-text("画像をアップロード")', timeout=5000
            ).click()
        fc_info.value.set_files(str(image_path))
        time.sleep(3)

        # Step 4: モーダル「保存」
        page.wait_for_selector(
            '.ReactModal__Content button:has-text("保存")', timeout=5000
        ).click()
        time.sleep(5)

        # Step 5: モーダルが完全に閉じるのを待つ → 下書き保存
        page.wait_for_selector('.ReactModal__Overlay', state='hidden', timeout=10000)
        time.sleep(2)
        page.wait_for_selector(
            'button:has-text("下書き保存"), button:has-text("一時保存")',
            timeout=10000,
        ).click()
        time.sleep(3)

        # Step 6: publish画面に遷移
        publish_url = f"https://editor.note.com/notes/{key}/publish/"
        page.goto(publish_url)
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        # Step 7: 投稿ボタンをクリック（note_publish.pyと同じセレクタ）
        publish_btn = page.wait_for_selector(
            'button:has-text("予約投稿"), button:has-text("投稿"), '
            'button:has-text("公開")',
            timeout=10000,
        )
        publish_btn.click()
        time.sleep(5)

        print(f"    OK（{image_path.name}）")
        return "ok"

    except Exception as e:
        # デバッグ用スクリーンショット保存
        ss_path = SCRIPT_DIR / "note_images" / f"debug_{no:02d}.png"
        page.screenshot(path=str(ss_path))
        print(f"    失敗: {e}")
        print(f"    スクリーンショット: {ss_path}")
        print(f"    現在のURL: {page.url}")
        return "fail"


def do_replace(target_no: int | None = None):
    print("note管理シートから記事一覧を取得...")
    articles = _get_articles_from_sheet()
    print(f"  {len(articles)}件の記事を検出\n")

    if not articles:
        print("対象記事がありません。")
        return

    # --no 指定時はフィルタ
    if target_no is not None:
        articles = [a for a in articles if a["no"] == target_no]
        if not articles:
            print(f"  No.{target_no} の記事が見つかりません。")
            return

    pw, context, page = _launch_browser(headless=False)

    try:
        ok = fail = 0

        for i, article in enumerate(articles):
            print(f"[{i+1}/{len(articles)}] {article['key']}")
            result = _replace_one(page, article)
            if result == "ok":
                ok += 1
            else:
                fail += 1

        print(f"\n{'#' * 40}")
        print(f"  完了: 成功={ok} 失敗={fail}")
        print(f"{'#' * 40}")

    finally:
        _close_browser(pw, context, wait_for_user=False)


def main():
    parser = argparse.ArgumentParser(description="note記事ヘッダー画像の差し替え")
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--no", type=int, default=None,
                        help="差し替える画像No.（省略時は全件）")
    args = parser.parse_args()

    if args.replace:
        do_replace(target_no=args.no)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
