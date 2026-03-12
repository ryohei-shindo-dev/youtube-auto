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


def _extract_hook_and_data(script_data: dict) -> tuple[str, str]:
    """scenes から hook テキストと data/fact テキストを抽出する。"""
    hook = ""
    data_text = ""
    for s in script_data.get("scenes", []):
        role = s.get("role")
        if role == "hook" and not hook:
            hook = s.get("text", "").rstrip("。？！ ")
        elif role in ("data", "fact") and not data_text:
            data_text = s.get("text", "")
        if hook and data_text:
            break
    return hook, data_text


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
            hook, data_text = _extract_hook_and_data(data)
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
    new_hook, new_data = _extract_hook_and_data(script_data)

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


def register_accepted(script_data: dict) -> None:
    """採用した台本をキャッシュに追加する（バッチ内の重複検知用）。

    batch_gen で1本採用するたびに呼ぶことで、
    同じバッチ内で生成した動画同士の重複を検知できる。
    """
    existing = _load_existing_scripts()
    title = script_data.get("title", "")
    hook, data_text = _extract_hook_and_data(script_data)
    existing.append({
        "folder": "(pending)",
        "title": title,
        "hook": hook,
        "data": data_text,
    })


def check_exhaustion(topic: str, data_pool: dict, topic_to_category: dict) -> dict:
    """APIを叩く前に、このトピックで新しいhook×data組み合わせが出せるか判定する。

    重複判定のルール（check_duplicate の判定3）を再現:
      hook類似度 >= 80% かつ data類似度 >= 50% → 重複
    つまり、同じhookでも異なるdataなら通る。
    ここでは「このトピックが生成しそうなhook」ごとに、
    dataプールの候補がブロックされているかを調べる。

    戻り値:
        {
            "is_exhausted": bool,       # True=スキップ推奨
            "reason": str,              # 判定理由
            "exhaustion_score": float,  # 0.0(余裕)〜1.0(完全枯渇)
            "blocked_combos": int,      # ブロックされた hook×data 組み合わせ数
            "total_combos": int,        # 候補 hook×data 組み合わせ数
            "max_retries": int,         # 推奨リトライ回数（0/1/通常）
        }
    """
    existing = _load_existing_scripts()
    if not existing:
        return {
            "is_exhausted": False, "reason": "",
            "exhaustion_score": 0.0, "blocked_combos": 0,
            "total_combos": 0, "max_retries": -1,
        }

    # 1. このトピックで使われそうなdataカテゴリを特定
    category = "長期"  # デフォルト
    for kw, cat in topic_to_category.items():
        if kw in topic:
            category = cat
            break
    pool = data_pool.get(category, data_pool.get("長期", []))

    # 2. このトピックが生成しそうなhookを推定
    #    トピック内のキーワードから、よく生成されるhookパターンを列挙
    likely_hooks = _estimate_likely_hooks(topic)

    # 3. 既存動画の hook→data マッピングを構築
    #    同じhookを持つ既存動画のdataリストを集める
    blocked_combos = 0
    total_combos = len(likely_hooks) * len(pool)

    if total_combos == 0:
        return {
            "is_exhausted": False, "reason": "",
            "exhaustion_score": 0.0, "blocked_combos": 0,
            "total_combos": 0, "max_retries": -1,
        }

    for hook_candidate in likely_hooks:
        # このhookに類似する既存動画を探す
        similar_existing_data = []
        for ex in existing:
            if _similarity(hook_candidate, ex["hook"]) >= HOOK_SIMILARITY_THRESHOLD:
                similar_existing_data.append(ex["data"])

        # このhookとペアになった既存dataで、プール内の候補がブロックされるか
        for data_candidate in pool:
            for ex_data in similar_existing_data:
                if _similarity(data_candidate, ex_data) >= 0.50:
                    blocked_combos += 1
                    break

    # 4. 枯渇度を計算
    available_combos = total_combos - blocked_combos
    exhaustion_score = blocked_combos / total_combos if total_combos > 0 else 0.0

    # 5. 判定
    if available_combos == 0:
        return {
            "is_exhausted": True,
            "reason": (f"hook×data完全枯渇: {category}カテゴリで"
                       f"{total_combos}組み合わせが全てブロック済み"),
            "exhaustion_score": exhaustion_score,
            "blocked_combos": blocked_combos,
            "total_combos": total_combos,
            "max_retries": 0,
        }
    if available_combos <= 2 and exhaustion_score >= 0.8:
        return {
            "is_exhausted": True,
            "reason": (f"枯渇度{exhaustion_score:.0%}: {category}カテゴリで"
                       f"未ブロック組み合わせ残り{available_combos}/{total_combos}"),
            "exhaustion_score": exhaustion_score,
            "blocked_combos": blocked_combos,
            "total_combos": total_combos,
            "max_retries": 0,
        }
    if available_combos <= 5 and exhaustion_score >= 0.5:
        return {
            "is_exhausted": False,
            "reason": (f"枯渇注意: {category}カテゴリで"
                       f"未ブロック組み合わせ残り{available_combos}/{total_combos}"),
            "exhaustion_score": exhaustion_score,
            "blocked_combos": blocked_combos,
            "total_combos": total_combos,
            "max_retries": 1,  # リトライ1回に制限
        }

    return {
        "is_exhausted": False, "reason": "",
        "exhaustion_score": exhaustion_score,
        "blocked_combos": blocked_combos,
        "total_combos": total_combos,
        "max_retries": -1,  # 通常（制限なし）
    }


# トピックキーワード → 生成されやすいhookパターン
_TOPIC_HOOK_MAP = {
    "焦": ["焦り", "焦る", "見たくない", "爆益"],
    "SNS": ["焦り", "焦る", "爆益", "見たくない"],
    "比較": ["焦り", "焦る", "見たくない", "マイナス"],
    "比べ": ["焦り", "見たくない"],
    "隣": ["焦り", "見たくない"],
    "同期": ["焦り", "焦る"],
    "仮想通貨": ["焦り", "爆益"],
    "レバ": ["焦り", "爆益"],
    "個別株": ["焦り", "見てしまった"],
    "FIRE": ["焦り", "焦る"],
    "YouTuber": ["焦り", "見たくない"],
    "含み損": ["含み損", "つらい", "マイナス"],
    "暴落": ["暴落", "怖い", "また下がった"],
    "下落": ["暴落", "怖い", "また下がった"],
    "積立": ["つらい", "増えない", "しんどい"],
    "配当": ["損してる", "後悔"],
    "退場": ["退場", "やめたい"],
    "不安": ["不安", "眠れない"],
    "売り": ["売りたい", "怖い"],
    "後悔": ["後悔", "つらい"],
    "NISA": ["不安", "焦る"],
    "iDeCo": ["不安", "焦る"],
    "損": ["損した", "つらい"],
    "疲れ": ["しんどい", "つらい", "増えない"],
}


def _estimate_likely_hooks(topic: str) -> list[str]:
    """トピックから、Claudeが生成しそうなhookパターンを推定する。"""
    hooks = set()
    for kw, patterns in _TOPIC_HOOK_MAP.items():
        if kw in topic:
            hooks.update(patterns)
    # マッチしなければ汎用hookを返す（判定を緩くする）
    if not hooks:
        hooks = {"不安", "つらい", "後悔"}
    return list(hooks)


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
