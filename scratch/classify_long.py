"""長尺20本にlayer + shorts_potential（Shorts切り出し可能な論点）を付与"""
from __future__ import annotations
import json
from pathlib import Path

TOPICS_PATH = Path("data/content/topics.json")

# 長尺20本の分類とShorts切り出し候補
# topic → (layer, core_problem, shorts_potential)
LONG_CLASSIFICATION = {
    "S&P500の200年史：暴落と回復の全記録": {
        "layer": "入口",
        "core_problem": "歴史的根拠",
        "shorts_potential": [
            "各暴落の回復期間比較（最短/最長）",
            "200年で最悪の10年間でも積立なら黒字",
            "暴落の頻度：平均18ヶ月ごとに来る事実",
        ],
    },
    "複利の魔法：なぜ時間が最大の武器になるのか": {
        "layer": "土台",
        "core_problem": "複利実感",
        "shorts_potential": [
            "複利が実感できるまで10年かかる理由",
            "72の法則で倍になる年数を計算",
        ],
    },
    "ウォーレン・バフェットに学ぶ長期投資の哲学": {
        "layer": "土台",
        "core_problem": "格言・哲学",
        "shorts_potential": [
            "バフェットの資産の99%は50歳以降に増えた",
            "バフェット遺言「妻にはS&P500を買え」",
        ],
    },
    "暴落の歴史：世界恐慌からコロナまで全回復データ": {
        "layer": "入口",
        "core_problem": "歴史的根拠",
        "shorts_potential": [
            "世界恐慌→25年で10倍",
            "コロナ→1年半で最高値更新",
            "暴落後1年のリターンは平均+25%",
        ],
    },
    "インデックス投資の生みの親ジョン・ボーグルの教え": {
        "layer": "土台",
        "core_problem": "格言・哲学",
        "shorts_potential": [
            "ボーグル「コストは確実にリターンを蝕む」",
            "信託報酬0.1%と1%の30年差=800万円",
        ],
    },
    "新NISAで長期投資を始める人へ：知っておくべき事実5つ": {
        "layer": "入口",
        "core_problem": "制度活用",
        "shorts_potential": [
            "NISA枠1800万円の非課税効果は約400万円",
            "NISA解約した人が再投資できない事実",
        ],
    },
    "なぜ積立投資は「退屈」なほど正しいのか": {
        "layer": "中核",
        "core_problem": "退屈",
        "shorts_potential": [
            "退屈な投資をしている人はたぶん正解",
            "何も起きない日がいちばん長期投資らしい",
            "積立設定を忘れてる人が一番儲かる",
        ],
    },
    "20年投資を続けた人だけが見える景色": {
        "layer": "土台",
        "core_problem": "継続習慣",
        "shorts_potential": [
            "3年続けたあなたは上位10%",
            "20年後の景色：月3万→約6000万円",
        ],
    },
    "投資の格言10選：暴落時に読み返したい言葉たち": {
        "layer": "土台",
        "core_problem": "格言・哲学",
        "shorts_potential": [
            "個別格言を1本ずつShorts化（10本分のネタ）",
        ],
    },
    "世界経済は200年間成長し続けている理由": {
        "layer": "土台",
        "core_problem": "歴史的根拠",
        "shorts_potential": [
            "世界のGDPは過去50年で10倍",
            "人口80億人→経済成長は止まらない",
        ],
    },
    "感情に負けない投資：行動経済学から学ぶガチホの技術": {
        "layer": "中核",
        "core_problem": "感情売買",
        "shorts_potential": [
            "損失は利益の2倍痛い（損失回避バイアス）",
            "口座を見る頻度と投資成績の逆相関",
            "ルールより感情で動いてしまった人へ",
        ],
    },
    "日経平均34年の旅：バブル崩壊から最高値更新まで": {
        "layer": "入口",
        "core_problem": "歴史的根拠",
        "shorts_potential": [
            "日経平均34年で最高値更新した事実",
            "バブル崩壊後に積立していたら何年で黒字？",
        ],
    },
    "チャーリー・マンガーの投資哲学：忍耐と合理性": {
        "layer": "土台",
        "core_problem": "格言・哲学",
        "shorts_potential": [
            "マンガー「座って待つだけで金持ちになれる」",
        ],
    },
    "月3万円の積立が30年後の人生を変えるシミュレーション": {
        "layer": "入口",
        "core_problem": "数字・データ",
        "shorts_potential": [
            "月3万円×30年=約6000万円（年利7%）",
            "月1万円でも20年で約500万円",
            "遅く始めた人ほど大きく積めば追いつける計算",
        ],
    },
    "暴落時にやるべきこと、やってはいけないこと": {
        "layer": "入口",
        "core_problem": "暴落不安",
        "shorts_potential": [
            "暴落時に売った人の90%が回復前に離脱",
            "暴落時にやるべきことは何もしないこと",
        ],
    },
    "長期投資と短期トレードの決定的な違い": {
        "layer": "中核",
        "core_problem": "正解不安",
        "shorts_potential": [
            "プロの多くがインデックスに負ける事実",
            "保有期間が短い人ほど損する研究結果",
        ],
    },
    "配当再投資の威力：雪だるま式に増える資産の仕組み": {
        "layer": "土台",
        "core_problem": "数字・データ",
        "shorts_potential": [
            "配当再投資で30年リターンが2.5倍",
            "配当金を使った人が5年後に失う金額",
        ],
    },
    "長期投資でFIREを目指す：現実的なシミュレーション": {
        "layer": "中核",
        "core_problem": "比較疲れ",
        "shorts_potential": [
            "FIRE達成者を見て焦る前に知ってほしい3つの事実",
            "4%ルールで1億円あれば年400万円の計算",
        ],
    },
    "なぜプロの投資家の多くがインデックスに負けるのか": {
        "layer": "土台",
        "core_problem": "数字・データ",
        "shorts_potential": [
            "アクティブファンドの80%が10年でインデックスに負ける",
        ],
    },
    "投資を続けるコツ：モチベーションの保ち方5選": {
        "layer": "土台",
        "core_problem": "継続習慣",
        "shorts_potential": [
            "証券口座を見ないことが最強のコツ",
            "チャートを見なかった週が一番いい投資判断",
        ],
    },
}


def main():
    with open(TOPICS_PATH) as f:
        data = json.load(f)

    stats = {"入口": 0, "中核": 0, "土台": 0}
    total_shorts = 0

    for i, topic in enumerate(data["long"]):
        if not isinstance(topic, dict):
            continue
        topic_text = topic.get("topic", "")
        cls = LONG_CLASSIFICATION.get(topic_text)
        if cls:
            topic["layer"] = cls["layer"]
            topic["core_problem"] = cls["core_problem"]
            topic["shorts_potential"] = cls["shorts_potential"]
            stats[cls["layer"]] += 1
            total_shorts += len(cls["shorts_potential"])
        else:
            print(f"WARNING: 未分類の長尺: {topic_text}")

    with open(TOPICS_PATH, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n=== 長尺 3層分類結果 ({len(data['long'])}本) ===")
    for layer, count in stats.items():
        print(f"  {layer}: {count}本")

    print(f"\n=== Shorts切り出し候補: 合計 {total_shorts}本 ===")
    for topic in data["long"]:
        if isinstance(topic, dict) and topic.get("shorts_potential"):
            name = topic["topic"][:30]
            count = len(topic["shorts_potential"])
            print(f"  {name}…: {count}本")


if __name__ == "__main__":
    main()
