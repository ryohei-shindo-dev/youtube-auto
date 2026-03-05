"""
batch_note_gen.py
note管理シートからトピックを読み取り、note記事をバッチ生成する。

使い方:
    python batch_note_gen.py              # 全未生成トピックを生成
    python batch_note_gen.py --count 5    # 5本だけ生成
    python batch_note_gen.py --theme 心理  # テーマ指定で生成
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
import time
import traceback
from datetime import datetime

from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).parent / ".env")

import note_gen
import sheets

SCRIPT_DIR = pathlib.Path(__file__).parent
NOTE_OUTPUT_DIR = SCRIPT_DIR / "note_articles"


def main():
    parser = argparse.ArgumentParser(description="note記事バッチ生成")
    parser.add_argument("--count", type=int, default=50, help="生成本数（デフォルト: 50）")
    parser.add_argument("--theme", type=str, default=None, help="テーマ指定（あるある/歴史データ/心理/メリット/ガチホモチベ/格言）")
    args = parser.parse_args()

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("[エラー] ANTHROPIC_API_KEY が未設定です。")
        sys.exit(1)

    sheet_id = os.getenv("YOUTUBE_SHEET_ID", "")
    if not sheet_id:
        print("[エラー] YOUTUBE_SHEET_ID が未設定です。")
        sys.exit(1)

    NOTE_OUTPUT_DIR.mkdir(exist_ok=True)

    target = args.count
    success = 0
    fail = 0
    results = []

    print(f"\n{'#' * 60}")
    print(f"  note記事バッチ生成")
    print(f"{'#' * 60}")
    print(f"  生成上限: {target}本")
    print(f"  テーマ: {args.theme or '全テーマ'}")
    print(f"  出力先: {NOTE_OUTPUT_DIR}")
    print(f"  開始: {datetime.now().strftime('%Y/%m/%d %H:%M:%S')}")
    print(f"{'#' * 60}")

    for i in range(1, target + 1):
        try:
            # シートから次のトピックを取得
            next_item = sheets.get_next_note_topic(sheet_id, theme=args.theme)
            if not next_item:
                print(f"\n[完了] 未生成トピックがなくなりました（{success}本生成済み）。")
                break

            topic = next_item["topic"]
            theme = next_item["theme"]
            row = next_item["row"]

            print(f"\n{'=' * 60}")
            print(f"  [{i}/{target}] テーマ: {theme}")
            print(f"  トピック: {topic}")
            print(f"{'=' * 60}")

            # ファイル名にテーマと連番を使う
            safe_topic = topic[:20].replace("/", "_").replace(":", "_")
            filename = f"note_{i:02d}_{safe_topic}.md"

            # 記事生成
            result_path = note_gen.generate_note_from_topic(
                topic=topic,
                theme=theme,
                output_dir=NOTE_OUTPUT_DIR,
                filename=filename,
            )

            if not result_path:
                raise RuntimeError("記事生成に失敗")

            # 記事タイトルを抽出（1行目の # を取得）
            article_text = result_path.read_text(encoding="utf-8")
            title = ""
            for line in article_text.split("\n"):
                if line.startswith("# "):
                    title = line[2:].strip()
                    break

            # シート更新
            sheets.update_note_generated(sheet_id, row, title)

            success += 1
            results.append({
                "no": i,
                "status": "OK",
                "theme": theme,
                "title": title,
                "file": str(result_path),
            })
            print(f"\n  OK [{i}] {title}")

        except Exception as e:
            fail += 1
            results.append({
                "no": i,
                "status": "FAIL",
                "error": str(e),
            })
            print(f"\n  FAIL [{i}] {e}")
            traceback.print_exc()

        # API レート制限対策
        if i < target:
            time.sleep(1)

    # ── 結果サマリー ──
    print(f"\n\n{'#' * 60}")
    print(f"  note記事バッチ生成 完了")
    print(f"{'#' * 60}")
    print(f"  成功: {success}本")
    print(f"  失敗: {fail}本")
    print(f"  出力先: {NOTE_OUTPUT_DIR}")
    print(f"  終了: {datetime.now().strftime('%Y/%m/%d %H:%M:%S')}")
    print()

    for r in results:
        if r["status"] == "OK":
            print(f"  {r['no']:3d}. OK  [{r['theme']}] {r['title']}")
        else:
            print(f"  {r['no']:3d}. FAIL {r['error']}")

    print()


if __name__ == "__main__":
    main()
