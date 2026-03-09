"""
analytics_analyze.py
蓄積された分析データから傾向を抽出し、analytics_insights.json を出力するスクリプト。

使い方:
    python analytics_analyze.py                # 通常の週次分析
    python analytics_analyze.py --mode=weekly  # 同上
    python analytics_analyze.py --mode=milestone  # 30本到達時の本分析

出力:
    analytics_insights.json — script_gen.py が台本生成時に読み込む

cron設定例（毎週月曜23:00に実行）:
    0 23 * * 1 cd /Users/shindoryohei/youtube-auto && ./run_with_notify.sh analytics_analyze venv/bin/python analytics_analyze.py
"""

from __future__ import annotations

import json
import math
import pathlib
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta

SCRIPT_DIR = pathlib.Path(__file__).parent
ANALYTICS_FILE = SCRIPT_DIR / "analytics_log.json"
INSIGHTS_FILE = SCRIPT_DIR / "analytics_insights.json"

# --- 分析に必要な最小本数 ---
MIN_VIDEOS_WEEKLY = 5      # 週次軽分析の最低本数
MIN_VIDEOS_FULL = 30       # 本分析の最低本数
MIN_SAMPLE_PER_PATTERN = 2 # パターン判定に必要な最小サンプル数


def load_analytics() -> dict:
    """analytics_log.json を読み込む。"""
    if not ANALYTICS_FILE.exists():
        return {}
    with open(ANALYTICS_FILE, encoding="utf-8") as f:
        return json.load(f)


def _get_latest_snapshot(history: dict) -> list[dict]:
    """最新日のスナップショットを返す。"""
    if not history:
        return []
    latest_date = max(history.keys())
    return history[latest_date]


def _calc_24h_views(history: dict) -> dict[str, int]:
    """各動画の公開後24時間時点の再生数を推定する。

    日次スナップショットなので正確な24h値は取れないが、
    公開翌日のスナップショットの値を近似値として使う。
    """
    # video_id → published_at のマッピング
    video_info: dict[str, str] = {}
    # video_id → {date: views} の時系列
    video_timeline: dict[str, dict[str, int]] = defaultdict(dict)

    for date_str, videos in sorted(history.items()):
        for v in videos:
            vid = v["video_id"]
            video_info[vid] = v.get("published_at", "")
            video_timeline[vid][date_str] = v["views"]

    result = {}
    for vid, pub_at in video_info.items():
        if not pub_at:
            continue
        # 公開日を算出（UTC→JST近似: +9h、日付だけ見るので概ねOK）
        pub_date_str = pub_at[:10]  # "2026-03-05"
        timeline = video_timeline[vid]

        # 公開翌日の値を24h近似として採用
        try:
            pub_date = datetime.strptime(pub_date_str, "%Y-%m-%d")
            next_day = (pub_date + timedelta(days=1)).strftime("%Y-%m-%d")
            # 翌日のスナップがなければ2日後を探す
            for offset in range(1, 4):
                check_date = (pub_date + timedelta(days=offset)).strftime("%Y-%m-%d")
                if check_date in timeline:
                    result[vid] = timeline[check_date]
                    break
        except ValueError:
            continue

    return result


def _extract_title_features(title: str) -> dict:
    """タイトルから特徴を抽出する。"""
    has_number = bool(re.search(r'\d', title))
    # 金額パターン
    has_money = bool(re.search(r'\d+万円|\d+円', title))
    # 期間パターン
    has_period = bool(re.search(r'\d+年|\d+ヶ月|\d+日', title))
    # パーセントパターン
    has_pct = bool(re.search(r'\d+%|\d+割', title))

    # hookワード抽出（タイトル先頭〜「｜」まで）
    hook_part = title.split("｜")[0] if "｜" in title else title
    hook_part = hook_part.split("、")[0].strip()

    return {
        "has_number": has_number,
        "has_money": has_money,
        "has_period": has_period,
        "has_pct": has_pct,
        "hook_part": hook_part,
    }


def analyze(history: dict, mode: str = "weekly") -> dict:
    """分析を実行し、insights辞書を返す。"""
    latest = _get_latest_snapshot(history)
    if not latest:
        print("分析するデータがありません。")
        return {}

    sample_size = len(latest)
    print(f"\n分析対象: {sample_size}本")

    # 本分析は30本以上必要
    if mode == "milestone" and sample_size < MIN_VIDEOS_FULL:
        print(f"  本分析には{MIN_VIDEOS_FULL}本以上必要です（現在{sample_size}本）。週次分析に切り替えます。")
        mode = "weekly"

    if sample_size < MIN_VIDEOS_WEEKLY:
        print(f"  分析には最低{MIN_VIDEOS_WEEKLY}本必要です。")
        return {}

    # --- 24h再生数の推定 ---
    views_24h = _calc_24h_views(history)

    # --- 最新スナップショットの再生数 ---
    videos = []
    for v in latest:
        features = _extract_title_features(v["title"])
        videos.append({
            **v,
            **features,
            "views_24h": views_24h.get(v["video_id"], v["views"]),
        })

    # 長尺動画を除外（Shortsのみ分析）
    shorts = [v for v in videos if v["views"] > 0]
    if not shorts:
        print("  再生数0の動画しかありません。")
        return {}

    avg_views = sum(v["views"] for v in shorts) / len(shorts)
    avg_views_24h = sum(v["views_24h"] for v in shorts) / len(shorts)

    # --- エンゲージメント指標 ---
    total_likes = sum(v.get("likes", 0) for v in shorts)
    total_comments = sum(v.get("comments", 0) for v in shorts)
    total_views = sum(v["views"] for v in shorts)
    avg_like_rate = total_likes / max(total_views, 1) * 100
    avg_comment_rate = total_comments / max(total_views, 1) * 100

    print(f"  平均再生数: {avg_views:.0f}")
    print(f"  平均24h再生数: {avg_views_24h:.0f}")
    print(f"  いいね率: {avg_like_rate:.2f}%")
    print(f"  コメント率: {avg_comment_rate:.3f}%")

    # --- タイトル数字分析 ---
    numeric_titles = [v for v in shorts if v["has_number"]]
    non_numeric = [v for v in shorts if not v["has_number"]]

    title_rules = {}
    if len(numeric_titles) >= MIN_SAMPLE_PER_PATTERN and len(non_numeric) >= MIN_SAMPLE_PER_PATTERN:
        avg_numeric = sum(v["views"] for v in numeric_titles) / len(numeric_titles)
        avg_non = sum(v["views"] for v in non_numeric) / len(non_numeric)
        ratio = avg_numeric / max(avg_non, 1)

        if ratio > 1.3:
            title_rules["prefer_numeric_titles"] = True
            title_rules["numeric_boost_ratio"] = round(ratio, 1)
            title_rules["numeric_title_ratio"] = 0.7
            print(f"  数字入りタイトル: 平均{avg_numeric:.0f}回 vs 数字なし: {avg_non:.0f}回（{ratio:.1f}倍）")
        title_rules["prefer_specific_timeframes"] = any(v["has_period"] for v in numeric_titles)
        title_rules["prefer_money_amounts"] = any(v["has_money"] for v in numeric_titles)

    # --- hook分析 ---
    hook_stats: dict[str, list] = defaultdict(list)
    for v in shorts:
        hook = v["hook_part"]
        if hook:
            hook_stats[hook].append(v["views"])

    strong_hooks = []
    weak_hooks = []
    for hook, views_list in hook_stats.items():
        if len(views_list) < 1:
            continue
        avg = sum(views_list) / len(views_list)
        score = round(avg / max(avg_views, 1), 1)
        entry = {"text": hook, "score": score, "sample_size": len(views_list), "avg_views": round(avg)}
        if score >= 1.3 and len(views_list) >= MIN_SAMPLE_PER_PATTERN:
            strong_hooks.append(entry)
        elif score <= 0.7 and len(views_list) >= MIN_SAMPLE_PER_PATTERN:
            weak_hooks.append(entry)

    strong_hooks.sort(key=lambda x: x["score"], reverse=True)
    weak_hooks.sort(key=lambda x: x["score"])

    # --- エンゲージメント上位動画 ---
    # いいね率・コメント率が高い動画を特定（再生数10以上のみ対象）
    eligible = [v for v in shorts if v["views"] >= 10]
    for v in eligible:
        v["like_rate"] = v.get("likes", 0) / max(v["views"], 1) * 100
        v["comment_rate"] = v.get("comments", 0) / max(v["views"], 1) * 100

    high_engagement = sorted(eligible, key=lambda v: v["like_rate"], reverse=True)[:3]

    # --- 上位/下位動画の特徴 ---
    sorted_by_views = sorted(shorts, key=lambda v: v["views"], reverse=True)
    top_videos = sorted_by_views[:3]
    bottom_videos = sorted_by_views[-3:]

    # --- confidence判定 ---
    if sample_size >= 50:
        confidence = "high"
    elif sample_size >= 30:
        confidence = "medium"
    elif sample_size >= 10:
        confidence = "low"
    else:
        confidence = "very_low"

    # --- prompt_guidance 生成 ---
    guidance = []
    if title_rules.get("prefer_numeric_titles"):
        guidance.append(
            f"タイトルに具体的な数字（金額・期間・割合）を入れると再生数が平均{title_rules.get('numeric_boost_ratio', 1.5)}倍。"
            f"70%の動画で数字入りタイトルを使え。"
        )
    if title_rules.get("prefer_money_amounts"):
        guidance.append("金額（1800万円、500万円等）はタイトルで特に強い。")
    if title_rules.get("prefer_specific_timeframes"):
        guidance.append("期間（3年目、20年、30年後等）もタイトルで効果的。")
    if strong_hooks:
        hooks_str = "、".join(h["text"] for h in strong_hooks[:3])
        guidance.append(f"最近強いhook語: {hooks_str}")
    if weak_hooks:
        weak_str = "、".join(h["text"] for h in weak_hooks[:3])
        guidance.append(f"避けるべきhook語: {weak_str}")
    # エンゲージメント分析のガイダンス
    if avg_like_rate >= 4.0:
        guidance.append(f"いいね率{avg_like_rate:.1f}%は良好。共感テーマが響いている。")
    elif avg_like_rate < 2.0 and sample_size >= 10:
        guidance.append(f"いいね率{avg_like_rate:.1f}%はやや低め。共感・感情に寄せたhookを増やす。")
    if high_engagement:
        eng_str = "、".join(v["title"][:20] for v in high_engagement[:2])
        guidance.append(f"エンゲージメント高い動画: {eng_str}")
    # トーン維持の注意
    guidance.append("数字を入れても煽りトーンにしない。落ち着いたトーンを維持。")

    # --- insights辞書の組み立て ---
    insights = {
        "meta": {
            "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00"),
            "sample_size": sample_size,
            "confidence": confidence,
            "mode": mode,
            "avg_views": round(avg_views),
            "avg_views_24h": round(avg_views_24h),
            "avg_like_rate_pct": round(avg_like_rate, 2),
            "avg_comment_rate_pct": round(avg_comment_rate, 3),
        },
        "title_rules": title_rules,
        "strong_hooks": strong_hooks[:5],
        "weak_hooks": weak_hooks[:5],
        "top_videos": [
            {"title": v["title"], "views": v["views"]}
            for v in top_videos
        ],
        "bottom_videos": [
            {"title": v["title"], "views": v["views"]}
            for v in bottom_videos
        ],
        "high_engagement": [
            {"title": v["title"], "views": v["views"],
             "like_rate_pct": round(v["like_rate"], 2),
             "comment_rate_pct": round(v["comment_rate"], 3)}
            for v in high_engagement
        ],
        "prompt_guidance": guidance,
    }

    return insights


def save_insights(insights: dict):
    """analytics_insights.json に保存する。"""
    with open(INSIGHTS_FILE, "w", encoding="utf-8") as f:
        json.dump(insights, f, ensure_ascii=False, indent=2)
    print(f"\n  analytics_insights.json 保存完了")
    print(f"  confidence: {insights['meta']['confidence']}")
    print(f"  guidance: {len(insights.get('prompt_guidance', []))}件")


def main():
    mode = "weekly"
    for arg in sys.argv[1:]:
        if arg.startswith("--mode="):
            mode = arg.split("=", 1)[1]

    print(f"\n{'='*60}")
    print(f"  分析実行: {datetime.now().strftime('%Y/%m/%d %H:%M')} (mode={mode})")
    print(f"{'='*60}")

    history = load_analytics()
    if not history:
        print("analytics_log.json が見つからないか空です。")
        return

    insights = analyze(history, mode=mode)
    if insights:
        save_insights(insights)


if __name__ == "__main__":
    main()
