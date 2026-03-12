"""新テーマのトピックをシートに追加するスクリプト

テーマごとの追加本数を指定可能。未使用トピック優先で必要本数だけ追加。

使い方:
    python add_new_topics.py                    # 全テーマの未使用トピックを全追加
    python add_new_topics.py --allocation       # 80本配分に合わせた追加
    python add_new_topics.py --dry-run          # 実際には追加せず確認のみ
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib

from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).parent / ".env")

import sheets

# 全テーマ（旧5 + 新5）
ALL_THEMES = [
    "メリット", "格言", "あるある", "歴史データ", "ガチホモチベ",
    "後悔系", "具体数字系", "積立疲れ系", "比較焦り系", "継続モチベ系",
]

# 80本バッチ配分（ChatGPT推奨）
BATCH_80_ALLOCATION = {
    "後悔系": 16,
    "具体数字系": 16,
    "積立疲れ系": 14,
    "比較焦り系": 10,
    "継続モチベ系": 10,
    "歴史データ": 6,
    "メリット": 4,
    "格言": 2,
    "ガチホモチベ": 2,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="新テーマのトピックをシートに追加")
    parser.add_argument("--allocation", action="store_true",
                        help="80本配分に合わせて必要本数だけ追加")
    parser.add_argument("--dry-run", action="store_true",
                        help="実際には追加せず確認のみ")
    args = parser.parse_args()

    sheet_id = os.getenv("YOUTUBE_SHEET_ID")
    svc = sheets.get_service()

    # 既存データの行数を取得
    result = svc.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"{sheets.SHEET_NAME}!A:G",
    ).execute()
    existing_rows = result.get("values", [])
    next_no = len(existing_rows)  # ヘッダー含むので、次のNoは行数そのまま

    # 既存トピックを集めて重複チェック
    existing_topics = set()
    # テーマごとの未使用（未生成）トピック数をカウント
    theme_pending_count: dict[str, int] = {}
    for row in existing_rows[1:]:
        if len(row) > 3:
            existing_topics.add(row[3].strip())
        # 種別列(C)からテーマを抽出、ステータス列(G)で未生成を判定
        kind = sheets.get_cell(row, sheets.COL["type"]) if len(row) > 2 else ""
        status = sheets.get_cell(row, sheets.COL["status"]) if len(row) > 6 else ""
        if kind.startswith("Shorts/"):
            theme = kind.replace("Shorts/", "")
            if status == sheets.STATUS_PENDING:
                theme_pending_count[theme] = theme_pending_count.get(theme, 0) + 1

    # topics.json を読み込み
    topics_path = pathlib.Path(__file__).parent / "topics.json"
    with open(topics_path, encoding="utf-8") as f:
        topics_data = json.load(f)

    # テーマリストと追加上限を決定
    if args.allocation:
        themes_to_add = BATCH_80_ALLOCATION
        print("80本配分モードで追加します。")
    else:
        # 全テーマの未使用トピックを全追加
        themes_to_add = {t: 999 for t in ALL_THEMES}
        print("全テーマの未使用トピックを追加します。")

    # テーマごとに必要本数を計算して追加
    new_rows = []
    for theme_name, target_count in themes_to_add.items():
        items = topics_data.get("shorts", {}).get(theme_name, [])
        if not items:
            continue

        # 既にシートにある未使用トピック数
        already_pending = theme_pending_count.get(theme_name, 0)

        if args.allocation:
            # 配分モード: 目標数 - 既存未使用数 = 追加必要数
            need = max(0, target_count - already_pending)
            if need == 0:
                print(f"  {theme_name}: 既に{already_pending}本あり（目標{target_count}）→ 追加不要")
                continue
            print(f"  {theme_name}: 目標{target_count} - 既存{already_pending} = {need}本追加")
        else:
            need = 999  # 全追加

        added = 0
        for item in items:
            if added >= need:
                break
            topic = item["topic"]
            if topic.strip() in existing_topics:
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
            added += 1

    if not new_rows:
        print("\n追加するトピックがありません。")
        return

    # テーマ別集計を表示
    print(f"\n追加予定: {len(new_rows)}件")
    theme_summary: dict[str, int] = {}
    for r in new_rows:
        t = r[2].replace("Shorts/", "")
        theme_summary[t] = theme_summary.get(t, 0) + 1
    for t, c in theme_summary.items():
        print(f"  Shorts/{t}: {c}本")

    if args.dry_run:
        print("\n[dry-run] シートへの書き込みをスキップしました。")
        return

    # シートに追記
    start_row = len(existing_rows) + 1
    svc.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"{sheets.SHEET_NAME}!A{start_row}",
        valueInputOption="RAW",
        body={"values": new_rows},
    ).execute()
    print(f"\n{len(new_rows)}件の新トピックをシートに追加しました。")


if __name__ == "__main__":
    main()
