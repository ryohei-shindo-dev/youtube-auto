"""
scene_linter.py — シーンごとの品質チェック

各シーン（hook/empathy/data/resolve/closing）に特化したルールで
文脈破綻・意味不明・品質不足を検出する。

使い方:
    from scene_linter import lint_all_scenes, format_report
    issues = lint_all_scenes(script_data)
    if any(i["level"] == "error" for i in issues):
        print(format_report(issues))
"""
from __future__ import annotations

import re

# ── hookチェック用 ──
# メディア専門用語（単独hookだと視聴者に伝わらない）
_MEDIA_JARGON = {
    "退場", "相場", "指数", "分散", "配分", "金融",
    "PER", "PBR", "ボラティリティ", "複利", "遺言",
}

# 感情・痛みワード（hookに最低1つ欲しい）
_EMOTION_WORDS = {
    "含み損", "暴落", "売りたい", "不安", "怖い", "つらい", "眠れない",
    "後悔", "焦る", "損", "溶けた", "増えない", "待てない", "やめたい",
    "無理", "しんどい", "迷う", "疲れ", "揺れ", "崩れ",
    "下がった", "減って", "続かない", "見たくない",
}

# ── closingチェック用 ──
# 矛盾ワードペア（同一closing内に共存するとNG）
_CONTRADICTION_PAIRS = [
    ("退場", "ガチホ"),
    ("やめた", "続ける"),
    ("売った", "持ち続ける"),
    ("売却", "持ち続ける"),
    ("退場", "続ける"),
]

# 不完全文の末尾パターン
_INCOMPLETE_ENDINGS = re.compile(r"[、。]$|でも$|それでも$|けど$|だけど$")

# 助詞のみで終わるパターン（slide_text）
_PARTICLE_ENDING = re.compile(r"[はがをにでとも]$")

# 数字検出
_RE_NUMBER = re.compile(r"\d+[万億円%年ヶ月倍本歳]?")

# 感情テーマ（数字チェックを緩める）
_EMOTION_THEMES = {"継続モチベ系", "積立疲れ系", "比較焦り系", "あるある"}


def lint_all_scenes(script_data: dict) -> list[dict]:
    """transcript.json 全体をシーンごとにチェックする。"""
    issues: list[dict] = []
    scenes = script_data.get("scenes", [])
    theme_name = script_data.get("theme_name", "")

    for scene in scenes:
        role = scene.get("role", "")
        text = scene.get("text", "")
        slide_text = scene.get("slide_text", "")

        # 共通チェック
        issues.extend(_lint_slide_text(slide_text, role))

        # ロール別チェック
        if role == "hook":
            issues.extend(_lint_hook(text, slide_text))
        elif role == "empathy":
            issues.extend(_lint_empathy(text, slide_text))
        elif role == "data":
            issues.extend(_lint_data(text, slide_text, theme_name))
        elif role == "resolve":
            issues.extend(_lint_resolve(text, slide_text))
        elif role == "closing":
            issues.extend(_lint_closing(text, slide_text))

    return issues


def _lint_slide_text(slide_text: str, role: str) -> list[dict]:
    """slide_text の共通チェック。"""
    issues: list[dict] = []

    if not slide_text.strip():
        issues.append(_issue("error", role, "empty_slide",
                             "slide_text が空です"))
        return issues

    # 助詞のみで終わる（意味不明な切れ方）
    if _PARTICLE_ENDING.search(slide_text) and len(slide_text) > 3:
        issues.append(_issue("warning", role, "particle_ending",
                             f"slide_text が助詞で終わっています: 「{slide_text[-5:]}」"))

    return issues


def _lint_hook(text: str, slide_text: str) -> list[dict]:
    """hookシーンのチェック。"""
    issues: list[dict] = []
    clean = text.rstrip("。？！ ")

    # メディア専門用語だけで構成されていないか
    if clean in _MEDIA_JARGON:
        issues.append(_issue("error", "hook", "media_jargon_only",
                             f"hookがメディア用語のみ: 「{clean}」。初見の視聴者に伝わりません"))

    # 感情・痛みワードが含まれているか
    has_emotion = any(w in text for w in _EMOTION_WORDS)
    has_number = bool(_RE_NUMBER.search(text))
    if not has_emotion and not has_number:
        issues.append(_issue("warning", "hook", "no_emotion_or_number",
                             f"hookに感情ワードも数字もありません: 「{clean}」"))

    return issues


def _lint_empathy(text: str, slide_text: str) -> list[dict]:
    """empathyシーンのチェック。"""
    issues: list[dict] = []
    clean = text.rstrip("。？！ ")

    # 一語だけ（「あなたも。」等）
    if len(clean) <= 4:
        issues.append(_issue("error", "empathy", "too_short",
                             f"empathyが短すぎます（{len(clean)}文字）: 「{clean}」"))

    return issues


def _lint_data(text: str, slide_text: str, theme_name: str) -> list[dict]:
    """dataシーンのチェック。"""
    issues: list[dict] = []

    # 感情テーマ以外では数字が必要
    if theme_name not in _EMOTION_THEMES:
        if not _RE_NUMBER.search(text):
            issues.append(_issue("warning", "data", "no_number",
                                 f"dataに数字がありません: 「{text[:30]}」"))

    return issues


def _lint_resolve(text: str, slide_text: str) -> list[dict]:
    """resolveシーンのチェック。"""
    issues: list[dict] = []

    # 空チェック
    if not text.strip():
        issues.append(_issue("error", "resolve", "empty",
                             "resolveのテキストが空です"))
        return issues

    return issues


def _lint_closing(text: str, slide_text: str) -> list[dict]:
    """closingシーンのチェック。"""
    issues: list[dict] = []

    # 矛盾ワードペアの検出
    combined = text + " " + slide_text
    for word_a, word_b in _CONTRADICTION_PAIRS:
        if word_a in combined and word_b in combined:
            issues.append(_issue("error", "closing", "contradiction",
                                 f"closingに矛盾ワード: 「{word_a}」×「{word_b}」"))

    # 不完全文の検出（slide_text）
    if slide_text and _INCOMPLETE_ENDINGS.search(slide_text):
        issues.append(_issue("warning", "closing", "incomplete_slide",
                             f"closing slide_textが不完全: 「{slide_text}」"))

    # 「フォロー」がslide_textに残っていないか
    if "フォロー" in slide_text:
        issues.append(_issue("error", "closing", "raw_cta",
                             f"closing slide_textに生のフォロー誘導: 「{slide_text}」"))

    return issues


def _issue(level: str, scene: str, check: str, message: str) -> dict:
    return {"level": level, "scene": scene, "check": check, "message": message}


def format_report(issues: list[dict]) -> str:
    """レポートを人間が読める文字列に変換する。"""
    if not issues:
        return "シーンチェック: OK"
    errors = [i for i in issues if i["level"] == "error"]
    warnings = [i for i in issues if i["level"] == "warning"]
    lines = [f"シーンチェック: エラー{len(errors)}件, 警告{len(warnings)}件"]
    for issue in issues:
        mark = "❌" if issue["level"] == "error" else "⚠"
        lines.append(f"  {mark} [{issue['scene']}] {issue['message']}")
    return "\n".join(lines)
