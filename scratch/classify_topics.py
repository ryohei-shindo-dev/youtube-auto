"""topics.json にlayer・core_problemタグを付与するスクリプト"""
from __future__ import annotations
import json
from pathlib import Path

TOPICS_PATH = Path("data/content/topics.json")

# === 分類基準 ===
# 入口: 初見でも分かる痛みが前面（暴落/含み損/具体的損失額）
# 中核: チャンネル固有の本丸（比較疲れ/目移り/正解不安/動いて崩す）
# 土台: 継続思想・姿勢の補強（退屈/静かな継続/自分の軸/習慣）

# core_problem候補:
#   暴落不安, 含み損, 後悔, 数字・データ, 制度活用,
#   歴史的根拠, 格言・哲学, 損失回避,
#   比較疲れ, 目移り, 正解不安, 乗り換え誘惑,
#   タイミング失敗, 感情売買,
#   継続習慣, 退屈, 複利実感, 自分の軸

# カテゴリごとのデフォルト + 個別オーバーライド
CATEGORY_DEFAULTS = {
    "メリット":       {"layer": "土台",  "core_problem": "数字・データ"},
    "格言":           {"layer": "土台",  "core_problem": "格言・哲学"},
    "あるある":       {"layer": "入口",  "core_problem": "損失回避"},
    "歴史データ":     {"layer": "入口",  "core_problem": "歴史的根拠"},
    "ガチホモチベ":   {"layer": "土台",  "core_problem": "継続習慣"},
    "後悔系":         {"layer": "入口",  "core_problem": "後悔"},
    "具体数字系":     {"layer": "入口",  "core_problem": "数字・データ"},
    "積立疲れ系":     {"layer": "中核",  "core_problem": "退屈"},
    "比較焦り系":     {"layer": "中核",  "core_problem": "比較疲れ"},
    "継続モチベ系":   {"layer": "土台",  "core_problem": "継続習慣"},
    "動いて崩した系": {"layer": "中核",  "core_problem": "タイミング失敗"},
}

# トピック文字列に含むキーワードで個別オーバーライド（カテゴリデフォルトより優先）
# (検索文字列, layer, core_problem)
KEYWORD_OVERRIDES: list[tuple[str, str, str]] = [
    # --- メリット → 一部は入口（具体数字で初見を引く） ---
    ("非課税", "入口", "制度活用"),
    ("NISA", "入口", "制度活用"),
    ("iDeCo", "入口", "制度活用"),
    ("65歳まで", "入口", "数字・データ"),
    ("退職金", "入口", "数字・データ"),
    ("20歳で始めるか30歳", "入口", "数字・データ"),

    # --- あるある → 一部は中核（比較/目移り/正解不安） ---
    ("SNSで見る短期トレーダー", "中核", "比較疲れ"),
    ("友達が仮想通貨で儲けた", "中核", "比較疲れ"),
    ("含み益が出ると利確したくなる", "中核", "目移り"),
    ("年初一括vs積立", "中核", "正解不安"),
    ("右肩上がりのグラフ", "中核", "正解不安"),
    ("積立設定したことを忘れてる", "土台", "継続習慣"),

    # --- 後悔系 → 一部は中核（乗り換え/比較系の後悔） ---
    ("S&P500を売ってビットコイン", "中核", "乗り換え誘惑"),
    ("レバナスに乗り換え", "中核", "乗り換え誘惑"),
    ("含み益が怖くなった", "中核", "損失回避"),
    ("含み益が出るたびに利確", "中核", "目移り"),

    # --- 具体数字系 → 一部は土台（複利実感/安心系） ---
    ("ベスト10日を逃す", "土台", "継続習慣"),
    ("暴落後1年のリターン", "入口", "暴落不安"),
    ("信託報酬", "土台", "数字・データ"),
    ("配当再投資で30年", "土台", "数字・データ"),
    ("4%ルール", "土台", "数字・データ"),
    ("年利7%を信じすぎた", "中核", "正解不安"),
    ("月5万円×30年で6000万円のグラフ", "中核", "正解不安"),

    # --- 積立疲れ系 → 一部は土台（安心・肯定）、入口（痛み前面） ---
    ("元本割れが2倍つらい", "入口", "損失回避"),
    ("5年積み立てて含み損", "入口", "含み損"),
    ("積立NISAを始めて半年、まだマイナス", "入口", "含み損"),
    ("勉強したのにむしろブレた", "中核", "正解不安"),
    ("「何もしない」が一番むずかしい", "中核", "正解不安"),
    ("オルカンが退屈すぎて不安", "中核", "目移り"),
    ("積立2年目の「別のことしたい病」", "中核", "目移り"),

    # --- 比較焦り系 → 一部は入口（初見でも痛みが分かる） ---
    ("30歳で投資を始めるのは遅い", "入口", "数字・データ"),
    ("「もっと早く始めればよかった」", "入口", "後悔"),
    ("利確しないと不安な人へ", "中核", "損失回避"),

    # --- 継続モチベ系 → 一部は中核（比較/退屈系） ---
    ("他人を見ない日", "中核", "比較疲れ"),
    ("投資を100時間調べて疲れた", "中核", "正解不安"),

    # --- 動いて崩した系 → 一部は中核の乗り換え/感情売買 ---
    ("乗り換えたら前のほうが伸びた", "中核", "乗り換え誘惑"),
    ("怖くなって全部外した", "中核", "感情売買"),
    ("ルールより感情で動いてしまった", "中核", "感情売買"),
    ("口座を見すぎて余計な売買", "中核", "感情売買"),

    # --- ガチホモチベ → 一部は入口 ---
    ("インフレ率2%", "入口", "数字・データ"),
]


def classify_topic(category: str, topic_text: str) -> dict:
    """トピックの layer と core_problem を判定"""
    default = CATEGORY_DEFAULTS[category]
    layer = default["layer"]
    core_problem = default["core_problem"]

    # キーワードオーバーライド（後にマッチしたものが優先）
    for keyword, ovr_layer, ovr_cp in KEYWORD_OVERRIDES:
        if keyword in topic_text:
            layer = ovr_layer
            core_problem = ovr_cp

    return {"layer": layer, "core_problem": core_problem}


def main():
    with open(TOPICS_PATH) as f:
        data = json.load(f)

    # Shorts分類
    stats = {"入口": 0, "中核": 0, "土台": 0}
    cp_stats: dict[str, int] = {}

    for category, topics in data["shorts"].items():
        for i, topic in enumerate(topics):
            if isinstance(topic, dict):
                topic_text = topic.get("topic", "")
            else:
                topic_text = str(topic)
                topic = {"topic": topic_text}
                topics[i] = topic

            result = classify_topic(category, topic_text)
            topic["layer"] = result["layer"]
            topic["core_problem"] = result["core_problem"]

            stats[result["layer"]] += 1
            cp_stats[result["core_problem"]] = cp_stats.get(result["core_problem"], 0) + 1

    # Long: layer追加 + shorts_potential欄
    for topic in data["long"]:
        if isinstance(topic, dict):
            topic["layer"] = "土台"  # 長尺はデフォルト土台
            if "shorts_potential" not in topic:
                topic["shorts_potential"] = []

    # 保存
    with open(TOPICS_PATH, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 集計表示
    total = sum(stats.values())
    print(f"\n=== Shorts 3層分類結果 ({total}本) ===")
    for layer, count in stats.items():
        pct = count / total * 100
        print(f"  {layer}: {count}本 ({pct:.1f}%)")

    print(f"\n=== core_problem 分布 ===")
    for cp, count in sorted(cp_stats.items(), key=lambda x: -x[1]):
        print(f"  {cp}: {count}本")

    # カテゴリ×layer クロス集計
    print(f"\n=== カテゴリ × layer クロス集計 ===")
    print(f"{'カテゴリ':<14} {'入口':>4} {'中核':>4} {'土台':>4} {'計':>4}")
    for category, topics in data["shorts"].items():
        cross = {"入口": 0, "中核": 0, "土台": 0}
        for topic in topics:
            cross[topic["layer"]] += 1
        total_cat = sum(cross.values())
        print(f"{category:<14} {cross['入口']:>4} {cross['中核']:>4} {cross['土台']:>4} {total_cat:>4}")


if __name__ == "__main__":
    main()
