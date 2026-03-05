"""
social_gen.py
TikTok・Instagram Reels・X（旧Twitter）用のキャプションを生成するモジュール。

Shorts台本のテキストからプラットフォーム別のキャプションを
テンプレートベースで生成する（API不要）。
"""

from __future__ import annotations

import json
import pathlib
import random

# 共通ハッシュタグ（長期投資チャンネル向け）
BASE_HASHTAGS = ["長期投資", "積立投資", "NISA", "ガチホ", "資産形成"]

# テーマ別の追加ハッシュタグ
THEME_HASHTAGS = {
    "メリット": ["複利", "インデックス投資", "ドルコスト平均法"],
    "格言": ["投資格言", "バフェット", "名言"],
    "あるある": ["投資あるある", "含み損", "投資初心者"],
    "歴史データ": ["株式市場", "暴落", "S&P500"],
    "ガチホモチベ": ["投資モチベーション", "長期保有", "退場しない"],
}

# TikTok追加タグ（TikTokで伸びやすいもの）
TIKTOK_EXTRA = ["投資初心者", "お金の勉強", "資産運用"]

# Instagram追加タグ（インスタで検索されやすいもの）
INSTAGRAM_EXTRA = ["インデックス投資", "投資モチベーション", "マネーリテラシー", "つみたてNISA"]

# X（旧Twitter）ハッシュタグ（1〜2個で十分）
X_HASHTAGS = ["長期投資", "ガチホ"]

# X用 hookバリエーション（自動投稿感を回避するため3パターン）
# {hook} にShorts台本のhookテキストが入る
X_HOOK_PATTERNS = [
    "{hook}",
    "{hook}がつらい夜。",
    "{hook}を見るたび思う。",
]


def generate_social_captions(script_data: dict, output_dir: pathlib.Path) -> dict:
    """TikTok・インスタ用のキャプション＋ハッシュタグを生成する。

    Args:
        script_data: script_gen が返す台本データ
        output_dir: 出力先ディレクトリ

    Returns:
        プラットフォーム別キャプション辞書
    """
    # 台本からテキスト抽出
    scenes_by_role = {}
    for scene in script_data.get("scenes", []):
        role = scene.get("role", "")
        scenes_by_role[role] = scene.get("text", "")

    hook = scenes_by_role.get("hook", "")
    data = scenes_by_role.get("data", "")
    resolve = scenes_by_role.get("resolve", "")
    theme = script_data.get("theme", "")

    # ハッシュタグ構築
    theme_tags = THEME_HASHTAGS.get(theme, [])

    tiktok_tags = _dedupe(BASE_HASHTAGS + theme_tags + TIKTOK_EXTRA)
    instagram_tags = _dedupe(BASE_HASHTAGS + theme_tags + INSTAGRAM_EXTRA)

    # TikTokキャプション（短め、1〜2行 + タグ）
    tiktok_caption = f"{hook}…{data}"
    tiktok_hashtag_str = " ".join(f"#{t}" for t in tiktok_tags)
    tiktok_full = f"{tiktok_caption} {tiktok_hashtag_str}"

    # Instagramキャプション（改行多め、読みやすく）
    insta_lines = [hook, "", data, resolve, ""]
    insta_hashtag_str = " ".join(f"#{t}" for t in instagram_tags)
    insta_full = "\n".join(insta_lines) + "\n" + insta_hashtag_str

    # X（旧Twitter）ポスト（改行多め、短文、1ポスト完結）
    x_post = _build_x_post(hook, data, resolve)

    result = {
        "tiktok": {
            "caption": tiktok_full,
            "hashtags": tiktok_tags,
        },
        "instagram": {
            "caption": insta_full,
            "hashtags": instagram_tags,
        },
        "x": {
            "post": x_post,
            "hashtags": X_HASHTAGS,
        },
    }

    # ファイル保存
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "social_captions.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  SNSキャプション生成完了: {output_path}")

    return result


def _build_x_post(hook: str, data: str, resolve: str) -> str:
    """X用ポストを生成する。改行多め・短文・1ポスト完結。"""
    # hookバリエーションをランダム選択（自動投稿感の回避）
    # hookが既に句点で終わる場合はパターンAのみ使う
    if hook.endswith("。") or hook.endswith("…") or len(hook) <= 4:
        x_hook = random.choice(X_HOOK_PATTERNS).format(hook=hook.rstrip("。"))
    else:
        x_hook = hook

    clean_data = _strip_connector(data)
    clean_resolve = _strip_connector(resolve)

    hashtag_str = " ".join(f"#{t}" for t in X_HASHTAGS)

    # X向けフォーマット（改行多め、短文）
    lines = [
        x_hook,
        "",
        "でも",
        clean_data,
        "",
        clean_resolve,
        "",
        hashtag_str,
    ]

    return "\n".join(lines)


def _strip_connector(text: str) -> str:
    """テキスト先頭の接続詞を除去する。"""
    for prefix in ["でも、", "だから、", "そう、", "でも ", "だから ", "そう "]:
        if text.startswith(prefix):
            return text[len(prefix):]
    return text


def _dedupe(tags: list[str]) -> list[str]:
    """重複を除去しつつ順序を維持する。"""
    seen = set()
    result = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            result.append(tag)
    return result
