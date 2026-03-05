"""
sheets.py
Google Sheets API で投稿管理シートを読み書きするモジュール。

【シート列構成】
  A: No.（連番）
  B: 種別（Shorts/メリット, Shorts/格言, Shorts/あるある, Shorts/歴史データ, Shorts/ガチホモチベ, 通常）
  C: トピック
  D: 検索キーワード
  E: 狙い
  F: ステータス（未生成 / 生成済み / 公開済み）
  G: タイトル（生成後に記録）
  H: 生成日
  I: 公開日
  J: YouTube URL
  K: 再生数
  L: 備考
"""

import os
import pathlib
from datetime import datetime
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

_DIR = pathlib.Path(__file__).parent
CREDENTIALS_FILE = str(_DIR / "credentials.json")
TOKEN_FILE = str(_DIR / "token.json")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

SHEET_NAME = "投稿管理"

STATUS_PENDING = "未生成"
STATUS_GENERATED = "生成済み"
STATUS_PUBLISHED = "公開済み"

_service_cache = {}


def get_service():
    """Google Sheets API サービスを取得する。"""
    if "sheets" not in _service_cache:
        creds = _get_credentials()
        _service_cache["sheets"] = build("sheets", "v4", credentials=creds)
    return _service_cache["sheets"]


def get_next_topic(
    spreadsheet_id: str,
    theme: str = None,
    video_type: str = "Shorts",
) -> Optional[dict]:
    """
    シートから次の「未生成」トピックを取得する。

    Args:
        spreadsheet_id: スプレッドシートID
        theme: テーマ名（メリット/格言/あるある/歴史データ/ガチホモチベ）。
               指定するとそのテーマのShortsのみ検索。
        video_type: "Shorts" or "通常"

    Returns:
        {"row": 行番号, "type": "種別", "topic": "トピック文字列"}
        未生成がなければ None
    """
    service = get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{SHEET_NAME}!A:F",
    ).execute()

    rows = result.get("values", [])
    if len(rows) <= 1:
        return None

    for i, row in enumerate(rows[1:], start=2):
        if len(row) < 6 or row[5] != STATUS_PENDING:
            continue

        row_type = row[1] if len(row) > 1 else ""

        if video_type == "通常":
            # 通常動画を検索
            if row_type == "通常":
                return {"row": i, "type": row_type, "topic": row[2] if len(row) > 2 else ""}
        else:
            # Shorts を検索（テーマ指定あり/なし）
            if theme:
                target = f"Shorts/{theme}"
                if row_type == target:
                    return {"row": i, "type": row_type, "topic": row[2] if len(row) > 2 else ""}
            else:
                if row_type.startswith("Shorts"):
                    return {"row": i, "type": row_type, "topic": row[2] if len(row) > 2 else ""}

    return None


def update_generated(
    spreadsheet_id: str,
    row: int,
    title: str,
    tags: list,
):
    """動画生成完了後にシートを更新する。"""
    service = get_service()
    today = datetime.now().strftime("%Y/%m/%d")
    tag_str = ", ".join(tags) if tags else ""

    data = [
        {"range": f"{SHEET_NAME}!F{row}", "values": [[STATUS_GENERATED]]},
        {"range": f"{SHEET_NAME}!G{row}", "values": [[title]]},
        {"range": f"{SHEET_NAME}!H{row}", "values": [[today]]},
        {"range": f"{SHEET_NAME}!L{row}", "values": [[tag_str]]},
    ]

    service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"valueInputOption": "RAW", "data": data},
    ).execute()

    print(f"  シート更新完了（行{row}: {STATUS_GENERATED}）")


def update_published(
    spreadsheet_id: str,
    row: int,
    youtube_url: str,
):
    """公開後にシートを更新する。"""
    service = get_service()
    today = datetime.now().strftime("%Y/%m/%d")

    data = [
        {"range": f"{SHEET_NAME}!F{row}", "values": [[STATUS_PUBLISHED]]},
        {"range": f"{SHEET_NAME}!I{row}", "values": [[today]]},
        {"range": f"{SHEET_NAME}!J{row}", "values": [[youtube_url]]},
    ]

    service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"valueInputOption": "RAW", "data": data},
    ).execute()

    print(f"  シート更新完了（行{row}: {STATUS_PUBLISHED}）")


def populate_from_topics_json(spreadsheet_id: str):
    """topics.json の全ネタをシートに初期投入する。"""
    import json

    topics_path = _DIR / "topics.json"
    if not topics_path.exists():
        print("  [エラー] topics.json が見つかりません。")
        return

    with open(topics_path, encoding="utf-8") as f:
        topics_data = json.load(f)

    # 既存データ確認
    service = get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{SHEET_NAME}!A:C",
    ).execute()
    existing_rows = result.get("values", [])
    existing_count = len(existing_rows) - 1 if len(existing_rows) > 1 else 0

    if existing_count > 0:
        print(f"  既に{existing_count}件のデータがあります。追加投入をスキップします。")
        return

    # ヘッダー + データ行を作成
    rows = [["No.", "種別", "トピック", "検索キーワード", "狙い", "ステータス",
             "タイトル", "生成日", "公開日", "YouTube URL", "再生数", "備考"]]

    no = 1
    # Shorts（テーマ別）
    shorts = topics_data.get("shorts", {})
    for theme_name, items in shorts.items():
        for item in items:
            keywords = ", ".join(item.get("search_keywords", []))
            rows.append([no, f"Shorts/{theme_name}", item["topic"], keywords,
                         item.get("intent", ""), STATUS_PENDING,
                         "", "", "", "", "", ""])
            no += 1

    # 通常動画
    for item in topics_data.get("long", []):
        keywords = ", ".join(item.get("search_keywords", []))
        rows.append([no, "通常", item["topic"], keywords,
                     item.get("intent", ""), STATUS_PENDING,
                     "", "", "", "", "", ""])
        no += 1

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{SHEET_NAME}!A1",
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()

    print(f"  {len(rows) - 1}件のトピックをシートに投入しました。")


def _get_credentials():
    """Google 認証情報を取得する。"""
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return creds
