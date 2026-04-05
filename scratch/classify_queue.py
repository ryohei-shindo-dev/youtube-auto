"""publish_queue 34本にlayerタグを付与して集計"""
from __future__ import annotations
import json, os
from pathlib import Path

QUEUE_PATH = Path("data/queues/publish_queue.json")
OUTPUT_PATH = Path("data/queues/publish_queue_layered.json")

# 分類基準（topics.jsonと同じ）
# 入口: 初見でも分かる痛み/具体数字（暴落/含み損/後悔/制度）
# 中核: 比較疲れ/目移り/正解不安/動いて崩す
# 土台: 継続思想/静かな肯定/複利実感

# 手動分類（34本、transcript.jsonのtopic文から判定）
QUEUE_CLASSIFICATION = {
    # 1. 遅く始めた人ほど大きく積み立てれば追いつける計算
    0: {"layer": "入口", "core_problem": "数字・データ"},
    # 2. 暴落後1年のリターンは平均+25%という事実
    1: {"layer": "入口", "core_problem": "暴落不安"},
    # 3. 1年目の元本割れがつらい人へ：それは脳の仕組みのせい
    2: {"layer": "入口", "core_problem": "損失回避"},
    # 4. 新しい投資先が全部よく見える時期
    3: {"layer": "中核", "core_problem": "目移り"},
    # 5. S&P500が高値回復まで7年かかった時期がある事実
    4: {"layer": "入口", "core_problem": "歴史的根拠"},
    # 6. 50歳から始めても65歳で1500万円を作れるシミュレーション
    5: {"layer": "入口", "core_problem": "数字・データ"},
    # 7. 月1万円の積み立てでも20年後には約500万円になる事実
    6: {"layer": "入口", "core_problem": "数字・データ"},
    # 8. 個別株の爆益報告を見たあと、積立が色あせて見える人へ
    7: {"layer": "中核", "core_problem": "比較疲れ"},
    # 9. 信託報酬0.1%と1%の差が30年で800万円になる事実
    8: {"layer": "土台", "core_problem": "数字・データ"},
    # 10. iDeCoを60歳まで待てずに後悔する人の共通点
    9: {"layer": "入口", "core_problem": "後悔"},
    # 11. 投資を始めるのが10年遅れた人の機会損失は2000万円
    10: {"layer": "入口", "core_problem": "後悔"},
    # 12. 「もっと早く始めればよかった」は全投資家が思うこと
    11: {"layer": "入口", "core_problem": "後悔"},
    # 13. 毎月の積み立ては、未来の自分への仕送り
    12: {"layer": "土台", "core_problem": "継続習慣"},
    # 14. 年間40万円のNISA枠を20年使い切ると非課税効果は約160万円
    13: {"layer": "入口", "core_problem": "制度活用"},
    # 15. 月5万円×30年で6000万円のグラフを信じた人へ：年利7%は毎年一定ではない
    14: {"layer": "中核", "core_problem": "正解不安"},
    # 16. 3年続けたあなたへ。それだけで上位10%にいる
    15: {"layer": "土台", "core_problem": "継続習慣"},
    # 17. 増えてない人へ：S&P500も最初の5年は退屈だった
    16: {"layer": "中核", "core_problem": "退屈"},
    # 18. 投資を始めて2年、まだプラマイゼロの人へ
    17: {"layer": "中核", "core_problem": "退屈"},
    # 19. (topic不明)
    18: {"layer": "不明", "core_problem": "不明"},
    # 20. 暴落で売った人が1年後に後悔した理由
    19: {"layer": "入口", "core_problem": "後悔"},
    # 21. NISA枠を解約した人が再投資できない事実
    20: {"layer": "入口", "core_problem": "後悔"},
    # 22. 毎月の積み立てを1年休んだ人が失った複利効果は150万円
    21: {"layer": "入口", "core_problem": "後悔"},
    # 23. 30歳で投資をやめた人と続けた人の60歳時点の差は4000万円
    22: {"layer": "入口", "core_problem": "数字・データ"},
    # 24. 売った途端に上がった人へ：タイミング売買の落とし穴
    23: {"layer": "中核", "core_problem": "タイミング失敗"},
    # 25. 下がるの待ってたら乗り遅れた人へ
    24: {"layer": "中核", "core_problem": "タイミング失敗"},
    # 26. 65歳までに3000万円を作るには月いくら必要？
    25: {"layer": "入口", "core_problem": "数字・データ"},
    # 27. 年利1%の差が30年で500万円の差になる現実
    26: {"layer": "土台", "core_problem": "数字・データ"},
    # 28. リーマンショックから5年で株価は完全回復した
    27: {"layer": "入口", "core_problem": "歴史的根拠"},
    # 29. 1987年ブラックマンデー：1日で22%下落→2年で回復
    28: {"layer": "入口", "core_problem": "歴史的根拠"},
    # 30. ITバブル崩壊からの回復に13年。でも積み立てなら7年で黒字
    29: {"layer": "入口", "core_problem": "歴史的根拠"},
    # 31. 過去50年で最悪のタイミングで買い続けても利益が出た話
    30: {"layer": "土台", "core_problem": "継続習慣"},
    # 32. 30歳で投資を始めるのは遅い？20歳との差を計算してみた
    31: {"layer": "入口", "core_problem": "数字・データ"},
    # 33. FIRE達成者を見て焦る前に知ってほしい3つの事実
    32: {"layer": "中核", "core_problem": "比較疲れ"},
    # 34. 高配当ETFに乗り換えたくなった日
    33: {"layer": "中核", "core_problem": "乗��換え誘惑"},
}


def main():
    with open(QUEUE_PATH) as f:
        queue = json.load(f)

    results = []
    stats = {"入口": 0, "中核": 0, "土台": 0, "不明": 0}
    cp_stats: dict[str, int] = {}

    for i, folder in enumerate(queue):
        cls = QUEUE_CLASSIFICATION.get(i, {"layer": "不明", "core_problem": "不明"})

        # transcript からtopicを取得
        tp = f"done/{folder}/transcript.json"
        topic_text = "?"
        if os.path.exists(tp):
            with open(tp) as f:
                t = json.load(f)
            topic_text = t.get("topic", "?")

        results.append({
            "folder": folder,
            "topic": topic_text,
            "layer": cls["layer"],
            "core_problem": cls["core_problem"],
        })
        stats[cls["layer"]] += 1
        cp_stats[cls["core_problem"]] = cp_stats.get(cls["core_problem"], 0) + 1

    # 保存
    with open(OUTPUT_PATH, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # 集計
    total = sum(v for k, v in stats.items() if k != "不明")
    print(f"\n=== publish_queue 3層分類結果 ({len(queue)}本) ===")
    for layer in ["入口", "中核", "土台", "不明"]:
        count = stats[layer]
        pct = count / len(queue) * 100
        print(f"  {layer}: {count}本 ({pct:.1f}%)")

    print(f"\n=== core_problem 分布 ===")
    for cp, count in sorted(cp_stats.items(), key=lambda x: -x[1]):
        print(f"  {cp}: {count}本")


if __name__ == "__main__":
    main()
