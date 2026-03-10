"""
candidate_ranker.py — 生成済み台本のスコアリング

台本生成後に品質チェックを行い、スコアが閾値未満なら再生成を促す。
analytics_insights.json のルールと、固定のコンテンツルールの両方でチェック。

使い方:
    from candidate_ranker import score_script, is_acceptable
    result = score_script(script_data)
    if not is_acceptable(result):
        # 再生成する
"""

from __future__ import annotations

import re

from script_gen import STRONG_HOOKS, WEAK_HOOKS, load_insights

# --- 閾値 ---
# 10点満点中、この点数以上なら採用
ACCEPT_THRESHOLD = 5

# --- 禁止表現（AGENTS.md由来の基本チェック） ---
BANNED_PHRASES = [
    "絶対に儲かる", "必ず上がる", "損しない", "元本保証",
    "今すぐ買え", "買わないと損", "100%",
]

# --- 数字検出パターン ---
_RE_NUMBER = re.compile(r"\d+[万億円%年ヶ月倍本]")


def score_script(script_data: dict) -> dict:
    """台本データをスコアリングする。

    戻り値:
        {
            "total_score": int,       # 合計スコア（0〜10）
            "checks": [               # 各チェック項目の詳細
                {"name": str, "score": int, "max": int, "reason": str},
                ...
            ],
            "warnings": [str],        # 警告メッセージ
        }
    """
    insights = load_insights()
    title_rules = insights.get("title_rules", {})
    strong_hooks_from_insights = insights.get("strong_hooks", [])
    weak_hooks_from_insights = insights.get("weak_hooks", [])

    title = script_data.get("title", "")
    scenes = script_data.get("scenes", [])

    # シーンをroleで引く
    scene_by_role = {}
    for s in scenes:
        role = s.get("role", "")
        if role:
            scene_by_role[role] = s

    hook_text = scene_by_role.get("hook", {}).get("text", "")
    data_text = scene_by_role.get("data", {}).get("text", "")

    checks = []
    warnings = []

    # ── チェック1: タイトルに具体的な数字があるか（3点） ──
    has_number = bool(_RE_NUMBER.search(title))
    prefer_numeric = title_rules.get("prefer_numeric_titles", True)
    if has_number:
        checks.append({
            "name": "タイトル数字",
            "score": 3,
            "max": 3,
            "reason": "タイトルに具体的な数字あり",
        })
    elif prefer_numeric:
        checks.append({
            "name": "タイトル数字",
            "score": 0,
            "max": 3,
            "reason": "タイトルに数字なし（insights: 数字入りが推奨）",
        })
        warnings.append(f"タイトルに数字がありません:「{title}」")
    else:
        checks.append({
            "name": "タイトル数字",
            "score": 1,
            "max": 3,
            "reason": "タイトルに数字なし（insights: 数字推奨なし）",
        })

    # ── チェック2: hookの強さ（3点） ──
    # insights の strong/weak + 固定リストを合算
    all_strong = set(STRONG_HOOKS + strong_hooks_from_insights)
    all_weak = set(WEAK_HOOKS + weak_hooks_from_insights)

    hook_clean = hook_text.rstrip("。？！ ")
    is_strong = any(w in hook_clean for w in all_strong)
    is_weak = any(w in hook_clean for w in all_weak) and not is_strong

    if is_strong:
        checks.append({
            "name": "hook強度",
            "score": 3,
            "max": 3,
            "reason": f"強hook:「{hook_clean}」",
        })
    elif is_weak:
        checks.append({
            "name": "hook強度",
            "score": 0,
            "max": 3,
            "reason": f"弱hook:「{hook_clean}」",
        })
        warnings.append(f"弱いhookです:「{hook_clean}」")
    else:
        checks.append({
            "name": "hook強度",
            "score": 1,
            "max": 3,
            "reason": f"hookの強弱不明:「{hook_clean}」",
        })

    # ── チェック3: dataに具体的な数字があるか（2点） ──
    has_data_number = bool(_RE_NUMBER.search(data_text))
    if has_data_number:
        checks.append({
            "name": "data具体性",
            "score": 2,
            "max": 2,
            "reason": "dataに具体的な数字あり",
        })
    else:
        checks.append({
            "name": "data具体性",
            "score": 0,
            "max": 2,
            "reason": f"dataに数字なし:「{data_text}」",
        })
        warnings.append(f"dataに具体的な数字がありません:「{data_text}」")

    # ── チェック4: 禁止表現チェック（2点、違反で0点） ──
    all_text = title + " " + " ".join(s.get("text", "") for s in scenes)
    found_banned = [p for p in BANNED_PHRASES if p in all_text]
    if not found_banned:
        checks.append({
            "name": "禁止表現",
            "score": 2,
            "max": 2,
            "reason": "禁止表現なし",
        })
    else:
        checks.append({
            "name": "禁止表現",
            "score": 0,
            "max": 2,
            "reason": f"禁止表現あり: {found_banned}",
        })
        warnings.append(f"禁止表現が含まれています: {found_banned}")

    total = sum(c["score"] for c in checks)
    return {
        "total_score": total,
        "max_score": sum(c["max"] for c in checks),
        "checks": checks,
        "warnings": warnings,
    }


def is_acceptable(result: dict) -> bool:
    """スコア結果が採用基準を満たすか判定する。"""
    return result["total_score"] >= ACCEPT_THRESHOLD


def format_report(result: dict) -> str:
    """スコア結果を人間が読める文字列にする。"""
    lines = [f"  [スコア] {result['total_score']}/{result['max_score']}点"]
    for c in result["checks"]:
        mark = "✓" if c["score"] == c["max"] else "△" if c["score"] > 0 else "✗"
        lines.append(f"    {mark} {c['name']}: {c['score']}/{c['max']} — {c['reason']}")
    if result["warnings"]:
        for w in result["warnings"]:
            lines.append(f"    ⚠ {w}")
    return "\n".join(lines)
