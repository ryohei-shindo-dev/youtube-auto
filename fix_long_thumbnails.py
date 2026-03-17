"""長尺動画1・2本目のサムネイルを再生成するワンショットスクリプト。

3本目（オルカンvsS&P500）のスタイルに合わせる:
- 顔が大きく映った人物写真
- 明るめ（brightness 0.85〜0.90）
- テキストは一目で内容がわかるもの
- 「積立」→「積み立て」修正
"""
from __future__ import annotations

import pathlib
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

LONG_DIR = pathlib.Path(__file__).parent / "long_video"
PHOTOS_DIR = pathlib.Path(__file__).parent / "assets" / "photos"

THUMB_WIDTH = 1280
THUMB_HEIGHT = 720

FONT_HEAVY = "/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc"
FONT_BOLD = "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"


def _load_font(path: str, size: int):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _crop_to_landscape(img: Image.Image, w: int, h: int) -> Image.Image:
    """画像を指定アスペクト比にクロップする。"""
    target_ratio = w / h
    img_ratio = img.width / img.height
    if img_ratio > target_ratio:
        new_w = int(img.height * target_ratio)
        left = (img.width - new_w) // 2
        img = img.crop((left, 0, left + new_w, img.height))
    else:
        new_h = int(img.width / target_ratio)
        top = (img.height - new_h) // 2
        img = img.crop((0, top, img.width, top + new_h))
    return img.resize((w, h), Image.LANCZOS)


def _render_thumbnail(
    photo_path: pathlib.Path,
    output_path: pathlib.Path,
    line1: str,
    line2: str,
    brightness: float = 0.85,
):
    """3本目スタイルのサムネイルを生成する。"""
    bg = Image.open(photo_path).convert("RGB")
    bg = _crop_to_landscape(bg, THUMB_WIDTH, THUMB_HEIGHT)
    bg = ImageEnhance.Brightness(bg).enhance(brightness)
    draw = ImageDraw.Draw(bg)

    # フォントサイズを文字数に応じて調整
    n1 = len(line1)
    if n1 <= 6:
        size1 = 130
    elif n1 <= 10:
        size1 = 110
    else:
        size1 = 90

    n2 = len(line2)
    size2 = 62 if n2 <= 12 else 52

    pain_font = _load_font(FONT_HEAVY, size1)
    body_font = _load_font(FONT_BOLD, size2)

    # 左寄せ配置
    text_x = 80

    # 1行目の位置
    bbox1 = draw.textbbox((0, 0), line1, font=pain_font)
    h1 = bbox1[3] - bbox1[1]

    bbox2 = draw.textbbox((0, 0), line2, font=body_font)
    h2 = bbox2[3] - bbox2[1]

    gap = 30
    total_h = h1 + gap + h2
    y1 = (THUMB_HEIGHT - total_h) // 2
    y2 = y1 + h1 + gap

    # 1行目: メインテキスト（黄色、縁取り）
    draw.text(
        (text_x, y1), line1, font=pain_font,
        fill=(240, 200, 60), stroke_width=7, stroke_fill=(0, 0, 0),
    )
    # 2行目: サブテキスト（白、縁取り）
    draw.text(
        (text_x, y2), line2, font=body_font,
        fill=(255, 255, 255), stroke_width=4, stroke_fill=(0, 0, 0),
    )

    bg.save(output_path, "PNG", optimize=True)
    size_kb = output_path.stat().st_size // 1024
    print(f"  保存完了: {output_path} ({size_kb}KB)")


def main():
    # 1本目: 含み損の夜 → 悩む男性（顔大きい）+ わかりやすいテキスト
    print("1本目: 含み損がつらい夜に")
    _render_thumbnail(
        photo_path=PHOTOS_DIR / "anxiety" / "anxiety10.jpg",
        output_path=LONG_DIR / "01_fukumison" / "thumbnail.png",
        line1="含み損がつらい夜に",
        line2="静かな整理のしかた",
        brightness=0.95,
    )

    # 2本目: 積み立て3年目 → PC前の女性（顔見える）+ 表記修正
    print("2本目: 積み立て3年目")
    _render_thumbnail(
        photo_path=PHOTOS_DIR / "anxiety" / "anxiety20.jpg",
        output_path=LONG_DIR / "02_tsumitate3" / "thumbnail.png",
        line1="積み立て3年目",
        line2="一番つらい理由",
        brightness=0.95,
    )

    print("\n完了")


if __name__ == "__main__":
    main()
