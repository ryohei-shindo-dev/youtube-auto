"""
stock_scorer.py — 在庫スコアリング＆公開順最適化

done/ 内の生成済み動画（transcript.json）をスコアリングし、
hookの偏り・タイトルの具体性・類似度を考慮した最適公開順を算出する。

使い方:
    python stock_scorer.py              # スコアリング＋公開順出力
    python stock_scorer.py --dry-run    # JSON書き出しなし（確認のみ）

出力:
    publish_queue.json — 最適化された公開順のフォルダ名リスト
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from collections import Counter
from difflib import SequenceMatcher

from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).parent / ".env")

SCRIPT_DIR = pathlib.Path(__file__).parent
DONE_DIR = SCRIPT_DIR / "done"

# hook定義は auto_publish.py が正本
from auto_publish import (
    HOOK_CATEGORIES,
    STEM_TO_CATEGORY,
    extract_hook_stem,
    extract_hook_category,
    _read_hook_text,
)
from candidate_ranker import _RE_NUMBER

# ── 感情トーン分類 ──
# テーマ→感情トーンのマッピング
_THEME_TONE_MAP = {
    "後悔系": "high_pain",
    "比較焦り系": "high_pain",
    "積立疲れ系": "mid_pain",
    "あるある": "mid_pain",
    "歴史データ": "mid_pain",
    "継続モチベ系": "recovery",
    "メリット": "recovery",
    "格言": "recovery",
    "ガチホモチベ": "recovery",
    "具体数字系": "mid_pain",
}


# 具体的なキーワード（数字以外でも具体性の高いワード）
_SPECIFIC_KEYWORDS = [
    "1800万", "72", "3年", "S&P500", "オルカン", "NISA", "iDeCo",
    "配当", "4%", "リーマン", "コロナ", "ITバブル",
]


# ── データ読み込み ──

def _load_all_transcripts() -> list[dict]:
    """done/ 内の全 transcript.json を読み込む。"""
    scripts = []
    if not DONE_DIR.exists():
        return scripts
    for folder in sorted(DONE_DIR.iterdir()):
        if not folder.is_dir():
            continue
        transcript = folder / "transcript.json"
        if not transcript.exists():
            continue
        try:
            data = json.loads(transcript.read_text(encoding="utf-8"))
            hook_text = ""
            for s in data.get("scenes", []):
                if s.get("role") == "hook":
                    hook_text = s.get("text", "").rstrip("。？！ ")
                    break
            scripts.append({
                "folder": folder.name,
                "title": data.get("title", ""),
                "hook": hook_text,
            })
        except (json.JSONDecodeError, OSError):
            continue
    return scripts


def _read_sheet_rows() -> list[list[str]]:
    """投稿管理シートの全行を取得する。"""
    import sheets
    sheet_id = os.getenv("YOUTUBE_SHEET_ID", "")
    if not sheet_id:
        print("[エラー] YOUTUBE_SHEET_ID が設定されていません。")
        sys.exit(1)
    svc = sheets.get_service()
    result = svc.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range="投稿管理!A:H",
    ).execute()
    return result.get("values", [])


def _build_sheet_status_map(rows: list[list[str]]) -> dict[str, dict]:
    """シート行をフォルダ名でインデックス化。

    戻り値: {folder_name: {"status": str, "title": str, "theme": str, "tone": str}}
    """
    import sheets
    C = sheets.COL
    status_map = {}
    for row in rows[1:]:  # ヘッダーを飛ばす
        folder = sheets.get_cell(row, C["folder"])
        if not folder:
            continue
        kind = sheets.get_cell(row, C["type"])
        theme = kind.replace("Shorts/", "") if kind.startswith("Shorts/") else ""
        tone = _THEME_TONE_MAP.get(theme, "mid_pain")
        status_map[folder] = {
            "status": sheets.get_cell(row, C["status"]),
            "title": sheets.get_cell(row, C["title"]),
            "theme": theme,
            "tone": tone,
        }
    return status_map




# ── スコアリング ──

def score_videos(
    all_scripts: list[dict],
    unpublished: list[dict],
) -> list[dict]:
    """未公開動画をスコアリングする。

    戻り値: スコア付きの動画リスト（降順ソート済み）
    """
    # 全動画のhookステム分布を集計
    stem_counts: Counter = Counter()
    for s in all_scripts:
        stem = extract_hook_stem(s["hook"])
        stem_counts[stem] += 1

    # 全動画のhookテキスト出現回数
    hook_text_counts: Counter = Counter()
    for s in all_scripts:
        hook_text_counts[s["hook"]] += 1

    scored = []
    for video in unpublished:
        score = 0
        reasons = []

        # 1. hook_penalty: 同一ステムが5本超なら -2/本
        stem = extract_hook_stem(video["hook"])
        stem_count = stem_counts[stem]
        if stem_count > 5:
            penalty = -2 * (stem_count - 5)
            score += penalty
            reasons.append(f"hook偏り({stem}={stem_count}本): {penalty:+d}")

        # 2. topic_match: タイトルに具体的な数字/キーワードがあれば+3、なければ-2
        title = video["title"]
        has_number = bool(_RE_NUMBER.search(title))
        has_keyword = any(kw in title for kw in _SPECIFIC_KEYWORDS)
        if has_number or has_keyword:
            score += 3
            reasons.append("タイトル具体性: +3")
        else:
            score -= 2
            reasons.append("タイトル抽象的: -2")

        # 3. title_diversity: 他の未公開動画との類似度チェック
        similar_count = 0
        for other in unpublished:
            if other["folder"] == video["folder"]:
                continue
            sim = SequenceMatcher(None, title, other["title"]).ratio()
            if sim > 0.6:
                similar_count += 1
        if similar_count > 0:
            penalty = -2 * similar_count
            score += penalty
            reasons.append(f"類似タイトル{similar_count}本: {penalty:+d}")

        # 4. hook_uniqueness: hookが3本未満なら+2
        hook_count = hook_text_counts[video["hook"]]
        if hook_count < 3:
            score += 2
            reasons.append(f"hookユニーク({hook_count}本): +2")

        category = extract_hook_category(video["hook"])
        tone = video.get("tone", "mid_pain")
        scored.append({
            "folder": video["folder"],
            "title": title,
            "hook": video["hook"],
            "hook_stem": stem,
            "hook_category": category,
            "tone": tone,
            "score": score,
            "reasons": reasons,
        })

    # スコア降順でソート
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


# ── 公開順最適化（制約付き並べ替え） ──

def triage(scored: list[dict]) -> dict[str, list[dict]]:
    """Cランク動画を 残す/後回し/捨てる に仕分ける。

    ChatGPT提案（2026-03-12）に基づく基準:
    - 残す: タイトルに具体性がある or 同じhook群でも論点が違う
    - 後回し: 中身は悪くないが今出すと似る
    - 捨てる: hookも結論も同じ、タイトルが抽象的、類似タイトルあり

    戻り値: {"keep": [...], "delay": [...], "discard": [...]}
    """
    keep = []
    delay = []
    discard = []

    # 同一ステムの出現回数をカウント（scored 内）
    stem_counts: Counter = Counter(v["hook_stem"] for v in scored)

    # 同一ステムで何本目かを追跡
    stem_seen: Counter = Counter()

    for v in scored:
        rank = classify(v["score"])

        # A/Bランクは無条件で残す
        if rank != "C":
            keep.append(v)
            continue

        stem = v["hook_stem"]
        stem_seen[stem] += 1
        total_in_stem = stem_counts[stem]
        has_specific_title = bool(_RE_NUMBER.search(v["title"])) or any(
            kw in v["title"] for kw in _SPECIFIC_KEYWORDS
        )
        has_similar = any("類似" in r for r in v["reasons"])

        # 捨てる条件: 同一ステムが多すぎ + タイトル抽象的 + 類似あり
        if total_in_stem >= 10 and not has_specific_title:
            # 同一ステム10本超で抽象的 → 大半は捨てる（最初の3本だけ残す）
            if stem_seen[stem] <= 3:
                delay.append(v)
            else:
                discard.append(v)
        elif has_similar and not has_specific_title:
            # 類似タイトルあり＋抽象的 → 捨てる
            discard.append(v)
        elif total_in_stem >= 5 and not has_specific_title:
            # ステム5本超で抽象的 → 後回し（最初の2本だけ残す）
            if stem_seen[stem] <= 2:
                delay.append(v)
            else:
                discard.append(v)
        elif has_specific_title:
            # 具体的なタイトルがあるCランクは残す
            keep.append(v)
        else:
            # それ以外は後回し
            delay.append(v)

    return {"keep": keep, "delay": delay, "discard": discard}


def reorder_with_constraints(scored: list[dict]) -> list[dict]:
    """スコア順をベースに、hookの偏りと感情トーンを制約で分散させる。

    制約:
    - 同一hookステムは8連続以内に再出現しない
    - 同一hookカテゴリは5連続以内に再出現しない
    - 同一感情トーンは3連続以内に再出現しない
    - 痛み系（high_pain）2本の後は回復系（recovery）を優先
    """
    result: list[dict] = []
    remaining = list(scored)  # スコア降順のコピー

    while remaining:
        placed = False
        for i, candidate in enumerate(remaining):
            # 制約チェック: 直近N本の stem/category/tone を確認
            recent_stems = [r["hook_stem"] for r in result[-8:]]
            recent_cats = [r["hook_category"] for r in result[-5:]]
            recent_tones = [r.get("tone", "mid_pain") for r in result[-3:]]

            stem_ok = candidate["hook_stem"] not in recent_stems
            cat_ok = candidate["hook_category"] not in recent_cats

            # 感情トーン制約: 同一トーン3連続禁止
            candidate_tone = candidate.get("tone", "mid_pain")
            tone_ok = not (
                len(recent_tones) >= 2
                and all(t == candidate_tone for t in recent_tones[-2:])
            )

            # 痛み系2連続の後は回復系を優先（ソフト制約: 候補があれば）
            pain_streak = 0
            for r in reversed(result):
                if r.get("tone") in ("high_pain", "mid_pain"):
                    pain_streak += 1
                else:
                    break
            pain_needs_recovery = pain_streak >= 2 and candidate_tone != "recovery"
            # pain_needs_recovery はソフト制約なので、他に候補がなければ無視

            if stem_ok and cat_ok and tone_ok and not pain_needs_recovery:
                result.append(candidate)
                remaining.pop(i)
                placed = True
                break

        if not placed:
            # ソフト制約(pain_needs_recovery)を緩和して再試行
            for i, candidate in enumerate(remaining):
                recent_stems = [r["hook_stem"] for r in result[-8:]]
                recent_cats = [r["hook_category"] for r in result[-5:]]
                recent_tones = [r.get("tone", "mid_pain") for r in result[-3:]]

                stem_ok = candidate["hook_stem"] not in recent_stems
                cat_ok = candidate["hook_category"] not in recent_cats
                candidate_tone = candidate.get("tone", "mid_pain")
                tone_ok = not (
                    len(recent_tones) >= 2
                    and all(t == candidate_tone for t in recent_tones[-2:])
                )

                if stem_ok and cat_ok and tone_ok:
                    result.append(candidate)
                    remaining.pop(i)
                    placed = True
                    break

        if not placed:
            # すべての制約を満たせない場合、スコア最上位をそのまま配置
            result.append(remaining.pop(0))

    return result


# ── A/B/C 分類 ──

def classify(score: int) -> str:
    """スコアをA/B/Cランクに分類する。"""
    if score >= 3:
        return "A"
    elif score >= 0:
        return "B"
    else:
        return "C"


# ── メイン処理 ──

def main() -> None:
    parser = argparse.ArgumentParser(description="在庫スコアリング＆公開順最適化")
    parser.add_argument("--dry-run", action="store_true", help="JSON書き出しなし（確認のみ）")
    args = parser.parse_args()

    # 1. 全 transcript.json を読み込み
    print("done/ フォルダからtranscript.jsonを読み込み中...")
    all_scripts = _load_all_transcripts()
    print(f"  {len(all_scripts)}本の動画を検出")

    # 2. シートからステータスを取得
    print("投稿管理シートを読み込み中...")
    rows = _read_sheet_rows()
    status_map = _build_sheet_status_map(rows)
    print(f"  シートに{len(status_map)}件のエントリ")

    # 3. 未公開動画を抽出
    import sheets
    unpublished = []
    published_count = 0
    no_sheet_count = 0

    for script in all_scripts:
        folder = script["folder"]
        info = status_map.get(folder)
        if info is None:
            no_sheet_count += 1
            continue
        if info["status"] == sheets.STATUS_PUBLISHED:
            published_count += 1
            continue
        if info["status"] == sheets.STATUS_GENERATED:
            script["tone"] = info.get("tone", "mid_pain")
            unpublished.append(script)

    print(f"  公開済み: {published_count}本")
    print(f"  未公開（生成済み）: {len(unpublished)}本")
    if no_sheet_count > 0:
        print(f"  シート未登録: {no_sheet_count}本")

    if not unpublished:
        print("\n未公開の動画がありません。")
        return

    # 4. スコアリング
    print("\nスコアリング中...")
    scored = score_videos(all_scripts, unpublished)

    # 5. トリアージ（Cランクを仕分け）
    tri = triage(scored)
    publishable = tri["keep"] + tri["delay"]  # 捨てる分は除外
    # スコア降順でソートし直す
    publishable.sort(key=lambda x: x["score"], reverse=True)

    print(f"\n  トリアージ結果:")
    print(f"    残す: {len(tri['keep'])}本（A/B + 具体的C）")
    print(f"    後回し: {len(tri['delay'])}本（弱いが最低限の価値あり）")
    print(f"    捨てる: {len(tri['discard'])}本（同質化・抽象的）")

    if tri["discard"]:
        print(f"\n  [捨てる {len(tri['discard'])}本]")
        for v in tri["discard"]:
            print(f"    ✗ {v['title']}  [stem={v['hook_stem']}]")

    # 6. 制約付き並べ替え（捨てる分を除外して並べ替え）
    reordered = reorder_with_constraints(publishable)

    # 6. 結果表示
    rank_counts: Counter = Counter()

    print("\n" + "=" * 70)
    print("スコアリング結果（公開推奨順）")
    print("=" * 70)

    for i, v in enumerate(reordered, 1):
        rank = classify(v["score"])
        rank_counts[rank] += 1
        print(f"\n{i:3d}. [{rank}] スコア {v['score']:+3d}  {v['folder']}")
        print(f"     タイトル: {v['title']}")
        print(f"     hook: {v['hook']}  [stem={v['hook_stem']}, cat={v['hook_category']}, tone={v.get('tone', '?')}]")
        if v["reasons"]:
            for r in v["reasons"]:
                print(f"       - {r}")

    # 7. 統計サマリー
    print("\n" + "=" * 70)
    print("ランク分布")
    print("=" * 70)
    for rank in ["A", "B", "C"]:
        count = rank_counts.get(rank, 0)
        bar = "#" * count
        print(f"  {rank}: {count:3d}本  {bar}")
    print(f"  合計: {sum(rank_counts.values())}本")

    # hookステム分布（上位10）
    stem_dist: Counter = Counter()
    for v in reordered:
        stem_dist[v["hook_stem"]] += 1
    print("\nhookステム分布（未公開のみ、上位10）:")
    for stem, count in stem_dist.most_common(10):
        cat = STEM_TO_CATEGORY.get(stem, "その他")
        print(f"  {stem}({cat}): {count}本")

    # カテゴリ分布
    cat_dist: Counter = Counter()
    for v in reordered:
        cat_dist[v["hook_category"]] += 1
    print("\nカテゴリ分布（未公開のみ）:")
    for cat, count in cat_dist.most_common():
        print(f"  {cat}: {count}本")

    # 感情トーン分布
    tone_dist: Counter = Counter()
    for v in reordered:
        tone_dist[v.get("tone", "?")] += 1
    tone_labels = {"high_pain": "高痛み", "mid_pain": "中痛み→安心", "recovery": "回復・肯定"}
    print("\n感情トーン分布（未公開のみ）:")
    for tone, count in tone_dist.most_common():
        label = tone_labels.get(tone, tone)
        print(f"  {label}({tone}): {count}本")

    # 感情トーン3連続チェック
    tone_violations = 0
    for i in range(2, len(reordered)):
        if (reordered[i].get("tone") == reordered[i-1].get("tone") == reordered[i-2].get("tone")):
            tone_violations += 1
    if tone_violations:
        print(f"\n  [警告] 感情トーン3連続: {tone_violations}箇所")
    else:
        print("\n  感情トーン3連続: なし（OK）")

    # 8. publish_queue.json 書き出し
    queue = [v["folder"] for v in reordered]
    if args.dry_run:
        print("\n[dry-run] publish_queue.json への書き出しをスキップしました。")
    else:
        out_path = SCRIPT_DIR / "publish_queue.json"
        out_path.write_text(
            json.dumps(queue, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\npublish_queue.json に{len(queue)}本の公開順を書き出しました。")


if __name__ == "__main__":
    main()
