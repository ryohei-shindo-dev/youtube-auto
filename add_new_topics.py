"""新テーマのトピックをシートに追加するスクリプト（一時使用）"""
from __future__ import annotations

import json
import os
import pathlib

from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).parent / ".env")

import sheets

NEW_THEMES = ["後悔系", "具体数字系", "積立疲れ系", "比較焦り系", "継続モチベ系"]

sheet_id = os.getenv("YOUTUBE_SHEET_ID")
svc = sheets.get_service()

# 既存データの行数を取得
result = svc.spreadsheets().values().get(
    spreadsheetId=sheet_id,
    range=f"{sheets.SHEET_NAME}!A:D",
).execute()
existing_rows = result.get("values", [])
next_no = len(existing_rows)  # ヘッダー含むので、次のNoは行数そのまま

# 既存トピックを集めて重複チェック
existing_topics = set()
for row in existing_rows[1:]:
    if len(row) > 3:
        existing_topics.add(row[3].strip())

# topics.json を読み込み
topics_path = pathlib.Path(__file__).parent / "topics.json"
with open(topics_path, encoding="utf-8") as f:
    topics_data = json.load(f)

# 新テーマのトピックだけを抽出
new_rows = []
for theme_name in NEW_THEMES:
    items = topics_data.get("shorts", {}).get(theme_name, [])
    for item in items:
        topic = item["topic"]
        if topic.strip() in existing_topics:
            print(f"  [スキップ] 既存: {topic[:50]}")
            continue
        keywords = ", ".join(item.get("search_keywords", []))
        new_rows.append([
            next_no,
            "",                         # B: フォルダ名
            f"Shorts/{theme_name}",     # C: 種別
            topic,                      # D: トピック
            keywords,                   # E: 検索キーワード
            item.get("intent", ""),     # F: 狙い
            sheets.STATUS_PENDING,      # G: ステータス
        ])
        next_no += 1

if not new_rows:
    print("追加するトピックがありません。")
else:
    # シートに追記
    start_row = len(existing_rows) + 1
    svc.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"{sheets.SHEET_NAME}!A{start_row}",
        valueInputOption="RAW",
        body={"values": new_rows},
    ).execute()
    print(f"\n{len(new_rows)}件の新トピックをシートに追加しました。")
    for theme in NEW_THEMES:
        count = sum(1 for r in new_rows if r[2] == f"Shorts/{theme}")
        if count:
            print(f"  Shorts/{theme}: {count}本")
