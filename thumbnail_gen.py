"""
thumbnail_gen.py
Pillow で YouTube 用のサムネイル画像（1280x720）を生成するモジュール。

【サムネ設計】
  曜日ごとにテンプレを固定。
  「曜日テンプレ（カラー）＋その日のキーワード」で生成する。

  月（メリット）:    グリーン系 — 成長・利益のイメージ
  火（格言）:        ゴールド系 — 格言・知恵のイメージ
  水（あるある）:    レッド系   — 共感・感情のイメージ
  木（歴史データ）:  ブルー系   — データ・信頼のイメージ
  金（ガチホモチベ）: オレンジ系 — 元気・モチベのイメージ
  日（通常動画）:    ホワイト系 — 落ち着き・信頼のイメージ
"""

import pathlib
import textwrap
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

THUMB_WIDTH = 1280
THUMB_HEIGHT = 720

FONT_PATH_BOLD = "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"
FONT_PATH_HEAVY = "/System/Library/Fonts/ヒラギノ角ゴシック W9.ttc"
FONT_PATH_REGULAR = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"

CHANNEL_NAME = "ガチホのモチベ"

# 曜日テーマ別のカラーテンプレート
THEME_COLORS = {
    "メリット": {
        "bg": (10, 40, 20),
        "accent": (46, 204, 113),
        "text": (255, 255, 255),
        "sub": (46, 204, 113),
        "label": "📈 長期投資のメリット",
    },
    "格言": {
        "bg": (30, 25, 10),
        "accent": (241, 196, 15),
        "text": (255, 255, 255),
        "sub": (241, 196, 15),
        "label": "💬 投資格言",
    },
    "あるある": {
        "bg": (40, 10, 15),
        "accent": (231, 76, 60),
        "text": (255, 255, 255),
        "sub": (231, 76, 60),
        "label": "😅 長期投資あるある",
    },
    "歴史データ": {
        "bg": (10, 20, 45),
        "accent": (52, 152, 219),
        "text": (255, 255, 255),
        "sub": (52, 152, 219),
        "label": "📊 歴史データ",
    },
    "ガチホモチベ": {
        "bg": (40, 25, 10),
        "accent": (230, 126, 34),
        "text": (255, 255, 255),
        "sub": (230, 126, 34),
        "label": "🔥 ガチホモチベ",
    },
    "通常": {
        "bg": (15, 23, 42),
        "accent": (236, 240, 241),
        "text": (255, 255, 255),
        "sub": (200, 200, 200),
        "label": "",
    },
}


def generate_thumbnail(
    title: str,
    output_path: pathlib.Path,
    theme: str = "通常",
) -> Optional[pathlib.Path]:
    """
    サムネイル画像を生成する。

    Args:
        title: 動画タイトル（キーワードとして使用）
        output_path: 保存先パス
        theme: テーマ名（曜日に対応）

    Returns:
        保存したファイルパス。失敗時は None。
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    colors = THEME_COLORS.get(theme, THEME_COLORS["通常"])

    try:
        canvas = Image.new("RGB", (THUMB_WIDTH, THUMB_HEIGHT), colors["bg"])
        draw = ImageDraw.Draw(canvas)

        # 左側にアクセントバー
        draw.rectangle([(0, 0), (14, THUMB_HEIGHT)], fill=colors["accent"])

        # テーマラベル（左上）
        if colors["label"]:
            _draw_theme_label(draw, colors["label"], colors["sub"])

        # タイトルテキスト（大きく）
        _draw_title(draw, title, colors["text"])

        # 右下にチャンネル名
        _draw_channel_badge(draw, colors["accent"])

        # 右側にアクセント図形
        _draw_accent_shapes(draw, colors["accent"], colors["sub"])

        canvas.save(str(output_path), "PNG", optimize=True)
        size_kb = output_path.stat().st_size // 1024
        print(f"  サムネイル生成完了: {output_path.name}（{size_kb}KB）")
        return output_path

    except Exception as e:
        print(f"  [エラー] サムネイル生成に失敗: {e}")
        return None


def _draw_theme_label(draw: ImageDraw.Draw, label: str, color: tuple):
    """左上にテーマラベルを表示する。"""
    font = _load_font(FONT_PATH_REGULAR, 22)
    draw.text((30, 20), label, font=font, fill=color)


def _draw_title(draw: ImageDraw.Draw, title: str, color: tuple):
    """タイトルテキストを左寄せで大きく描画する。"""
    font = _load_font(FONT_PATH_HEAVY, 72)
    wrapped = textwrap.wrap(title, width=10)
    lines = wrapped[:3]

    line_height = 110
    total_height = len(lines) * line_height
    y_start = (THUMB_HEIGHT - total_height) // 2

    for i, line in enumerate(lines):
        x = 40
        y = y_start + i * line_height
        draw.text((x + 3, y + 3), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=color)


def _draw_channel_badge(draw: ImageDraw.Draw, accent: tuple):
    """右下にチャンネル名バッジを描画する。"""
    font = _load_font(FONT_PATH_REGULAR, 28)
    bbox = draw.textbbox((0, 0), CHANNEL_NAME, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    padding = 12
    x = THUMB_WIDTH - text_width - padding * 2 - 30
    y = THUMB_HEIGHT - text_height - padding * 2 - 30
    draw.rounded_rectangle(
        [(x, y), (x + text_width + padding * 2, y + text_height + padding * 2)],
        radius=8,
        fill=accent,
    )
    draw.text((x + padding, y + padding), CHANNEL_NAME, font=font, fill=(255, 255, 255))


def _draw_accent_shapes(draw: ImageDraw.Draw, accent: tuple, sub: tuple):
    """右側にアクセント図形を描画する。"""
    cx = THUMB_WIDTH + 40
    cy = THUMB_HEIGHT // 2
    r = 200
    draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], outline=sub, width=4)
    draw.ellipse([(cx - r - 80, cy - 120), (cx - r - 80 + 60, cy - 120 + 60)], fill=accent)


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    """フォントを読み込む。失敗時はデフォルトフォント。"""
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()
