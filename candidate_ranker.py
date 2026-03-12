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
from typing import List

from script_gen import STRONG_HOOKS, WEAK_HOOKS, load_insights

# --- 閾値 ---
# 12点満点中、この点数以上なら採用
ACCEPT_THRESHOLD = 5

# --- テーマ別配点プロファイル ---
# 数字重視テーマ: タイトル数字3点、hook3点、data具体性2点（デフォルト）
# 感情重視テーマ: タイトル数字を1点ボーナスに変更、共感自然さ2点を追加
_EMOTION_THEMES = {"継続モチベ系", "積立疲れ系", "比較焦り系", "あるある"}

# --- 禁止表現（AGENTS.md由来の基本チェック） ---
BANNED_PHRASES = [
    "絶対に儲かる", "必ず上がる", "損しない", "元本保証",
    "今すぐ買え", "買わないと損", "100%",
]

# --- 数字検出パターン ---
_RE_NUMBER = re.compile(r"\d+[万億円%年ヶ月倍本]")

# --- トピックキーワード抽出パターン ---
# 数字+単位（1800万、72、3年 など）
_RE_TOPIC_NUMBER = re.compile(r"\d+[万億円%年ヶ月倍本歳]*")
# 英字の固有名詞（NISA、S&P500、ETF など）
_RE_TOPIC_PROPER = re.compile(r"[A-Za-z][A-Za-z0-9&]+(?:\d+)?")
# 漢字2文字以上のキーワード（複利、暴落、配当、新NISA など）
_RE_TOPIC_KANJI = re.compile(r"[一-龥ぁ-んァ-ヴー]{2,}")


def _extract_topic_keywords(topic: str) -> List[str]:
    """トピック文字列からキーワードを抽出する。"""
    keywords: List[str] = []
    # 数字+単位
    keywords.extend(_RE_TOPIC_NUMBER.findall(topic))
    # 英字固有名詞
    keywords.extend(_RE_TOPIC_PROPER.findall(topic))
    # 漢字キーワード（ストップワードを除外）
    stop_words = {"する", "ある", "いる", "なる", "できる", "こと", "もの", "ため", "とき",
                  "それ", "これ", "あれ", "その", "この", "での", "について", "として"}
    for m in _RE_TOPIC_KANJI.findall(topic):
        if m not in stop_words:
            keywords.append(m)
    # 空文字と1文字の数字のみを除外、重複排除（順序保持）
    seen: set = set()
    result: List[str] = []
    for kw in keywords:
        if len(kw) >= 2 and kw not in seen:
            seen.add(kw)
            result.append(kw)
    return result


def check_topic_match(script_data: dict) -> dict:
    """タイトルがトピックに関連しているかチェックする。

    戻り値:
        {
            "matches": bool,        # タイトルにトピックキーワードが含まれるか
            "topic_keywords": list,  # トピックから抽出したキーワード
            "found_in_title": list,  # タイトルで見つかったキーワード
            "score": int,           # -2 〜 +2
        }
    """
    topic = script_data.get("topic", "")
    title = script_data.get("title", "")

    topic_keywords = _extract_topic_keywords(topic)
    found_in_title = [kw for kw in topic_keywords if kw in title]

    if found_in_title:
        score = 2
        matches = True
    elif not topic_keywords:
        # トピックからキーワードが抽出できない場合はニュートラル
        score = 0
        matches = True
    else:
        # タイトルに具体的な数字や固有名詞が何かしらあるか
        has_any_specific = bool(_RE_NUMBER.search(title)) or bool(_RE_TOPIC_PROPER.search(title))
        if has_any_specific:
            score = 0
            matches = False
        else:
            # 完全に抽象的なタイトル
            score = -2
            matches = False

    return {
        "matches": matches,
        "topic_keywords": topic_keywords,
        "found_in_title": found_in_title,
        "score": score,
    }


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
    theme_name = script_data.get("theme_name", "")
    is_emotion_theme = theme_name in _EMOTION_THEMES

    # シーンをroleで引く
    scene_by_role = {}
    for s in scenes:
        role = s.get("role", "")
        if role:
            scene_by_role[role] = s

    hook_text = scene_by_role.get("hook", {}).get("text", "")
    data_text = scene_by_role.get("data", {}).get("text", "")
    empathy_text = scene_by_role.get("empathy", {}).get("text", "")

    checks = []
    warnings = []

    # ── チェック1: タイトルに具体的な数字があるか ──
    # 感情テーマ: max=1（ボーナス扱い）、数字テーマ: max=3（必須）
    title_num_max = 1 if is_emotion_theme else 3
    has_number = bool(_RE_NUMBER.search(title))
    prefer_numeric = title_rules.get("prefer_numeric_titles", True)
    if has_number:
        checks.append({
            "name": "タイトル数字",
            "score": title_num_max,
            "max": title_num_max,
            "reason": f"タイトルに具体的な数字あり{'（ボーナス）' if is_emotion_theme else ''}",
        })
    elif prefer_numeric and not is_emotion_theme:
        checks.append({
            "name": "タイトル数字",
            "score": 0,
            "max": title_num_max,
            "reason": "タイトルに数字なし（insights: 数字入りが推奨）",
        })
        warnings.append(f"タイトルに数字がありません:「{title}」")
    else:
        checks.append({
            "name": "タイトル数字",
            "score": 0,
            "max": title_num_max,
            "reason": f"タイトルに数字なし{'（感情テーマのため減点なし）' if is_emotion_theme else ''}",
        })

    # ── 感情テーマ追加: 共感自然さチェック（2点） ──
    if is_emotion_theme:
        empathy_score = 0
        empathy_reason = "empathyシーンなし"
        if empathy_text:
            # 共感フレーズ: 「あなた」「だけじゃない」「わかる」「つらい」系
            empathy_words = ["あなた", "だけじゃない", "わかる", "つらい", "不安",
                             "怖い", "焦る", "迷う", "疲れ", "しんどい"]
            has_empathy = any(w in empathy_text for w in empathy_words)
            if has_empathy:
                empathy_score = 2
                empathy_reason = f"共感フレーズあり:「{empathy_text[:20]}…」"
            else:
                empathy_score = 1
                empathy_reason = f"empathyあるが共感フレーズ弱:「{empathy_text[:20]}…」"
        checks.append({
            "name": "共感自然さ",
            "score": empathy_score,
            "max": 2,
            "reason": empathy_reason,
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

    # ── チェック3: dataに具体的な数字があるか ──
    # 感情テーマ: max=1（ボーナス）、数字テーマ: max=2（必須）
    data_num_max = 1 if is_emotion_theme else 2
    has_data_number = bool(_RE_NUMBER.search(data_text))
    if has_data_number:
        checks.append({
            "name": "data具体性",
            "score": data_num_max,
            "max": data_num_max,
            "reason": f"dataに具体的な数字あり{'（ボーナス）' if is_emotion_theme else ''}",
        })
    elif is_emotion_theme:
        checks.append({
            "name": "data具体性",
            "score": 0,
            "max": data_num_max,
            "reason": "dataに数字なし（感情テーマのため軽微）",
        })
    else:
        checks.append({
            "name": "data具体性",
            "score": 0,
            "max": data_num_max,
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

    # ── チェック5: タイトル−トピック一致（2点） ──
    topic_result = check_topic_match(script_data)
    topic_score = topic_result["score"]
    # スコアを 0〜2 の範囲にマッピング（内部は -2〜+2 だが合計計算用）
    clamped = max(0, topic_score)
    if topic_result["matches"]:
        checks.append({
            "name": "トピック一致",
            "score": clamped,
            "max": 2,
            "reason": f"トピックKW「{'、'.join(topic_result['found_in_title'])}」がタイトルに含まれる",
        })
    elif topic_score == -2:
        checks.append({
            "name": "トピック一致",
            "score": 0,
            "max": 2,
            "reason": f"タイトルが抽象的。トピックKW: {topic_result['topic_keywords']}",
        })
        warnings.append(
            f"タイトルがトピックと無関係の可能性:「{script_data.get('title', '')}」"
            f"（トピック: {script_data.get('topic', '')}）"
        )
    else:
        checks.append({
            "name": "トピック一致",
            "score": 0,
            "max": 2,
            "reason": f"トピックKWがタイトルに未検出（別の具体性あり）",
        })

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
