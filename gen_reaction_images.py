"""noteリアクション設定用の画像を5種類生成する（Pillow）。

デザイン仕様:
  - 1080x1080 正方形
  - 濃紺の縦グラデーション背景
  - 中央にシンプルな白アイコン（種類別）
  - 種類ごとに差し色のグロー効果
  - 下部に細いライン1本
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT_DIR = Path(__file__).parent / "note_images" / "reactions"

# 種類ごとの設定: (ファイル名, 差し色RGB)
KINDS = {
    "like": ("reaction_like.png", (212, 175, 55)),         # ゴールド
    "comment_like": ("reaction_comment_like.png", (135, 190, 220)),  # 水色
    "follow": ("reaction_follow.png", (200, 140, 80)),     # オレンジ
    "magazine_add": ("reaction_magazine_add.png", (130, 170, 120)),  # くすみグリーン
    "share": ("reaction_share.png", (120, 190, 190)),      # シアン
}

SIZE = 1080
BG_TOP = (15, 20, 45)      # 濃紺（上）
BG_BOTTOM = (25, 35, 65)   # やや明るい紺（下）


def _gradient_bg() -> Image.Image:
    """縦グラデーション背景を生成する（1px幅→resize方式で高速化）。"""
    strip = Image.new("RGB", (1, SIZE))
    pixels = strip.load()
    for y in range(SIZE):
        t = y / (SIZE - 1)
        r = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t)
        pixels[0, y] = (r, g, b)
    return strip.resize((SIZE, SIZE), Image.NEAREST)


def _add_glow(img: Image.Image, color: tuple[int, int, int]) -> Image.Image:
    """中央にぼんやりとした光のグロー効果を追加する。"""
    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    cx, cy = SIZE // 2, SIZE // 2 - 40
    radius = 220
    for r in range(radius, 0, -1):
        alpha = int(35 * (r / radius))
        draw.ellipse(
            [cx - r, cy - r, cx + r, cy + r],
            fill=(*color, alpha),
        )
    glow = glow.filter(ImageFilter.GaussianBlur(radius=60))
    img = img.convert("RGBA")
    return Image.alpha_composite(img, glow).convert("RGB")


def _add_bottom_line(draw: ImageDraw.Draw, color: tuple[int, int, int]):
    """下部に細いアクセントラインを描画する。"""
    y = SIZE - 120
    margin = 300
    draw.line([(margin, y), (SIZE - margin, y)], fill=(*color, 80), width=2)


def _draw_heart(draw: ImageDraw.Draw, cx: int, cy: int, size: int, color: str):
    """ハートを描画する。"""
    s = size
    # 左上の円
    draw.ellipse([cx - s, cy - s, cx, cy + int(s * 0.1)], fill=color)
    # 右上の円
    draw.ellipse([cx, cy - s, cx + s, cy + int(s * 0.1)], fill=color)
    # 下の三角
    draw.polygon([
        (cx - s, cy - int(s * 0.05)),
        (cx + s, cy - int(s * 0.05)),
        (cx, cy + int(s * 0.9)),
    ], fill=color)


def _draw_speech_bubble(draw: ImageDraw.Draw, cx: int, cy: int, color: str):
    """吹き出しアイコンを描画する。"""
    w, h = 130, 100
    r = 25
    x0, y0 = cx - w, cy - h
    x1, y1 = cx + w, cy + h - 30
    draw.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=color)
    # しっぽ
    draw.polygon([
        (cx - 30, y1 - 5),
        (cx + 10, y1 - 5),
        (cx - 50, y1 + 50),
    ], fill=color)
    # 内側に小さなハート
    _draw_heart(draw, cx, cy - 15, 30, "#1a2040")


def _draw_person(draw: ImageDraw.Draw, cx: int, cy: int, color: str):
    """人物シルエットアイコンを描画する。"""
    # 頭
    head_r = 45
    draw.ellipse([cx - head_r, cy - 100 - head_r, cx + head_r, cy - 100 + head_r], fill=color)
    # 体（半楕円）
    body_w, body_h = 80, 100
    draw.ellipse([cx - body_w, cy - 20, cx + body_w, cy + body_h + 20], fill=color)


def _draw_bookmark(draw: ImageDraw.Draw, cx: int, cy: int, color: str):
    """ブックマーク/本のアイコンを描画する。"""
    w, h = 70, 120
    draw.rectangle([cx - w, cy - h, cx + w, cy + h], fill=color)
    # 下のV字切り込み
    draw.polygon([
        (cx - w, cy + h),
        (cx, cy + h - 40),
        (cx + w, cy + h),
        (cx + w, cy + h + 5),
        (cx - w, cy + h + 5),
    ], fill="#1a2040")


def _draw_share_arrow(draw: ImageDraw.Draw, cx: int, cy: int, color: str):
    """シェア矢印アイコンを描画する。"""
    # 矢印の頭（右上向き）
    draw.polygon([
        (cx + 80, cy - 80),
        (cx + 80, cy - 10),
        (cx + 10, cy - 80),
    ], fill=color)
    # 矢印の軸（曲線を直線で近似）
    draw.line([
        (cx + 50, cy - 45),
        (cx, cy - 20),
        (cx - 40, cy + 20),
        (cx - 60, cy + 80),
    ], fill=color, width=18, joint="curve")


ICON_DRAWERS = {
    "like": lambda d, cx, cy: _draw_heart(d, cx, cy, 80, "white"),
    "comment_like": lambda d, cx, cy: _draw_speech_bubble(d, cx, cy, "white"),
    "follow": lambda d, cx, cy: _draw_person(d, cx, cy, "white"),
    "magazine_add": lambda d, cx, cy: _draw_bookmark(d, cx, cy, "white"),
    "share": lambda d, cx, cy: _draw_share_arrow(d, cx, cy, "white"),
}


def generate_reaction_image(kind: str, bg_base: Image.Image | None = None) -> Path:
    """1種類のリアクション画像を生成して保存する。"""
    filename, accent = KINDS[kind]

    # 背景（bg_base が渡されたら再利用）
    img = bg_base.copy() if bg_base else _gradient_bg()
    img = _add_glow(img, accent)

    draw = ImageDraw.Draw(img)

    # アイコン
    cx, cy = SIZE // 2, SIZE // 2 - 30
    ICON_DRAWERS[kind](draw, cx, cy)

    # 下部ライン
    _add_bottom_line(draw, accent)

    # 保存
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / filename
    img.save(out_path, "PNG", optimize=True)
    print(f"  ✓ {kind}: {out_path}")
    return out_path


def main():
    print("リアクション画像を生成中...\n")
    bg_base = _gradient_bg()
    paths = {}
    for kind in KINDS:
        paths[kind] = generate_reaction_image(kind, bg_base=bg_base)
    print(f"\n完了: {len(paths)}枚 → {OUT_DIR}")
    return paths


if __name__ == "__main__":
    main()
