"""
test_haiku_quality.py — Sonnet vs Haiku の台本品質比較テスト

同じトピック5つに対して両モデルで台本を生成し、
candidate_ranker でスコアリングして品質差を確認する。

使い方:
    python test_haiku_quality.py
"""

from __future__ import annotations

import os
import pathlib
import sys

from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).parent / ".env")

import candidate_ranker
import script_gen

# テスト用トピック（異なるテーマから5つ選択）
TEST_TOPICS = [
    ("SNSで他人の爆益報告を見て焦る夜", "あるある"),
    ("S&P500は過去30年で10倍以上に成長した", "歴史データ"),
    ("含み損が続いて眠れない", "ガチホモチベ"),
    ("バフェットの資産の99%は50歳以降にできた", "格言"),
    ("月3万円の積立でも30年後には大きな差になる", "メリット"),
]

MODELS = [
    ("claude-sonnet-4-6", "Sonnet"),
    ("claude-haiku-4-5-20251001", "Haiku"),
]


def main():
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("[エラー] ANTHROPIC_API_KEY が未設定です。")
        sys.exit(1)

    results = {}  # model_name -> [(topic, score, details)]

    for model_id, model_name in MODELS:
        print(f"\n{'#'*60}")
        print(f"  モデル: {model_name} ({model_id})")
        print(f"{'#'*60}")

        # 環境変数でモデルを切り替え
        script_gen.SCRIPT_MODEL = model_id
        results[model_name] = []

        for topic, theme in TEST_TOPICS:
            print(f"\n  --- トピック: {topic} ({theme}) ---")
            try:
                script_data = script_gen.generate_shorts_script(topic, theme=theme)
                if not script_data:
                    print("  [失敗] 台本生成に失敗")
                    results[model_name].append((topic, 0, "生成失敗"))
                    continue

                score = candidate_ranker.score_script(script_data)
                print(candidate_ranker.format_report(score))
                results[model_name].append((
                    topic,
                    score["total_score"],
                    f"{score['total_score']}/{score['max_score']} "
                    f"タイトル:{script_data.get('title', '不明')}",
                ))
            except Exception as e:
                print(f"  [エラー] {e}")
                results[model_name].append((topic, 0, f"エラー: {e}"))

    # 比較サマリー
    print(f"\n\n{'='*60}")
    print(f"  品質比較サマリー")
    print(f"{'='*60}")

    for model_name in ["Sonnet", "Haiku"]:
        scores = [r[1] for r in results[model_name]]
        avg = sum(scores) / len(scores) if scores else 0
        print(f"\n  [{model_name}] 平均スコア: {avg:.1f}")
        for topic, score, detail in results[model_name]:
            print(f"    {score:2d}点  {detail}")

    # 差分
    sonnet_scores = [r[1] for r in results["Sonnet"]]
    haiku_scores = [r[1] for r in results["Haiku"]]
    sonnet_avg = sum(sonnet_scores) / len(sonnet_scores) if sonnet_scores else 0
    haiku_avg = sum(haiku_scores) / len(haiku_scores) if haiku_scores else 0
    diff = sonnet_avg - haiku_avg

    print(f"\n  差分: Sonnet {sonnet_avg:.1f} vs Haiku {haiku_avg:.1f} (差: {diff:+.1f})")
    if diff <= 1.0:
        print("  → Haikuへの切替を推奨（品質差が小さい）")
    elif diff <= 2.0:
        print("  → Haikuへの切替は要検討（やや品質差あり）")
    else:
        print("  → Sonnet継続を推奨（品質差が大きい）")

    # モデルを元に戻す
    script_gen.SCRIPT_MODEL = "claude-sonnet-4-6"


if __name__ == "__main__":
    main()
