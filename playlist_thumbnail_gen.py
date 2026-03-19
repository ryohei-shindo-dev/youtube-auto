"""再生リスト用カスタムサムネイル生成スクリプト。

写真主役 + 視聴者目線の短いコピー。
動画個別サムネ（黒背景＋大文字）と差別化する。

Usage:
    python playlist_thumbnail_gen.py
"""
from __future__ import annotations

import pathlib
import random

from PIL import Image, ImageDraw, ImageEnhance

from slide_gen import _fit_photo_to_area, _blend_gradient, _load_font

# ── 定数 ──
WIDTH, HEIGHT = 1280, 720
FONT_PATH_HEAVY = "/System/Library/Fonts/ヒラギノ角ゴシック W9.ttc"
SLIDES_DIR = pathlib.Path("assets/photos")
OUTPUT_DIR = pathlib.Path("assets/playlist_thumbnails")

# オーバーレイ色（各リストで微妙に違うネイビー系）
OVERLAY_COLORS = {
    "sell":    (15, 15, 35),   # 深いネイビー
    "slow":    (18, 20, 35),   # ネイビー+グレー
    "compare": (20, 15, 38),   # ネイビー+紫
    "quiet":   (15, 18, 28),   # 落ち着いたネイビー
}

YELLOW = (240, 200, 60)

# ── 再生リスト定義（視聴者目線） ──
PLAYLISTS = [
    {
        "id": "sell",
        "label": "売りたくなった日",
        "photo_category": "anxiety",
    },
    {
        "id": "slow",
        "label": "増えていない気がする",
        "photo_category": "steady",
    },
    {
        "id": "compare",
        "label": "人と比べてしまう日",
        "photo_category": "comparison",
    },
    {
        "id": "quiet",
        "label": "何も起きない日",
        "photo_category": "recovery",
    },
]


def _pick_landscape_photo(category: str) -> pathlib.Path | None:
    """カテゴリから横長写真をランダムに1枚選ぶ。"""
    search_dir = SLIDES_DIR / category
    if not search_dir.exists():
        return None

    all_photos = sorted(search_dir.glob("*.jpg"))
    if not all_photos:
        return None

    # 横長写真のみ
    landscape = []
    for p in all_photos:
        img = Image.open(p)
        w, h = img.size
        if w > h:
            landscape.append(p)

    return random.choice(landscape) if landscape else random.choice(all_photos)


def generate_playlist_thumbnail(
    label: str,
    photo_path: pathlib.Path,
    overlay_color: tuple,
    output_path: pathlib.Path,
) -> pathlib.Path:
    """再生リスト用サムネイルを1枚生成する。"""
    photo = Image.open(photo_path).convert("RGB")
    canvas = _fit_photo_to_area(photo, WIDTH, HEIGHT)

    # 全体を少し暗く + ネイビーオーバーレイ
    canvas = ImageEnhance.Brightness(canvas).enhance(0.75)
    overlay = Image.new("RGB", (WIDTH, HEIGHT), overlay_color)
    canvas = Image.blend(canvas, overlay, alpha=0.30)

    # 下半分にグラデーション
    _blend_gradient(canvas, start_y=int(HEIGHT * 0.40),
                    bg_color=overlay_color, exponent=1.5)

    draw = ImageDraw.Draw(canvas)

    # テキスト（1行、白、左下寄せ）
    font_size = 72 if len(label) <= 9 else 60
    font = _load_font(FONT_PATH_HEAVY, font_size)
    bbox = draw.textbbox((0, 0), label, font=font)
    text_h = bbox[3] - bbox[1]

    x = 60
    y = HEIGHT - text_h - 80
    draw.text((x, y), label, font=font, fill=YELLOW,
              stroke_width=4, stroke_fill=(0, 0, 0))

    # 保存
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(str(output_path), "PNG", optimize=True)
    size_kb = output_path.stat().st_size // 1024
    print(f"  生成: {output_path.name}（{size_kb}KB）— {label}")
    return output_path


def main():
    print("再生リスト用サムネイル生成\n")
    for pl in PLAYLISTS:
        photo = _pick_landscape_photo(pl["photo_category"])
        if not photo:
            print(f"  [スキップ] {pl['label']}: 写真なし")
            continue
        out = OUTPUT_DIR / f"playlist_{pl['id']}.png"
        generate_playlist_thumbnail(
            label=pl["label"],
            photo_path=photo,
            overlay_color=OVERLAY_COLORS[pl["id"]],
            output_path=out,
        )
    print(f"\n完了。出力先: {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
