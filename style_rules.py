"""
style_rules.py — 表記揺れの自動検出・修正

生成テキストの表記ルールを一元管理する。
AGENTS.md の Style Rules / Avoid Phrases が一次資料。

使い方:
    from style_rules import normalize_text, lint_text, lint_script
    text = normalize_text("月3万の積立")       # → "月3万の積み立て"
    issues = lint_text("絶対に儲かる")          # → [{"level": "error", ...}]
    issues = lint_script(script_data)           # → transcript.json 全体チェック
"""
from __future__ import annotations

import re

# ── 禁止表記 → 正しい表記（自動置換対象） ──
# 固有名詞（つみたてNISA、積立NISA等）は別途保護する
SPELLING_RULES: dict[str, str] = {
    "積立": "積み立て",
}

# 固有名詞パターン（自動置換をスキップする）
_PROPER_NOUNS = re.compile(
    r"つみたてNISA|積立NISA|iDeCo|確定拠出年金|積立投資信託"
)

# ── 禁止表現（正本。AGENTS.md Avoid Phrases と同期。他ファイルはここからimportする） ──
AVOID_PHRASES: list[str] = [
    "今が買い時",
    "この銘柄を買うべき",
    "絶対に儲かる",
    "誰でも勝てる",
    "これを知らないと損",
    "まだ買ってないのは危険",
    "短期で稼ぐ",
    "爆益確定",
    "必ず上がる",
    "損しない",
    "元本保証",
    "今すぐ買え",
    "買わないと損",
    "100%",
]

# ── hookで使うべきでないメディア専門用語（単独使用時のみ検出） ──
MEDIA_JARGON: list[str] = [
    "退場",
    "相場",
    "指数",
    "分散",
    "配分",
    "金融",
    "PER",
    "PBR",
    "ボラティリティ",
]


def normalize_text(text: str) -> str:
    """表記揺れを自動修正する。固有名詞は保護。"""
    if not isinstance(text, str):
        return text

    # 固有名詞をプレースホルダに退避
    placeholders: dict[str, str] = {}
    for i, m in enumerate(_PROPER_NOUNS.finditer(text)):
        ph = f"\ue100{i}"
        placeholders[ph] = m.group()
        text = text.replace(m.group(), ph, 1)

    # 置換ルール適用
    for wrong, correct in SPELLING_RULES.items():
        text = text.replace(wrong, correct)

    # プレースホルダを復元
    for ph, original in placeholders.items():
        text = text.replace(ph, original)

    return text


def lint_text(text: str, field: str = "") -> list[dict]:
    """テキストの表記違反を検出する（修正はしない）。

    Returns:
        [{"level": "error"|"warning", "field": field, "found": str,
          "suggestion": str, "rule": str}, ...]
    """
    if not isinstance(text, str):
        return []

    issues: list[dict] = []

    # 表記揺れチェック（固有名詞を除外してからチェック）
    cleaned = _PROPER_NOUNS.sub("", text)
    for wrong, correct in SPELLING_RULES.items():
        if wrong in cleaned:
            issues.append({
                "level": "error",
                "field": field,
                "found": wrong,
                "suggestion": correct,
                "rule": "spelling",
            })

    # 禁止表現チェック
    for phrase in AVOID_PHRASES:
        if phrase in text:
            issues.append({
                "level": "error",
                "field": field,
                "found": phrase,
                "suggestion": "削除または言い換え",
                "rule": "avoid_phrase",
            })

    return issues


def lint_script(script_data: dict) -> list[dict]:
    """transcript.json 全体の表記チェック。"""
    issues: list[dict] = []

    # タイトル・トピック
    for key in ("title", "description", "topic"):
        val = script_data.get(key, "")
        if isinstance(val, str):
            issues.extend(lint_text(val, field=key))

    # 各シーン
    for scene in script_data.get("scenes", []):
        role = scene.get("role", "unknown")
        for key in ("text", "slide_text"):
            val = scene.get(key, "")
            if isinstance(val, str):
                issues.extend(lint_text(val, field=f"{role}.{key}"))

    return issues


def format_report(issues: list[dict]) -> str:
    """違反レポートを人間が読める文字列に変換する。"""
    if not issues:
        return "表記チェック: OK"
    lines = [f"表記チェック: {len(issues)}件の問題"]
    for issue in issues:
        level = "❌" if issue["level"] == "error" else "⚠"
        lines.append(
            f"  {level} [{issue['rule']}] {issue['field']}: "
            f"「{issue['found']}」→「{issue['suggestion']}」"
        )
    return "\n".join(lines)
