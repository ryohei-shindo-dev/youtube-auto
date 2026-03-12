"""生成失敗トピックの確認＆リセット用スクリプト

投稿管理シートから「生成失敗」ステータスの行を一覧表示し、
必要に応じて「未生成」に戻す。

使い方:
    python check_failed.py
"""

from __future__ import annotations

import os
import pathlib

from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).parent / ".env")

import sheets

sheet_id = os.getenv("YOUTUBE_SHEET_ID")
svc = sheets.get_service()
result = svc.spreadsheets().values().get(
    spreadsheetId=sheet_id, range=f"{sheets.SHEET_NAME}!A:H"
).execute()
rows = result.get("values", [])
C = sheets.COL

failed = []  # (sheet_row_number, type, topic)
for i, row in enumerate(rows[1:], start=2):  # シートの行番号は2始まり（ヘッダー=1）
    status = sheets.get_cell(row, C["status"])
    if status == sheets.STATUS_GEN_FAILED:
        topic = sheets.get_cell(row, C["topic"])
        row_type = sheets.get_cell(row, C["type"])
        failed.append((i, row_type, topic))

if not failed:
    print("「生成失敗」のトピックはありません。")
    raise SystemExit(0)

print(f"=== 生成失敗トピック一覧 ({len(failed)}件) ===\n")
for sheet_row, row_type, topic in failed:
    print(f"  行{sheet_row:3d}: [{row_type}] {topic}")

print(f"\n合計: {len(failed)}件")
answer = input("\nこれらを「未生成」に戻しますか？ (y/n): ").strip().lower()
if answer != "y":
    print("キャンセルしました。")
    raise SystemExit(0)

# バッチ更新で一括リセット
data = []
for sheet_row, _, _ in failed:
    data.append({
        "range": f"{sheets.SHEET_NAME}!G{sheet_row}",
        "values": [[sheets.STATUS_PENDING]],
    })

svc.spreadsheets().values().batchUpdate(
    spreadsheetId=sheet_id,
    body={"valueInputOption": "RAW", "data": data},
).execute()

print(f"\n{len(failed)}件を「{sheets.STATUS_PENDING}」に更新しました。")
