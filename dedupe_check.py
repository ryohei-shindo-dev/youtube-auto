"""
dedupe_check.py — 同質化検知

生成済み台本が、既存の動画と似すぎていないかチェックする。
done/ 内の全 transcript.json を読み取り、タイトル・hook の類似度を判定。

使い方:
    from dedupe_check import check_duplicate
    result = check_duplicate(script_data)
    if result["is_duplicate"]:
        print(result["reason"])  # 類似元の情報
"""

from __future__ import annotations

import json
import pathlib
from difflib import SequenceMatcher

SCRIPT_DIR = pathlib.Path(__file__).parent
DONE_DIR = SCRIPT_DIR / "done"

# 類似度の閾値（0.0〜1.0）。これ以上なら「似すぎ」と判定
TITLE_SIMILARITY_THRESHOLD = 0.65
HOOK_SIMILARITY_THRESHOLD = 0.80
# タイトルとhookの両方が一定以上なら重複判定
COMBINED_TITLE_THRESHOLD = 0.50
COMBINED_HOOK_THRESHOLD = 0.60

# モジュールレベルキャッシュ（バッチ実行中の繰り返し読み込みを防ぐ）
_cache: list[dict] | None = None


def _load_existing_scripts() -> list[dict]:
    """done/ 内の全 transcript.json を読み込む（キャッシュあり）。"""
    global _cache
    if _cache is not None:
        return _cache

    scripts = []
    if not DONE_DIR.exists():
        _cache = scripts
        return scripts
    for folder in DONE_DIR.iterdir():
        if not folder.is_dir():
            continue
        transcript = folder / "transcript.json"
        if not transcript.exists():
            continue
        try:
            data = json.loads(transcript.read_text(encoding="utf-8"))
            title = data.get("title", "")
            hook = ""
            data_text = ""
            for s in data.get("scenes", []):
                role = s.get("role")
                if role == "hook" and not hook:
                    hook = s.get("text", "").rstrip("。？！ ")
                elif role in ("data", "fact") and not data_text:
                    data_text = s.get("text", "")
                if hook and data_text:
                    break
            scripts.append({
                "folder": folder.name,
                "title": title,
                "hook": hook,
                "data": data_text,
            })
        except (json.JSONDecodeError, OSError):
            continue

    _cache = scripts
    return scripts


def _similarity(a: str, b: str) -> float:
    """2つの文字列の類似度を返す（0.0〜1.0）。"""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def check_duplicate(script_data: dict) -> dict:
    """新しい台本が既存の動画と似すぎていないかチェックする。

    戻り値:
        {
            "is_duplicate": bool,
            "reason": str,              # 重複判定の理由（重複時のみ）
            "similar_to": str,          # 類似元のタイトル（重複時のみ）
            "title_similarity": float,  # 最も高いタイトル類似度
            "hook_similarity": float,   # 最も高いhook類似度
        }
    """
    existing = _load_existing_scripts()
    no_dup = {
        "is_duplicate": False,
        "reason": "",
        "similar_to": "",
        "title_similarity": 0.0,
        "hook_similarity": 0.0,
    }
    if not existing:
        return no_dup

    new_title = script_data.get("title", "")
    new_hook = ""
    new_data = ""
    for s in script_data.get("scenes", []):
        role = s.get("role")
        if role == "hook" and not new_hook:
            new_hook = s.get("text", "").rstrip("。？！ ")
        elif role == "data" and not new_data:
            new_data = s.get("text", "")
        if new_hook and new_data:
            break

    max_title_sim = 0.0
    max_hook_sim = 0.0
    most_similar_title = ""

    for ex in existing:
        title_sim = _similarity(new_title, ex["title"])
        hook_sim = _similarity(new_hook, ex["hook"])

        # 最大値を更新
        if title_sim > max_title_sim:
            max_title_sim = title_sim
            most_similar_title = ex["title"]
        if hook_sim > max_hook_sim:
            max_hook_sim = hook_sim

        # 判定1: タイトルだけで非常に似ている
        if title_sim >= TITLE_SIMILARITY_THRESHOLD:
            return {
                "is_duplicate": True,
                "reason": (
                    f"タイトルが似すぎ（類似度{title_sim:.0%}）: "
                    f"「{new_title}」≈「{ex['title']}」"
                ),
                "similar_to": ex["title"],
                "title_similarity": title_sim,
                "hook_similarity": hook_sim,
            }

        # 判定2: hookが完全一致 + タイトルもそこそこ似ている
        if (hook_sim >= COMBINED_HOOK_THRESHOLD
                and title_sim >= COMBINED_TITLE_THRESHOLD):
            return {
                "is_duplicate": True,
                "reason": (
                    f"hookとタイトルの組み合わせが類似"
                    f"（hook類似度{hook_sim:.0%}, タイトル類似度{title_sim:.0%}）: "
                    f"「{new_title}」≈「{ex['title']}」"
                ),
                "similar_to": ex["title"],
                "title_similarity": title_sim,
                "hook_similarity": hook_sim,
            }

        # 判定3: hookが完全一致 かつ dataも似ている
        # （hookは50個プールから選ぶので同じhookの再利用は正常。
        #   dataも似ている場合のみ重複とする）
        if hook_sim >= HOOK_SIMILARITY_THRESHOLD:
            data_sim = _similarity(new_data, ex["data"])
            if data_sim >= 0.50:
                return {
                    "is_duplicate": True,
                    "reason": (
                        f"hookとdataが類似（hook類似度{hook_sim:.0%}, "
                        f"data類似度{data_sim:.0%}）: "
                        f"「{new_hook}」≈「{ex['hook']}」（{ex['title']}）"
                    ),
                    "similar_to": ex["title"],
                    "title_similarity": title_sim,
                    "hook_similarity": hook_sim,
                }

    no_dup["similar_to"] = most_similar_title
    no_dup["title_similarity"] = max_title_sim
    no_dup["hook_similarity"] = max_hook_sim
    return no_dup


def format_report(result: dict) -> str:
    """重複チェック結果を人間が読める文字列にする。"""
    if result["is_duplicate"]:
        return (
            f"  [重複検知] ⚠ {result['reason']}\n"
            f"    → 再生成を推奨"
        )
    return (
        f"  [重複チェック] ✓ 類似動画なし"
        f"（最大タイトル類似度: {result['title_similarity']:.0%}, "
        f"最大hook類似度: {result['hook_similarity']:.0%}）"
    )
