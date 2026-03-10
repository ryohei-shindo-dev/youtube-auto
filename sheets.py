"""
sheets.py
Google Sheets API で投稿管理シートを読み書きするモジュール。

【シート列構成】
  A: No.（通番、人間用。コードでは使わない）
  B: フォルダ名（コードの唯一のキー。done/ディレクトリ名と一致）
  C: 種別
  D: トピック
  E: 検索キーワード
  F: 狙い
  G: ステータス（未生成 / 生成済み / 公開済み / 投稿失敗）
  H: タイトル（生成後に記録）
  I: 生成日
  J: 公開日
  K: YouTube URL
  L: Instagram URL
  M: X URL
  N: TikTok URL
  O: 再生数
  P: 備考
  Q: hook力（レビュー）
  R: 感情曲線（レビュー）
  S: 文脈（レビュー）
  T: 1メッセージ（レビュー）
  U: 総合（レビュー）
  V: コメント（レビュー）
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
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

SHEET_NAME = "投稿管理"

# 投稿管理シートの列インデックス（0始まり）と列レター
COL = {
    "no": 0, "folder": 1, "type": 2, "topic": 3,
    "keyword": 4, "intent": 5, "status": 6, "title": 7,
    "gen_date": 8, "pub_date": 9,
    "youtube_url": 10, "instagram_url": 11, "x_url": 12, "tiktok_url": 13,
    "views": 14, "remarks": 15,
    "hook": 16, "curve": 17, "context": 18, "one_msg": 19, "overall": 20, "comment": 21,
}

# プラットフォーム別のURL列レターマッピング（投稿管理シート）
PLATFORM_COLUMNS = {
    "youtube": "K",
    "instagram": "L",
    "x": "M",
    "tiktok": "N",
}

NOTE_SHEET_NAME = "note管理"

STATUS_PENDING = "未生成"
STATUS_GENERATED = "生成済み"
STATUS_FAILED = "投稿失敗"


def get_cell(row: list, idx: int, default: str = "") -> str:
    """行データから安全にセルを取得する。"""
    return row[idx] if len(row) > idx else default

STATUS_PUBLISHED = "公開済み"

_service_cache = {}


def _get_cached_service(name: str, version: str):
    """Google API サービスをキャッシュ付きで取得する。"""
    if name not in _service_cache:
        creds = _get_credentials()
        _service_cache[name] = build(name, version, credentials=creds)
    return _service_cache[name]


def get_service():
    """Google Sheets API サービスを取得する。"""
    return _get_cached_service("sheets", "v4")


def get_youtube_service():
    """YouTube Data API v3 サービスを取得する。"""
    return _get_cached_service("youtube", "v3")


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
        range=f"{SHEET_NAME}!A:G",
    ).execute()

    rows = result.get("values", [])
    if len(rows) <= 1:
        return None

    for i, row in enumerate(rows[1:], start=2):
        if len(row) < 7 or row[6] != STATUS_PENDING:
            continue

        row_type = row[2] if len(row) > 2 else ""

        if video_type == "通常":
            # 通常動画を検索
            if row_type == "通常":
                return {"row": i, "type": row_type, "topic": row[3] if len(row) > 3 else ""}
        else:
            # Shorts を検索（テーマ指定あり/なし）
            if theme:
                target = f"Shorts/{theme}"
                if row_type == target:
                    return {"row": i, "type": row_type, "topic": row[3] if len(row) > 3 else ""}
            else:
                if row_type.startswith("Shorts"):
                    return {"row": i, "type": row_type, "topic": row[3] if len(row) > 3 else ""}

    return None


def update_generated(
    spreadsheet_id: str,
    row: int,
    title: str,
    tags: list,
    folder: str = "",
):
    """動画生成完了後にシートを更新する。"""
    service = get_service()
    today = datetime.now().strftime("%Y/%m/%d")
    tag_str = ", ".join(tags) if tags else ""

    data = [
        {"range": f"{SHEET_NAME}!G{row}", "values": [[STATUS_GENERATED]]},
        {"range": f"{SHEET_NAME}!H{row}", "values": [[title]]},
        {"range": f"{SHEET_NAME}!I{row}", "values": [[today]]},
        {"range": f"{SHEET_NAME}!P{row}", "values": [[tag_str]]},
    ]
    if folder:
        data.append({"range": f"{SHEET_NAME}!B{row}", "values": [[folder]]})

    service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"valueInputOption": "RAW", "data": data},
    ).execute()

    print(f"  シート更新完了（行{row}: {STATUS_GENERATED}）")


def update_published(
    spreadsheet_id: str,
    row: int,
    urls: dict = None,
    failed_platforms: list = None,
    target_platforms: list = None,
):
    """公開後にシートを更新する。

    プラットフォーム別に時間をずらして投稿する運用に対応。
    - URLは投稿成功のたびに即座に書き込む
    - ステータスは target_platforms 全てのURLが埋まった時だけ「公開済み」にする
    - 全プラットフォーム失敗時は「投稿失敗」にする

    Args:
        urls: 成功したプラットフォームのURL dict
        failed_platforms: 全プラットフォーム失敗時のみ指定（備考に記録）
        target_platforms: 今回の投稿対象プラットフォーム一覧（省略時は従来動作）
    """
    service = get_service()
    today = datetime.now().strftime("%Y/%m/%d")
    all_failed = failed_platforms and not urls

    data = []

    if all_failed:
        data.append({"range": f"{SHEET_NAME}!G{row}", "values": [[STATUS_FAILED]]})
        data.append({"range": f"{SHEET_NAME}!P{row}", "values": [[f"投稿失敗: {', '.join(failed_platforms)}"]]})
    else:
        # URLを書き込む
        for platform, column in PLATFORM_COLUMNS.items():
            url = (urls or {}).get(platform)
            if url:
                data.append({"range": f"{SHEET_NAME}!{column}{row}", "values": [[url]]})

        # 全対象プラットフォームのURLが埋まったかチェック
        if target_platforms:
            # 現在のシート上のURLを読み取り
            existing = _read_platform_urls(spreadsheet_id, row)
            # 今回成功した分をマージ
            merged = {**existing, **(urls or {})}
            all_filled = all(merged.get(p) for p in target_platforms)
        else:
            # target_platforms 未指定なら従来動作（即座に公開済み）
            all_filled = True

        if all_filled:
            data.append({"range": f"{SHEET_NAME}!G{row}", "values": [[STATUS_PUBLISHED]]})
            data.append({"range": f"{SHEET_NAME}!J{row}", "values": [[today]]})

    if data:
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"valueInputOption": "RAW", "data": data},
        ).execute()

    if all_failed:
        print(f"  シート更新完了（行{row}: {STATUS_FAILED}）")
    elif all_filled:
        print(f"  シート更新完了（行{row}: {STATUS_PUBLISHED}）")
    else:
        written = [p for p in (urls or {}) if urls.get(p)]
        print(f"  シート更新完了（行{row}: URL書き込み {', '.join(written)}）")


def _read_platform_urls(spreadsheet_id: str, row: int) -> dict:
    """シートから指定行のプラットフォームURL列を読み取る。"""
    service = get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{SHEET_NAME}!K{row}:N{row}",
    ).execute()
    values = result.get("values", [[]])[0]
    cols = ["youtube", "instagram", "x", "tiktok"]
    return {cols[i]: (values[i] if i < len(values) else "") for i in range(4)}


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
        range=f"{SHEET_NAME}!A:D",
    ).execute()
    existing_rows = result.get("values", [])
    existing_count = len(existing_rows) - 1 if len(existing_rows) > 1 else 0

    if existing_count > 0:
        print(f"  既に{existing_count}件のデータがあります。追加投入をスキップします。")
        return

    # ヘッダー + データ行を作成
    rows = [["No.", "フォルダ名", "種別", "トピック", "検索キーワード", "狙い",
             "ステータス", "タイトル", "生成日", "公開日", "YouTube URL",
             "Instagram URL", "X URL", "TikTok URL",
             "再生数", "備考",
             "hook力", "感情曲線", "文脈", "1メッセージ", "総合", "コメント"]]

    no = 1
    # Shorts（テーマ別）
    shorts = topics_data.get("shorts", {})
    for theme_name, items in shorts.items():
        for item in items:
            keywords = ", ".join(item.get("search_keywords", []))
            rows.append([no, "", f"Shorts/{theme_name}", item["topic"], keywords,
                         item.get("intent", ""), STATUS_PENDING,
                         "", "", "", "", "", "", ""])
            no += 1

    # 通常動画
    for item in topics_data.get("long", []):
        keywords = ", ".join(item.get("search_keywords", []))
        rows.append([no, "", "通常", item["topic"], keywords,
                     item.get("intent", ""), STATUS_PENDING,
                     "", "", "", "", "", "", ""])
        no += 1

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{SHEET_NAME}!A1",
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()

    print(f"  {len(rows) - 1}件のトピックをシートに投入しました。")


# ── note管理シート ──
# 列構成:
#   A: No.  B: テーマ  C: トピック  D: 元Shorts  E: ステータス
#   F: タイトル  G: 生成日  H: 公開日  I: note URL  J: 備考

NOTE_HEADER = [
    "No.", "テーマ", "トピック", "元Shorts", "ステータス",
    "タイトル", "生成日", "公開日", "note URL", "備考",
]


def get_next_note_topic(spreadsheet_id: str, theme: str = None) -> Optional[dict]:
    """note管理シートから次の「未生成」トピックを取得する。"""
    service = get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{NOTE_SHEET_NAME}!A:E",
    ).execute()

    rows = result.get("values", [])
    if len(rows) <= 1:
        return None

    for i, row in enumerate(rows[1:], start=2):
        if len(row) < 5 or row[4] != STATUS_PENDING:
            continue
        row_theme = row[1] if len(row) > 1 else ""
        if theme and row_theme != theme:
            continue
        return {
            "row": i,
            "theme": row_theme,
            "topic": row[2] if len(row) > 2 else "",
            "source_shorts": row[3] if len(row) > 3 else "",
        }

    return None


def update_note_generated(spreadsheet_id: str, row: int, title: str):
    """note記事生成完了後にシートを更新する。"""
    service = get_service()
    today = datetime.now().strftime("%Y/%m/%d")

    data = [
        {"range": f"{NOTE_SHEET_NAME}!E{row}", "values": [[STATUS_GENERATED]]},
        {"range": f"{NOTE_SHEET_NAME}!F{row}", "values": [[title]]},
        {"range": f"{NOTE_SHEET_NAME}!G{row}", "values": [[today]]},
    ]

    service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"valueInputOption": "RAW", "data": data},
    ).execute()

    print(f"  note管理シート更新完了（行{row}: {STATUS_GENERATED}）")


def update_note_published(spreadsheet_id: str, row: int, note_url: str):
    """note記事公開後にシートを更新する。"""
    service = get_service()
    today = datetime.now().strftime("%Y/%m/%d")

    data = [
        {"range": f"{NOTE_SHEET_NAME}!E{row}", "values": [[STATUS_PUBLISHED]]},
        {"range": f"{NOTE_SHEET_NAME}!H{row}", "values": [[today]]},
        {"range": f"{NOTE_SHEET_NAME}!I{row}", "values": [[note_url]]},
    ]

    service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"valueInputOption": "RAW", "data": data},
    ).execute()

    print(f"  note管理シート更新完了（行{row}: {STATUS_PUBLISHED}）")


def populate_note_topics(spreadsheet_id: str):
    """note管理シートにテーマを初期投入する。"""
    service = get_service()

    # 既存データ確認
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"{NOTE_SHEET_NAME}!A:A",
        ).execute()
        existing = result.get("values", [])
        if len(existing) > 1:
            print(f"  既に{len(existing) - 1}件のデータがあります。追加投入をスキップします。")
            return
    except Exception:
        # シートが存在しない場合は新規作成
        _create_note_sheet(spreadsheet_id)

    # テーマデータ
    topics = [
        # ChatGPTレビュー推奨5テーマ
        {"theme": "あるある", "topic": "含み損で眠れない夜にやることは、売買じゃなく確認回数を減らす",
         "source": "含み損系Shorts"},
        {"theme": "あるある", "topic": "積立3年目がしんどい理由：数字より期待のズレがしんどい",
         "source": "積立3年目系Shorts"},
        {"theme": "歴史データ", "topic": "暴落のニュースで口座を開きたくなる時、思い出したい1つの数字",
         "source": "暴落系Shorts"},
        {"theme": "心理", "topic": "SNSの爆益を見て焦る夜：比較をやめるための見方",
         "source": "SNS焦り系Shorts"},
        {"theme": "心理", "topic": "利確したくなる気持ちと、複利が止まる感覚を同時に扱う",
         "source": "利確/複利系Shorts"},
        # 派生テーマ（痛み×安心の型）
        {"theme": "あるある", "topic": "毎日口座を見てしまう人へ：確認頻度と不安の関係",
         "source": "口座確認系Shorts"},
        {"theme": "あるある", "topic": "積立をやめたくなる瞬間と、やめた人が後悔する理由",
         "source": "積立やめる系Shorts"},
        {"theme": "歴史データ", "topic": "暴落後1年のリターンが示す、売らなかった人の結果",
         "source": "暴落後リターン系Shorts"},
        {"theme": "歴史データ", "topic": "20年投資を続けた場合の元本割れ確率がゼロに近い理由",
         "source": "長期投資データ系Shorts"},
        {"theme": "心理", "topic": "投資を始めて最初の暴落で何を感じるか：初心者の心理と対処",
         "source": "初暴落系Shorts"},
        {"theme": "メリット", "topic": "ドルコスト平均法が心を守る仕組み：安く買える時期の意味",
         "source": "ドルコスト系Shorts"},
        {"theme": "メリット", "topic": "配当再投資と複利の静かな力：10年後に気づくこと",
         "source": "複利/配当系Shorts"},
        {"theme": "ガチホモチベ", "topic": "長期投資で退場しない人の共通点：特別なことはしていない",
         "source": "退場しない系Shorts"},
        {"theme": "ガチホモチベ", "topic": "投資を続けるコツは、投資のことを考えすぎないこと",
         "source": "ガチホ系Shorts"},
        {"theme": "格言", "topic": "バフェットが言った「退潮時」の意味を、含み損の夜に読む",
         "source": "格言/バフェット系Shorts"},
    ]

    rows = [NOTE_HEADER]
    for no, t in enumerate(topics, start=1):
        rows.append([
            no, t["theme"], t["topic"], t["source"], STATUS_PENDING,
            "", "", "", "", "",
        ])

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{NOTE_SHEET_NAME}!A1",
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()

    print(f"  note管理シートに{len(topics)}件のテーマを投入しました。")


def _create_note_sheet(spreadsheet_id: str):
    """note管理シートタブを新規作成する。"""
    service = get_service()
    body = {
        "requests": [{
            "addSheet": {
                "properties": {"title": NOTE_SHEET_NAME},
            },
        }],
    }
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body=body,
    ).execute()
    print(f"  「{NOTE_SHEET_NAME}」シートを作成しました。")


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
