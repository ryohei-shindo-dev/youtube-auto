"""
script_gen.py
Claude API で YouTube 用の台本を生成するモジュール。

チャンネル: ガチホのモチベ
コンセプト: 長期投資の継続モチベーション提供

【固定フレーズ】
  挨拶: 「今日もガチホしてますか？」
  結論: 5パターンからランダム選択
  CTA: 「明日もガチホしたい人はチャンネル登録お願いします。」

【Shorts台本構成（5シーン、16〜18秒目標17秒）】
  感情曲線: 不安で掴む → 共感 → データで安心 → 断言・希望 → CTA
  1. hook（3秒）     — 不安ワードで掴む（最初の1.5秒が勝負）
  2. empathy（4秒）  — 共感 + 挨拶「今日もガチホしてますか？」
  3. data（5秒）     — 具体的な数字1つだけ
  4. resolve（4秒）  — 断言フレーズ + 結論
  5. closing（2秒）  — CTA固定

【通常動画台本構成（6シーン、約5分）】
  1. opening（30秒）  — 導入「今日もガチホしてますか？」
  2. theme（30秒）    — 今日のテーマ
  3. data（90秒）     — データ・歴史・格言
  4. explain（90秒）  — 解説
  5. summary（30秒）  — まとめ
  6. closing（30秒）  — 締め

【Shortsテーマローテーション（月〜金）】
  月: メリット / 火: 格言 / 水: あるある / 木: 歴史データ / 金: ガチホモチベ
"""

from __future__ import annotations

import json
import os
import pathlib
import random
import re

import anthropic

import api_usage_log

from script_config import (  # noqa: F401 — 定数・テンプレート
    _MODEL_HAIKU, _MODEL_SONNET, SCRIPT_MODEL, _THEME_MODEL_MAP,
    INSIGHTS_FILE, CHANNEL_CONCEPT,
    OPENING_PHRASES, OPENING_PHRASE, _SHORTS_OPENING_RATIO, _SHORTS_CTA_RATIO,
    CLOSING_PHRASES_LIST, _CLOSING_NO_CTA, CLOSING_PHRASE, CLOSING_SLIDE_TEXTS,
    _LOOP_CLOSING_ANXIETY, _LOOP_CLOSING_COMPARISON, _LOOP_CLOSING_STAGNATION,
    _LOOP_CLOSING_CRASH, _LOOP_CLOSING_RESTRAIN, _LOOP_CLOSING_COMMON,
    _THEME_CLOSING_MAP, _HOOK_TYPE_KEYWORDS,
    _RESOLVE_CONTINUE, _RESOLVE_TIME, _RESOLVE_CALM,
    _RESOLVE_CRASH, _RESOLVE_COMPARE, _RESOLVE_RESTRAIN,
    CONCLUSION_PHRASES, _THEME_RESOLVE_MAP, _resolve_texts,
    SHORTS_THEMES, WEEKDAY_THEME,
    SHORTS_TEMPLATE, LONG_TEMPLATE,
    DATA_POOL, _TOPIC_TO_CATEGORY,
    _CRASH_WORDS, _EXIT_WORDS, _TIME_WORDS, _PSYCH_WORDS,
    _COMPARE_WORDS, _POSITIVE_WORDS, _SURPRISE_WORDS, _CONTINUATION_WORDS,
    STRONG_HOOKS, WEAK_HOOKS, _TOPIC_PAIN_MAP, _EXAGGERATION_FIXES,
    _RESOLVE_SLIDE_MAP,
    _RESOLVE_HISTORY_PATH, _RESOLVE_HISTORY_KEEP, _RESOLVE_TAG_HISTORY_KEEP,
)




def get_model_for_theme(theme: str) -> str:
    """テーマに応じたモデルを返す。環境変数で上書きされている場合はそちらを優先。"""
    if os.getenv("SCRIPT_MODEL"):
        return SCRIPT_MODEL
    return _THEME_MODEL_MAP.get(theme, SCRIPT_MODEL)

# --- 分析結果の読み込み ---

def load_insights() -> dict:
    """analytics_insights.json を読み込む。ファイルがなければ空辞書。"""
    try:
        with open(INSIGHTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _build_insights_block(insights: dict) -> str:
    """insights辞書からプロンプトに差し込む文字列を生成する。"""
    guidance = insights.get("prompt_guidance", [])
    if not guidance:
        return ""

    meta = insights.get("meta", {})
    confidence = meta.get("confidence", "unknown")
    sample = meta.get("sample_size", 0)

    lines = [
        f"\n━━━ チャンネル分析からの学習結果（{sample}本分析、信頼度: {confidence}） ━━━",
        "以下は過去の動画データから自動抽出されたルール。従え。",
    ]
    for g in guidance:
        lines.append(f"- {g}")
    lines.append("━━━")
    return "\n".join(lines)

# チャンネル設定

def _classify_hook_type(hook: str) -> str:
    """hookの感情タイプを判定する。"""
    for hook_type, keywords in _HOOK_TYPE_KEYWORDS.items():
        if any(kw in hook for kw in keywords):
            return hook_type
    return "anxiety"  # デフォルトは焦り系


_HOOK_TYPE_TO_CLOSINGS = {
    "restrain": _LOOP_CLOSING_RESTRAIN,
    "crash": _LOOP_CLOSING_CRASH,
    "comparison": _LOOP_CLOSING_COMPARISON,
    "stagnation": _LOOP_CLOSING_STAGNATION,
    "anxiety": _LOOP_CLOSING_ANXIETY,
}


def _pick_loop_closing(hook: str, theme_name: str = "",
                       resolve_tag: str = "") -> tuple[str, str]:
    """hookの感情タイプ・テーマに応じてclosing余韻句を選択する。

    resolve_tag が指定されている場合、同じ意味タグのclosingを避ける
    （resolveは意味、closingは余韻。同じ意味が重なると冗長になるため）。
    """
    # テーマ名で直接マッチすればそれを優先
    if theme_name in _THEME_CLOSING_MAP:
        pool = _THEME_CLOSING_MAP[theme_name] + _LOOP_CLOSING_COMMON
    else:
        # hookキーワードから感情タイプを判定
        hook_type = _classify_hook_type(hook)
        pool = _HOOK_TYPE_TO_CLOSINGS[hook_type] + _LOOP_CLOSING_COMMON

    # resolve と同じ意味タグのclosingを避ける
    if resolve_tag:
        distant = [c for c in pool if len(c) < 3 or c[2] != resolve_tag]
        if distant:
            pool = distant

    chosen = random.choice(pool)
    # 3要素タプル (text, slide, tag) → (text, slide) を返す
    return (chosen[0], chosen[1])


def _apply_loop_closing(scenes: list, hook_word: str, theme_name: str = "",
                        resolve_tag: str = "") -> tuple:
    """hookの感情タイプからclosing余韻句を生成してscenesに反映する。"""
    closing, closing_slide = _pick_loop_closing(hook_word, theme_name, resolve_tag)
    # 4本に1本だけ弱いCTAを付加
    if random.random() < _SHORTS_CTA_RATIO:
        cta = random.choice(CLOSING_PHRASES_LIST)
        closing = closing.rstrip("。") + "。" + cta
    for s in scenes:
        if s.get("role") == "closing":
            s["text"] = closing
            s["slide_text"] = _strip_terminal_punctuation(closing_slide)
            break
    return closing, closing_slide




def _strip_terminal_punctuation(text: str) -> str:
    """画面テキスト末尾の句点類を落として見出しとして整える。"""
    return text.rstrip("。.!！?？ ").strip()


# 絵文字除去用の正規表現（サロゲートペア・記号・修飾子を除去）
_RE_EMOJI = re.compile(r'[\U00010000-\U0010FFFF\u2600-\u27BF\uFE00-\uFE0F\u200D]')


def _clean_slide_text(text: str) -> str:
    """slide_text から絵文字を除去し、末尾句読点を落とす。"""
    return _strip_terminal_punctuation(_RE_EMOJI.sub('', text).strip())


_SLIDE_CONNECTOR_PREFIXES = (
    "だからこそ、", "そう考えると、", "それでもなお、",
    "やっぱり、", "だから、", "つまり、", "結局、", "そう、", "となると、",
    "だからこそ", "そう考えると", "それでもなお",
    "やっぱり", "だから", "つまり", "結局", "そう", "となると",
)


def _strip_slide_connector(text: str) -> str:
    """スライド表示では不要な接続詞を落とす。"""
    for prefix in _SLIDE_CONNECTOR_PREFIXES:
        if text.startswith(prefix):
            return text[len(prefix):].lstrip()
    return text


# 日本語の危険な末尾パターン（意味が途中で切れてしまう語尾）
# endswith() で判定するため並び順は動作に影響しない
_DANGLING_ENDINGS = (
    # 3文字
    "たくな", "でき", "まし", "ませ", "され", "して", "なけ",
    # 2文字
    "てい", "でい", "から", "かも", "だろ", "ない",
    # 1文字: 促音・拗音
    "っ", "ッ", "ゃ", "ゅ", "ょ", "ャ", "ュ", "ョ",
    # 1文字: 活用語尾
    "し", "き", "ぎ", "み", "り", "ち", "び",
    "な", "れ", "い", "て", "ま", "ら", "け",
)
# 安全な切れ目になれる文字（助詞・句読点）
# 「で」「に」は助詞としても活用語尾としても使われるため除外
_SAFE_BREAK_CHARS = set("はがをのもへとや、，")


def _ends_dangling(text: str) -> bool:
    """テキスト末尾が日本語として不自然な途中切れかどうかを判定する。"""
    return any(text.endswith(e) for e in _DANGLING_ENDINGS)


def _safe_truncate_slide_text(text: str, max_len: int = 14, max_extra: int = 3) -> str:
    """日本語として不自然な途中切れを防ぐ安全な切り詰め。

    1. max_len で切る
    2. 数字の途中切れを保護
    3. 危険な末尾パターンに該当する場合:
       a. まず +max_extra 文字まで延長して安全な切れ目を探す
       b. 見つからなければ手前の安全な切れ目まで戻す
    """
    if len(text) <= max_len:
        return text

    truncated = text[:max_len]
    rest = text[max_len:]

    # 数字の途中切れ保護
    if truncated and truncated[-1].isdigit():
        m = re.match(r"(\d*[万億千百兆円%％年月日本倍回件人]?[後前目間分]?)", rest)
        if m and m.group(1):
            truncated += m.group(1)
            return truncated

    if not _ends_dangling(truncated):
        return truncated

    # 戦略A: 前方に最大 max_extra 文字延長して安全な切れ目を探す
    for i in range(1, min(max_extra + 1, len(rest) + 1)):
        candidate = text[:max_len + i]
        if not _ends_dangling(candidate):
            return candidate

    # 戦略B: 手前の安全な切れ目まで戻す
    for i in range(len(truncated) - 1, max(0, max_len - 6), -1):
        if truncated[i] in _SAFE_BREAK_CHARS:
            return truncated[:i + 1].rstrip("、，")
        if i > 0 and truncated[i - 1] in _SAFE_BREAK_CHARS:
            return truncated[:i]

    # どちらも失敗 → 延長した結果をそのまま使う
    return text[:max_len + max_extra] if len(text) > max_len + max_extra else text


def _single_sentence_slide_text(text: str, max_len: int = 14) -> str:
    """スライド表示用に1センテンスへ圧縮する。"""
    text = _strip_slide_connector(_clean_slide_text(text))
    parts = re.split(r"[。!?！？]+", text, maxsplit=1)
    text = parts[0].strip() if parts and parts[0].strip() else text
    return _clean_slide_text(_safe_truncate_slide_text(text, max_len))



def _resolve_slide_from_conclusion(conclusion: str) -> str:
    """resolve の表示テキストは意味を保った短い要約を返す。"""
    cleaned = _strip_slide_connector(_clean_slide_text(conclusion))
    for key, value in _RESOLVE_SLIDE_MAP.items():
        if key in cleaned:
            return value
    return _single_sentence_slide_text(cleaned, max_len=12)


def _closing_slide_from_text(text: str) -> str:
    """closing の表示テキストは短い固定CTAに寄せる。"""
    if "コメント" in text:
        return "同じ人いる？"
    if "フォロー" in text or "持つ" in text or "続けよう" in text:
        return "続けてますか"
    return "続けてますか"


def _trim_to_first_sentence(text: str, max_len: int) -> str:
    """テキストを最初の文（句点区切り）で切り詰める。句点がなければmax_lenで切る。"""
    if len(text) <= max_len:
        return text
    parts = re.split(r"(?<=[。？！])", text)
    first = parts[0].rstrip("。、 ") if parts[0] else ""
    # 最初の文が収まるならそれを使う
    if first and len(first) <= max_len:
        return first
    # 最初の文が長すぎる場合、読点で区切って収まる部分を返す
    if first:
        comma_parts = re.split(r"(?<=[、])", first)
        built = ""
        for cp in comma_parts:
            if len(built + cp) <= max_len:
                built += cp
            else:
                break
        if built:
            return built.rstrip("、 ")
    return text[:max_len]



def _load_resolve_history() -> list[dict]:
    """直近使用済みresolve履歴を読み込む。各要素は {"text": ..., "tag": ...}。

    旧形式（文字列リスト）にも対応する。
    """
    try:
        data = json.loads(_RESOLVE_HISTORY_PATH.read_text())[-_RESOLVE_HISTORY_KEEP:]
        # 旧形式互換: 文字列→dict変換
        return [
            d if isinstance(d, dict) else {"text": d, "tag": ""}
            for d in data
        ]
    except Exception:
        return []


def _save_resolve_history(history: list[dict], new_text: str, new_tag: str) -> None:
    """resolveフレーズの使用履歴を保存する。"""
    history.append({"text": new_text, "tag": new_tag})
    history = history[-_RESOLVE_HISTORY_KEEP:]
    _RESOLVE_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _RESOLVE_HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2))


def _select_conclusion_and_connector(data_text: str, theme_name: str = "") -> tuple:
    """dataの内容とテーマに最も合う結論フレーズと接続詞を選択する。

    まず data 内容から resolve カテゴリを判定し、
    判定不能な場合のみテーマの既定カテゴリにフォールバックする。
    直近使用済みフレーズ + 直近3本の同義タグを避ける。
    """
    data_text = data_text or ""

    if any(word in data_text for word in _COMPARE_WORDS):
        resolve_pool = _RESOLVE_COMPARE
    elif any(word in data_text for word in _EXIT_WORDS + _PSYCH_WORDS):
        resolve_pool = _RESOLVE_CALM
    elif any(word in data_text for word in _CRASH_WORDS):
        resolve_pool = _RESOLVE_CRASH
    elif any(word in data_text for word in _CONTINUATION_WORDS):
        resolve_pool = _RESOLVE_CONTINUE
    elif any(word in data_text for word in _TIME_WORDS + _POSITIVE_WORDS + _SURPRISE_WORDS):
        resolve_pool = _RESOLVE_TIME
    else:
        resolve_pool = _THEME_RESOLVE_MAP.get(theme_name, None)

    # タプル形式のプール → (text, tag) のリスト
    if resolve_pool and isinstance(resolve_pool[0], tuple):
        tagged_pool = resolve_pool
    else:
        # フォールバック: CONCLUSION_PHRASES（文字列リスト）から全タプルプールへ
        tagged_pool = (
            _RESOLVE_CONTINUE + _RESOLVE_TIME + _RESOLVE_CALM
            + _RESOLVE_CRASH + _RESOLVE_COMPARE + _RESOLVE_RESTRAIN
        )

    history = _load_resolve_history()
    used_texts = {h["text"] for h in history}
    recent_tags = {h["tag"] for h in history[-_RESOLVE_TAG_HISTORY_KEEP:] if h.get("tag")}

    # 優先: 同一フレーズも同義タグも避ける
    best = [t for t in tagged_pool if t[0] not in used_texts and t[1] not in recent_tags]
    if not best:
        # 次善: 同一フレーズだけ避ける（タグ重複は許容）
        best = [t for t in tagged_pool if t[0] not in used_texts]
    if not best:
        # 最終手段: 全候補からランダム
        best = list(tagged_pool)

    chosen = random.choice(best)
    conclusion, tag = chosen[0], chosen[1]
    _save_resolve_history(history, conclusion, tag)

    # 接続詞は付けない（シーン切替で間があるため、接続詞なしが自然）
    connector = ""

    return conclusion, connector, tag


def extract_scene_texts(script_data: dict, *roles: str) -> dict:
    """台本データから指定ロールのslide_textを辞書で返すヘルパー。

    使用例:
        texts = extract_scene_texts(script_data, "hook", "resolve")
        hook_text = texts.get("hook", "")
    """
    result = {r: "" for r in roles}
    for scene in script_data.get("scenes", []):
        role = scene.get("role", "")
        if role in result:
            result[role] = scene.get("slide_text", "")
    return result


def normalize_preferred_spelling(text: str) -> str:
    """ブランド表記の揺れを正規化する。style_rules に委譲。"""
    from style_rules import normalize_text
    return normalize_text(text)


def normalize_script_spelling(script_data: dict) -> dict:
    """台本内のユーザー向け文言を表記ルールに合わせて正規化する。"""
    for key in ("title", "description", "topic"):
        if key in script_data and isinstance(script_data[key], str):
            script_data[key] = normalize_preferred_spelling(script_data[key])

    for scene in script_data.get("scenes", []):
        for key in ("text", "slide_text"):
            if key in scene and isinstance(scene[key], str):
                scene[key] = normalize_preferred_spelling(scene[key])

    if isinstance(script_data.get("tags"), list):
        script_data["tags"] = [
            normalize_preferred_spelling(tag) if isinstance(tag, str) else tag
            for tag in script_data["tags"]
        ]

    return script_data


def _build_shorts_vars(theme: str) -> dict:
    """Shorts生成用の固定変数（opening, conclusion, closing等）をセットアップする。"""
    theme_desc = SHORTS_THEMES.get(theme, SHORTS_THEMES["ガチホモチベ"])
    # 語りかけフレーズ: 約3本に1本だけ入れる（尺圧迫を避ける）
    if random.random() < _SHORTS_OPENING_RATIO:
        opening = random.choice(OPENING_PHRASES)
        print(f"  [語りかけ] この動画にフレーズを入れます:「{opening}」")
    else:
        opening = ""
    conclusion = random.choice(CONCLUSION_PHRASES)  # 初期値（ポスプロで上書き）
    closing_idx = random.randrange(len(CLOSING_PHRASES_LIST))
    return {
        "theme_name": theme,
        "theme_desc": theme_desc,
        "opening": opening,
        "conclusion": conclusion,
        "closing": CLOSING_PHRASES_LIST[closing_idx],
        "closing_slide": CLOSING_SLIDE_TEXTS[closing_idx],
    }


def generate_shorts_script(topic: str, theme: str = "ガチホモチベ") -> dict:
    """Shorts用台本（5シーン、16〜18秒）を生成する。"""
    return _generate_script(
        topic,
        SHORTS_TEMPLATE,
        expected_scenes=5,
        extra_vars=_build_shorts_vars(theme),
    )


def generate_shorts_candidates(
    topic: str, theme: str = "ガチホモチベ", count: int = 3,
    prohibited_hooks: list = None,
) -> list:
    """1回のAPI呼び出しでcount個のShorts台本候補を生成する。

    コスト削減用: 従来は1候補ずつAPI呼び出し→リトライだったが、
    1回のAPI呼び出しで複数候補を取得し、ローカルでスコアリングして最良を選ぶ。

    prohibited_hooks: 同一バッチで既に使用済みのhookテキスト一覧。
                      プロンプトに「これらのhookは使用禁止」として注入する。

    戻り値: list[dict]（各要素は generate_shorts_script と同じ形式の台本）
    """
    result = _generate_script(
        topic,
        SHORTS_TEMPLATE,
        expected_scenes=5,
        extra_vars=_build_shorts_vars(theme),
        num_candidates=count,
        prohibited_hooks=prohibited_hooks,
    )
    if isinstance(result, dict):
        # 単一候補が返った場合（パース失敗時のフォールバック）
        return [result] if result else []
    return result


def generate_long_script(topic: str) -> dict:
    """通常動画用台本（6シーン、約5分）を生成する。"""
    opening = random.choice(OPENING_PHRASES)
    conclusion = random.choice(CONCLUSION_PHRASES)
    return _generate_script(
        topic,
        LONG_TEMPLATE,
        expected_scenes=6,
        extra_vars={"opening": opening, "conclusion": conclusion},
    )


def _generate_script(
    topic: str,
    template: str,
    expected_scenes: int,
    extra_vars: dict = None,
    num_candidates: int = 1,
    prohibited_hooks: list = None,
) -> dict | list:
    """Claude API で台本を生成する共通関数。

    num_candidates=1: 従来通り dict を返す
    num_candidates>1: 候補リスト list[dict] を返す（1回のAPIで複数生成）
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("  [エラー] ANTHROPIC_API_KEY が設定されていません。")
        return {} if num_candidates == 1 else []

    try:
        client = anthropic.Anthropic(api_key=api_key)
        fmt_vars = {
            "concept": CHANNEL_CONCEPT,
            "topic": topic,
            "opening": OPENING_PHRASE,
            "conclusion": CONCLUSION_PHRASES[0],
            "closing": CLOSING_PHRASE,
        }
        if extra_vars:
            fmt_vars.update(extra_vars)

        conclusion = fmt_vars["conclusion"]
        opening = fmt_vars["opening"]
        closing = fmt_vars["closing"]
        closing_slide = fmt_vars.get("closing_slide", "明日もガチホしたい人はフォロー")
        prompt = template.format(**fmt_vars)

        # 分析 insights をプロンプト先頭に差し込む
        insights = load_insights()
        insights_block = _build_insights_block(insights)
        if insights_block:
            prompt = insights_block + "\n\n" + prompt
            print(f"  [insights] 分析結果を差し込み（{insights.get('meta', {}).get('sample_size', 0)}本）")

        # プロンプトキャッシュ: 固定テンプレート部分を system に分離
        system_text = prompt
        if num_candidates > 1:
            # 禁止hookステム注入
            prohibited_block = ""
            if prohibited_hooks:
                stems = list(dict.fromkeys(prohibited_hooks))[:15]  # 最大15個
                prohibited_block = (
                    f"\n【禁止hookワード（同一バッチで使用済み。これらと同じ・類似のhookは絶対に使わないこと）】\n"
                    + "\n".join(f"- 「{h}」" for h in stems)
                    + "\n"
                )
            user_text = (
                f"トピック「{topic}」の台本を{num_candidates}パターン生成してください。\n"
                f"それぞれ異なるhookワードとdataを使うこと（同じhookやdataの使い回し禁止）。\n\n"
                f"【重要: 各候補の切り口を明確に変えること】\n"
                f"- 候補A: 数字先頭型（hookの1語目に具体的な数字を置く。例:「1800万円」「20年」）\n"
                f"- 候補B: 感情先頭型（hookの1語目に感情・痛みワードを置く。例:「含み損」「不安」）\n"
                f"- 候補C: 後悔先頭型（hookの1語目に後悔・行動ワードを置く。例:「売った人」「やめた人」）\n"
                f"{prohibited_block}\n"
                f"JSON配列で出力: [{num_candidates}個のJSON]"
            )
            max_tokens = 1500 * num_candidates
        else:
            user_text = f"トピック「{topic}」の台本をJSON形式で生成してください。"
            max_tokens = 2000

        # テーマ別モデルルーティング
        theme_name = fmt_vars.get("theme_name", "")
        model = get_model_for_theme(theme_name)

        print(f"  Claude API で台本を生成中（トピック: {topic}、候補数: {num_candidates}）...")
        print(f"  挨拶: {opening} / 結論: {conclusion}")
        print(f"  モデル: {model}（テーマ: {theme_name}）")
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[{
                "type": "text",
                "text": system_text,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user_text}],
        )
        api_usage_log.log_usage(
            message, model=model, endpoint="script_gen",
            topic=topic, theme=theme_name,
            num_candidates=num_candidates,
        )
        raw = message.content[0].text.strip()
        # マークダウンのコードブロック装飾を除去
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```\s*$", "", raw)

        # JSON を抽出
        if num_candidates > 1:
            # JSON配列を探す（貪欲マッチで配列全体をキャプチャ）
            m = re.search(r"\[\s*\{[\s\S]*\}\s*\]", raw)
            if not m:
                # 配列が見つからなければ単一JSONとして処理
                m = re.search(r"\{[\s\S]*\}", raw)
                if not m:
                    print("  [エラー] JSON形式のレスポンスが見つかりませんでした。")
                    _save_debug("script_raw_response.txt", raw)
                    return []
                candidates_raw = [json.loads(m.group())]
            else:
                candidates_raw = json.loads(m.group())
                if not isinstance(candidates_raw, list):
                    candidates_raw = [candidates_raw]
        else:
            m = re.search(r"\{[\s\S]*\}", raw)
            if not m:
                print("  [エラー] JSON形式のレスポンスが見つかりませんでした。")
                _save_debug("script_raw_response.txt", raw)
                return {}
            candidates_raw = [json.loads(m.group())]

        # 各候補をポスト処理
        results = []
        for ci, data in enumerate(candidates_raw):
            if num_candidates > 1:
                print(f"\n  --- 候補 {ci+1}/{len(candidates_raw)} ---")
            result = _postprocess_script(
                data, topic, fmt_vars, expected_scenes,
            )
            if result:
                results.append(result)

        if num_candidates == 1:
            return results[0] if results else {}
        return results

    except json.JSONDecodeError as e:
        print(f"  [エラー] JSONパースに失敗しました: {e}")
        _save_debug("script_json_error.txt", raw)
        return {} if num_candidates == 1 else []
    except Exception as e:
        print(f"  [エラー] 台本生成中にエラーが発生しました: {e}")
        return {} if num_candidates == 1 else []


def _postprocess_script(
    data: dict,
    topic: str,
    fmt_vars: dict,
    expected_scenes: int,
) -> dict:
    """Claude が返した生JSON を整形・修正・バリデーションして完成台本にする。

    戻り値: 整形済み台本 dict。失敗時は空の {}。
    """
    opening = fmt_vars.get("opening", "")
    conclusion = fmt_vars.get("conclusion", CONCLUSION_PHRASES[0])
    closing = fmt_vars.get("closing", CLOSING_PHRASE)
    closing_slide = fmt_vars.get("closing_slide", "明日もガチホしたい人はフォロー")

    # 固定テキストを強制適用（Claudeが指示に従わなくても上書き）
    scenes = data.get("scenes", [])

    # ── ループ再生: hookワードを取得してclosingに埋め込む ──
    hook_word = ""
    for s in scenes:
        if s.get("role") == "hook":
            hook_word = s.get("text", "").rstrip("。？！ ")
            break
    if hook_word:
        closing, closing_slide = _apply_loop_closing(scenes, hook_word, fmt_vars.get("theme_name", ""))
        print(f"  [ループ再生] closing にhookワード埋め込み:「{closing_slide}」")

    for s in scenes:
        role = s.get("role", "")
        if role == "empathy":
            if opening:
                # 語りかけフレーズあり → slide_textに表示、ナレーションにも含める
                s["slide_text"] = opening
                if opening not in s.get("text", ""):
                    s["text"] = s.get("text", "").rstrip("。") + "。" + opening
            else:
                # 語りかけなし → ナレーションからslide_textを生成（絵文字防止）
                raw = s.get("text", "").rstrip("。？！ ")
                s["slide_text"] = _safe_truncate_slide_text(raw, max_len=10)
        elif role == "opening":
            # 通常動画用: openingのslide_textを固定
            s["slide_text"] = OPENING_PHRASE
        elif role == "resolve":
            # resolveの整形は文字数制限ループ内で実施（data内容を見て結論を選択）
            pass
        elif role == "closing":
            s["slide_text"] = _closing_slide_from_text(closing)
            s["text"] = closing

        if "slide_text" in s:
            s["slide_text"] = _clean_slide_text(s.get("slide_text", ""))

    # 文字数制限チェック
    # 固定フレーズを保護しながら AI生成部分を切り詰める
    strict_limits = {"hook": 18, "data": 22}
    # data_text をループ前に1回だけ取得（resolve等で使用）
    data_text = next((s.get("text", "") for s in scenes if s.get("role") == "data"), "")
    for s in scenes:
        role = s.get("role", "")
        text = s.get("text", "")

        if role == "hook":
            # hookの痛みワードチェック: 弱いhookを検出して警告
            hook_text = text.rstrip("。？！ ")
            if any(w in hook_text for w in WEAK_HOOKS) and not any(w in hook_text for w in STRONG_HOOKS):
                replaced = False
                for kw, replacement in _TOPIC_PAIN_MAP.items():
                    if kw in topic:
                        print(f"  [修正] hookが弱い「{hook_text}」→「{replacement}」に変更")
                        s["text"] = replacement
                        s["slide_text"] = _strip_terminal_punctuation(replacement)
                        text = replacement
                        replaced = True
                        break
                if not replaced:
                    print(f"  [警告] hookが弱い可能性:「{hook_text}」")
            # ループ再生: hook修正後のワードでclosingを再更新
            new_hook = text.rstrip("。？！ ")
            if new_hook and new_hook != hook_word:
                hook_word = new_hook
                closing, closing_slide = _apply_loop_closing(scenes, hook_word)
                print(f"  [ループ再生] hook修正に合わせてclosing更新:「{closing_slide}」")

        if role == "data":
            # 誇張表現を正確な表現に自動置換
            for bad, good in _EXAGGERATION_FIXES.items():
                if bad in text:
                    old_text = text
                    text = text.replace(bad, good)
                    s["text"] = text
                    s["slide_text"] = _single_sentence_slide_text(good)
                    print(f"  [修正] data誇張表現を修正:「{old_text.rstrip('。')}」→「{text.rstrip('。')}」")
                    data_text = text  # resolve用に更新
                    break

        if role == "data" and len(text) > 22:
            # dataが22文字超 → データプールからフォールバック選択
            # まずトピックからカテゴリを特定
            category = "長期"  # デフォルト
            for kw, cat in _TOPIC_TO_CATEGORY.items():
                if kw in topic:
                    category = cat
                    break
            pool = DATA_POOL.get(category, DATA_POOL["長期"])
            # Claudeの生成文とキーワードが重なるものを優先選択
            best = pool[0]
            best_score = 0
            for candidate in pool:
                score = sum(1 for w in candidate if w in text)
                if score > best_score:
                    best_score = score
                    best = candidate
            print(f"  [修正] dataが{len(text)}文字で長すぎ → プールから選択:「{best}」")
            s["text"] = best
            s["slide_text"] = _single_sentence_slide_text(best)
            text = best
            data_text = best  # resolve用に更新

        elif role in strict_limits:
            limit = strict_limits[role]
            if len(text) > limit:
                print(f"  [警告] {role}が{len(text)}文字（制限{limit}文字）→ 切り詰めます")
                parts = re.split(r"(?<=[。？！])", text)
                trimmed = ""
                for part in parts:
                    if len(trimmed + part) <= limit:
                        trimmed += part
                    else:
                        break
                s["text"] = trimmed if trimmed else text[:limit]

        elif role == "empathy":
            # AI生成部分の間延び防止
            if opening and opening in text:
                raw_ai_part = text.replace(opening, "").strip().rstrip("。、 ")
                ai_part = _trim_to_first_sentence(raw_ai_part, 12)
                if ai_part != raw_ai_part:
                    print(f"  [調整] empathyのAI部分を切り詰めました")
                s["text"] = (ai_part + "。" + opening) if ai_part else opening
            elif not opening:
                # 語りかけなし → AI生成の共感テキストを10文字以内に制限
                # ただし最低4文字は確保（「あなたも。」等の短すぎ防止）
                if len(text) > 10:
                    trimmed = _trim_to_first_sentence(text, 10)
                    if len(trimmed) >= 4:
                        s["text"] = trimmed + "。"
                        print(f"  [調整] empathy（語りかけなし）を切り詰めました")
                    else:
                        print(f"  [維持] empathy切り詰め結果が短すぎるため元テキストを維持")

        elif role == "resolve":
            # dataの内容に最も合う結論フレーズと接続詞を一括選択
            theme_name = fmt_vars.get("theme_name", "")
            best_conclusion, connector, resolve_tag = _select_conclusion_and_connector(data_text, theme_name)
            if best_conclusion != conclusion:
                print(f"  [修正] 結論フレーズを変更: 「{conclusion}」→「{best_conclusion}」")
                conclusion = best_conclusion

            s["text"] = connector + conclusion
            s["slide_text"] = _resolve_slide_from_conclusion(conclusion)

            # resolve-closing 距離チェック: 同じ意味タグのclosingを避けて再選択
            if hook_word and resolve_tag:
                closing, closing_slide = _apply_loop_closing(
                    scenes, hook_word, theme_name, resolve_tag)
                print(f"  [距離チェック] closing をresolveタグ「{resolve_tag}」と離して再選択:「{closing_slide}」")

        if "slide_text" in s:
            s["slide_text"] = _clean_slide_text(s.get("slide_text", ""))

    # hook補正後に closing 文面が更新されることがあるため、
    # 最後に表示テキストを必ず再適用する。
    for s in scenes:
        if s.get("role") == "closing":
            s["text"] = closing
            s["slide_text"] = _clean_slide_text(_closing_slide_from_text(closing))
            break

    # バリデーション
    title = data.get("title", "").strip()
    if not title or len(scenes) != expected_scenes:
        print(f"  [エラー] 台本の形式が不正です（タイトル: {bool(title)}, シーン数: {len(scenes)}/{expected_scenes}）")
        _save_debug("script_invalid.json", json.dumps(data, ensure_ascii=False, indent=2))
        return {}

    total_sec = sum(s.get("duration_sec", 0) for s in scenes)
    total_chars = sum(len(s.get("text", "")) for s in scenes)
    print(f"  台本生成完了（タイトル: {title}）")
    print(f"  シーン数: {len(scenes)} / 想定尺: {total_sec}秒 / 文字数: {total_chars}文字")

    # トピックを返り値に含める（transcript.json への保存・dedupe等で使用）
    data["topic"] = topic
    data = normalize_script_spelling(data)

    return data


def _save_debug(filename: str, content: str):
    """デバッグ情報を debug/ に保存する。"""
    import pathlib
    debug_dir = pathlib.Path(__file__).parent / "debug"
    debug_dir.mkdir(exist_ok=True)
    try:
        (debug_dir / filename).write_text(content, encoding="utf-8")
        print(f"  デバッグ情報を保存: debug/{filename}")
    except Exception:
        pass
