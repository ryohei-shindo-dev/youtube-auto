"""既存公開済み動画のプラットフォームIDをURL列から抽出してY/Z/AA列にバックフィルする。

使い方:
  python migrate_backfill_platform_ids.py --dry-run   # 確認のみ
  python migrate_backfill_platform_ids.py              # 実際に書き込み
"""
from __future__ import annotations

import argparse
import os
import re
import sys

import sheets


def _extract_x_post_id(url: str) -> str:
    """X URL から post ID を抽出する。"""
    m = re.search(r"/status/(\d+)", url)
    return m.group(1) if m else ""


def _extract_tiktok_publish_id(url: str) -> str:
    """TikTok URL/記録 から publish_id を抽出する。"""
    # tiktok:publish_id=xxx 形式
    m = re.search(r"publish_id=([a-zA-Z0-9_-]+)", url)
    if m:
        return m.group(1)
    # 通常URL: /video/NNNN
    m = re.search(r"/video/(\d+)", url)
    return m.group(1) if m else ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="確認のみ（書き込みしない）")
    args = parser.parse_args()

    sheet_id = os.getenv("YOUTUBE_SHEET_ID", "")
    if not sheet_id:
        print("YOUTUBE_SHEET_ID が設定されていません。")
        sys.exit(1)

    service = sheets.get_service()

    # 全行読み取り
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"{sheets.SHEET_NAME}!A:AC",
    ).execute()
    rows = result.get("values", [])

    if len(rows) <= 1:
        print("データがありません。")
        return

    C = sheets.COL
    updates = []

    for i, row in enumerate(rows[1:], start=2):
        x_url = sheets.get_cell(row, C["x_url"])
        tiktok_url = sheets.get_cell(row, C["tiktok_url"])
        existing_x_id = sheets.get_cell(row, C["x_post_id"])
        existing_tiktok_id = sheets.get_cell(row, C["tiktok_post_id"])

        # X post ID
        if x_url and not existing_x_id:
            x_id = _extract_x_post_id(x_url)
            if x_id:
                updates.append({
                    "row": i,
                    "platform": "x",
                    "id": x_id,
                    "col": sheets.COL_LETTER["x_post_id"],
                    "url": x_url[:50],
                })

        # TikTok post ID
        if tiktok_url and not existing_tiktok_id:
            tt_id = _extract_tiktok_publish_id(tiktok_url)
            if tt_id:
                updates.append({
                    "row": i,
                    "platform": "tiktok",
                    "id": tt_id,
                    "col": sheets.COL_LETTER["tiktok_post_id"],
                    "url": tiktok_url[:50],
                })

    # Instagram: permalink からは media_id を抽出できないためスキップ
    # （permalink は /p/XXXXX 形式で media_id とは別物）

    print(f"バックフィル対象: {len(updates)}件")
    x_count = sum(1 for u in updates if u["platform"] == "x")
    tt_count = sum(1 for u in updates if u["platform"] == "tiktok")
    print(f"  X post ID: {x_count}件")
    print(f"  TikTok post ID: {tt_count}件")
    print(f"  Instagram media ID: スキップ（permalink から抽出不可）")

    for u in updates[:10]:
        print(f"  行{u['row']} [{u['platform']}] {u['id']} ← {u['url']}")
    if len(updates) > 10:
        print(f"  ... 他 {len(updates) - 10}件")

    if args.dry_run:
        print("\n[dry-run] 書き込みは行いません。")
        return

    if not updates:
        print("\nバックフィル対象がありません。")
        return

    data = []
    for u in updates:
        data.append({
            "range": f"{sheets.SHEET_NAME}!{u['col']}{u['row']}",
            "values": [[u["id"]]],
        })

    print(f"\n{len(data)}セルを書き込み中...")
    BATCH_SIZE = 200
    for start in range(0, len(data), BATCH_SIZE):
        batch = data[start:start + BATCH_SIZE]
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=sheet_id,
            body={"valueInputOption": "RAW", "data": batch},
        ).execute()

    print(f"完了: X {x_count}件 / TikTok {tt_count}件をバックフィル")


if __name__ == "__main__":
    main()
