"""
投稿管理シートのマイグレーション（v2）

やること:
  1. 投稿管理シートをバックアップタブにコピー
  2. B列に「フォルダ名」列を挿入（既存B以降は1列右にずれる）
  3. A列にあるフォルダ名（YYYYMMDD_HHMMSS形式）をB列にコピー
  4. A列を通番（1, 2, 3...）に戻す
  5. ヘッダー行のB1に「フォルダ名」を記入

実行:
    python migrate_sheet_v2.py              # 実行
    python migrate_sheet_v2.py --dry-run    # 確認だけ（シートを変更しない）
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys

from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).parent / ".env")


def get_sheet_service():
    import sheets
    return sheets.get_service()


def get_sheet_tab_id(svc, spreadsheet_id: str, tab_name: str) -> int | None:
    """シートタブの数値IDを取得する。"""
    meta = svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for s in meta.get("sheets", []):
        if s["properties"]["title"] == tab_name:
            return s["properties"]["sheetId"]
    return None


def main():
    parser = argparse.ArgumentParser(description="投稿管理シート マイグレーション")
    parser.add_argument("--dry-run", action="store_true", help="確認だけ（シートを変更しない）")
    args = parser.parse_args()

    spreadsheet_id = os.getenv("YOUTUBE_SHEET_ID", "")
    if not spreadsheet_id:
        print("[エラー] YOUTUBE_SHEET_ID が未設定です。")
        sys.exit(1)

    svc = get_sheet_service()
    tab_name = "投稿管理"

    # シートタブの数値IDを取得
    sheet_tab_id = get_sheet_tab_id(svc, spreadsheet_id, tab_name)
    if sheet_tab_id is None:
        print(f"[エラー] 「{tab_name}」タブが見つかりません。")
        sys.exit(1)

    print(f"対象: {tab_name}（タブID: {sheet_tab_id}）")

    # ── 1. 現在のA列データを読み込み ──
    result = svc.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{tab_name}!A:A",
    ).execute()
    a_col_values = result.get("values", [])
    print(f"行数: {len(a_col_values)}（ヘッダー含む）")

    # フォルダ名パターン（YYYYMMDD_HHMMSS）
    folder_pattern = re.compile(r"^\d{8}_\d{6}$")
    folder_rows = []  # (行番号, フォルダ名)
    for i, row in enumerate(a_col_values):
        if i == 0:
            continue  # ヘッダーはスキップ
        val = row[0] if row else ""
        if folder_pattern.match(val):
            folder_rows.append((i + 1, val))  # 1-based行番号

    print(f"フォルダ名が入っている行: {len(folder_rows)}")

    if args.dry_run:
        print("\n[dry-run] 以下の変更を行います:")
        print(f"  1. 「{tab_name}_backup」タブにバックアップ")
        print(f"  2. B列に「フォルダ名」列を挿入")
        print(f"  3. A列のフォルダ名（{len(folder_rows)}行）をB列にコピー")
        print(f"  4. A列を通番（1〜{len(a_col_values) - 1}）に戻す")
        if folder_rows:
            print(f"\n  例: 行{folder_rows[0][0]}: A=「{folder_rows[0][1]}」→ B列に移動、A=通番")
        return

    # ── 2. バックアップタブを作成 ──
    print("\n[1/4] バックアップタブ作成...")
    backup_name = f"{tab_name}_backup"
    # 既存バックアップがあれば削除
    backup_id = get_sheet_tab_id(svc, spreadsheet_id, backup_name)
    requests = []
    if backup_id is not None:
        requests.append({"deleteSheet": {"sheetId": backup_id}})

    requests.append({
        "duplicateSheet": {
            "sourceSheetId": sheet_tab_id,
            "newSheetName": backup_name,
        }
    })
    svc.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": requests},
    ).execute()
    print(f"  「{backup_name}」タブを作成しました。")

    # ── 3. B列を挿入 ──
    print("[2/4] B列を挿入...")
    svc.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": [{
            "insertDimension": {
                "range": {
                    "sheetId": sheet_tab_id,
                    "dimension": "COLUMNS",
                    "startIndex": 1,
                    "endIndex": 2,
                },
                "inheritFromBefore": False,
            }
        }]},
    ).execute()
    print("  B列を挿入しました（既存B列以降が1列右にずれました）。")

    # ── 4. ヘッダー + フォルダ名をB列に書き込み ──
    print("[3/4] B列にフォルダ名を書き込み...")
    data = [
        {"range": f"{tab_name}!B1", "values": [["フォルダ名"]]},
    ]
    for row_num, folder_name in folder_rows:
        data.append({
            "range": f"{tab_name}!B{row_num}",
            "values": [[folder_name]],
        })

    svc.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"valueInputOption": "RAW", "data": data},
    ).execute()
    print(f"  B列にフォルダ名を{len(folder_rows)}行書き込みました。")

    # ── 5. A列を通番に戻す ──
    print("[4/4] A列を通番に戻す...")
    total_rows = len(a_col_values) - 1  # ヘッダー除く
    a_data = [{"range": f"{tab_name}!A1", "values": [["No."]]}]
    for i in range(1, total_rows + 1):
        a_data.append({
            "range": f"{tab_name}!A{i + 1}",
            "values": [[i]],
        })

    svc.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"valueInputOption": "RAW", "data": a_data},
    ).execute()
    print(f"  A列を 1〜{total_rows} の通番に更新しました。")

    print(f"\nマイグレーション完了！")
    print(f"  バックアップ: 「{backup_name}」タブ")
    print(f"  新しい列構成: A=No. | B=フォルダ名 | C=種別 | D=トピック | ...")


if __name__ == "__main__":
    main()
