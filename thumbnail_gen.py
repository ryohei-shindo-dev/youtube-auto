"""
thumbnail_gen.py
Pillow で YouTube Shorts 用のサムネイル画像（1280x720）を生成するモジュール。

【サムネ設計（v2 — 痛みワード最強テンプレ）】
  黒背景 + 中央に超大文字の痛みワード（2〜4語）
  1行目: hookの痛みワード（黄色、超太字）
  2行目: resolveの短い結論（白、やや小さい）

  例:
    暴落
    売るな
"""

import pathlib
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

THUMB_WIDTH = 1280
THUMB_HEIGHT = 720

FONT_PATH_HEAVY = "/System/Library/Fonts/ヒラギノ角ゴシック W9.ttc"
FONT_PATH_REGULAR = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"

CHANNEL_NAME = "ガチホのモチベ"

# 痛みワード色
COLOR_PAIN = (255, 215, 0)       # 黄色（メイン）
COLOR_RESOLVE = (255, 255, 255)  # 白（サブ）
COLOR_BG = (10, 10, 10)          # ほぼ黒


def generate_thumbnail(
    title: str,
    output_path: pathlib.Path,
    theme: str = "通常",
    hook_text: str = "",
    resolve_text: str = "",
) -> Optional[pathlib.Path]:
    """
    サムネイル画像を生成する。

    Args:
        title: 動画タイトル（フォールバック用）
        output_path: 保存先パス
        theme: テーマ名（未使用、互換性のため残す）
        hook_text: hookのslide_text（短い痛みワード）
        resolve_text: resolveのslide_text（短い結論）

    Returns:
        保存したファイルパス。失敗時は None。
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # テキスト決定: hook_text があればそれを使う、なければタイトルから抽出
    line1 = _clean_text(hook_text) if hook_text else _extract_pain_word(title)
    line2 = _clean_text(resolve_text) if resolve_text else ""

    try:
        canvas = Image.new("RGB", (THUMB_WIDTH, THUMB_HEIGHT), COLOR_BG)
        draw = ImageDraw.Draw(canvas)

        # メインの痛みワード（黄色、超大文字）
        _draw_pain_word(draw, line1, line2)

        # 右下にチャンネル名（控えめ）
        _draw_channel_name(draw)

        canvas.save(str(output_path), "PNG", optimize=True)
        size_kb = output_path.stat().st_size // 1024
        print(f"  サムネイル生成完了: {output_path.name}（{size_kb}KB）")
        return output_path

    except Exception as e:
        print(f"  [エラー] サムネイル生成に失敗: {e}")
        return None


def _draw_pain_word(draw: ImageDraw.Draw, line1: str, line2: str):
    """中央に痛みワードを超大文字で描画する。"""
    # フォントサイズを文字数に応じて調整
    size1 = _auto_font_size(line1, max_size=160, min_size=80)
    font1 = _load_font(FONT_PATH_HEAVY, size1)

    bbox1 = draw.textbbox((0, 0), line1, font=font1)
    w1 = bbox1[2] - bbox1[0]
    h1 = bbox1[3] - bbox1[1]

    if line2:
        size2 = _auto_font_size(line2, max_size=120, min_size=60)
        font2 = _load_font(FONT_PATH_HEAVY, size2)
        bbox2 = draw.textbbox((0, 0), line2, font=font2)
        w2 = bbox2[2] - bbox2[0]
        h2 = bbox2[3] - bbox2[1]

        gap = 40
        total_h = h1 + gap + h2
        y1 = (THUMB_HEIGHT - total_h) // 2
        y2 = y1 + h1 + gap
        x1 = (THUMB_WIDTH - w1) // 2
        x2 = (THUMB_WIDTH - w2) // 2

        # 1行目: 痛みワード（黄色）
        _draw_text_with_stroke(draw, x1, y1, line1, font1, COLOR_PAIN)
        # 2行目: 結論（白）
        _draw_text_with_stroke(draw, x2, y2, line2, font2, COLOR_RESOLVE)
    else:
        # 1行のみ
        x1 = (THUMB_WIDTH - w1) // 2
        y1 = (THUMB_HEIGHT - h1) // 2
        _draw_text_with_stroke(draw, x1, y1, line1, font1, COLOR_PAIN)


def _draw_text_with_stroke(
    draw: ImageDraw.Draw, x: int, y: int,
    text: str, font, color: tuple,
):
    """黒縁付きテキストを描画する。"""
    draw.text((x, y), text, font=font, fill=color, stroke_width=6, stroke_fill=(0, 0, 0))


def _draw_channel_name(draw: ImageDraw.Draw):
    """右下にチャンネル名を控えめに表示する。"""
    font = _load_font(FONT_PATH_REGULAR, 24)
    bbox = draw.textbbox((0, 0), CHANNEL_NAME, font=font)
    tw = bbox[2] - bbox[0]
    x = THUMB_WIDTH - tw - 30
    y = THUMB_HEIGHT - 50
    draw.text((x + 1, y + 1), CHANNEL_NAME, font=font, fill=(30, 30, 30))
    draw.text((x, y), CHANNEL_NAME, font=font, fill=(100, 100, 100))


def _auto_font_size(text: str, max_size: int = 160, min_size: int = 80) -> int:
    """文字数に応じてフォントサイズを自動調整する。"""
    n = len(text)
    if n <= 2:
        return max_size
    elif n <= 4:
        return max_size - 20
    elif n <= 6:
        return max_size - 40
    elif n <= 8:
        return max_size - 60
    else:
        return min_size


def _clean_text(text: str) -> str:
    """テキストから句読点を除去してサムネ向きに整える。"""
    for ch in "。、！？.!?":
        text = text.replace(ch, "")
    return text.strip()


def _extract_pain_word(title: str) -> str:
    """タイトルから短い痛みワードを抽出する（フォールバック用）。"""
    # 句読点で分割して最初の短いフレーズを使う
    for sep in ["、", "。", "，", "…", "―", "─"]:
        if sep in title:
            parts = title.split(sep)
            shortest = min(parts, key=len)
            if 2 <= len(shortest) <= 6:
                return shortest.strip()
            return parts[0].strip()
    # 分割できない場合は先頭6文字
    return title[:6]


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    """フォントを読み込む。失敗時はデフォルトフォント。"""
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()
