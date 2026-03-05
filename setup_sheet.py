"""
setup_sheet.py
投稿管理スプレッドシートを新規作成し、topics.json のデータを初期投入するセットアップスクリプト。

使い方:
    venv/bin/python setup_sheet.py

実行すると:
    1. 「ガチホのモチベ - 投稿管理」という名前のスプレッドシートを作成
    2. topics.json の80件をシートに投入
    3. スプレッドシートIDを .env に保存
"""

import pathlib
import sys

from dotenv import load_dotenv

_DIR = pathlib.Path(__file__).parent
load_dotenv(_DIR / ".env")

import sheets


def main():
    print("投稿管理スプレッドシートをセットアップします。")
    print()

    # スプレッドシートを新規作成
    print("[Step 1] スプレッドシートを作成中...")
    service = sheets.get_service()

    spreadsheet = service.spreadsheets().create(
        body={
            "properties": {"title": "ガチホのモチベ - 投稿管理"},
            "sheets": [{"properties": {"title": sheets.SHEET_NAME}}],
        }
    ).execute()

    spreadsheet_id = spreadsheet["spreadsheetId"]
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
    print(f"  作成完了: {url}")

    # .env にスプレッドシートIDを保存
    print("\n[Step 2] .env にスプレッドシートIDを保存中...")
    env_path = _DIR / ".env"
    env_content = env_path.read_text(encoding="utf-8") if env_path.exists() else ""

    if "YOUTUBE_SHEET_ID" in env_content:
        print("  [注意] YOUTUBE_SHEET_ID は既に .env に存在します。手動で更新してください。")
        print(f"  新しいID: {spreadsheet_id}")
    else:
        with open(env_path, "a", encoding="utf-8") as f:
            f.write(f"\nYOUTUBE_SHEET_ID={spreadsheet_id}\n")
        print(f"  保存完了: YOUTUBE_SHEET_ID={spreadsheet_id}")

    # トピック初期投入
    print("\n[Step 3] topics.json のデータを投入中...")
    sheets.populate_from_topics_json(spreadsheet_id)

    # ヘッダー行を太字＋固定にする
    print("\n[Step 4] ヘッダー行の書式を設定中...")
    _format_header(service, spreadsheet_id)

    print("\n" + "=" * 50)
    print("セットアップ完了！")
    print(f"  スプレッドシート: {url}")
    print(f"  スプレッドシートID: {spreadsheet_id}")
    print("=" * 50)


def _format_header(service, spreadsheet_id: str):
    """ヘッダー行を太字にし、固定する。"""
    # シートIDを取得
    sheet_metadata = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id,
    ).execute()
    sheet_id = sheet_metadata["sheets"][0]["properties"]["sheetId"]

    requests_body = [
        # ヘッダー行を太字にする
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {"bold": True},
                        "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
                    }
                },
                "fields": "userEnteredFormat(textFormat,backgroundColor)",
            }
        },
        # ヘッダー行を固定
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {"frozenRowCount": 1},
                },
                "fields": "gridProperties.frozenRowCount",
            }
        },
        # 列幅を調整
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": 2,  # C列（トピック）
                    "endIndex": 3,
                },
                "properties": {"pixelSize": 400},
                "fields": "pixelSize",
            }
        },
    ]

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": requests_body},
    ).execute()
    print("  ヘッダー書式設定完了")


if __name__ == "__main__":
    main()
