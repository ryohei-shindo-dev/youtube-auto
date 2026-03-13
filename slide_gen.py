"""
slide_gen.py
プリメイド画像 + Pillow で YouTube Shorts 用のスライド画像（1080x1920）を生成するモジュール。

【レイアウト2型】
  v1（従来型）: シルエット画像を全画面に暗くぼかして配置、テキスト中央
  v2（写真型）: 写真の縦横で自動レイアウト切替
    - 縦型写真: 全画面写真 + 下部グラデーション + テキスト重ね（没入型）
    - 横型写真: 上部55%写真 + 下部45%テキスト（分割型）
    - 写真は assets/photos/ のカテゴリ別素材を使用
    - 色補正はnote記事画像と統一（暗め・低彩度・ネイビーオーバーレイ）

【素材】
  assets/*.png           — v1用シルエット画像（12枚）
  assets/photos/*/       — v2用ストック写真（5カテゴリ×3枚）
    anxiety/   : 不安系（hook用）
    comparison/: 比較・焦り系（empathy用）
    data/      : データ系（data用）
    recovery/  : 回復・安心系（resolve用）
    steady/    : 行動・継続系（closing用）
"""

from __future__ import annotations

import pathlib
import random
import textwrap

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

# Shorts 解像度（縦型 9:16）
SHORTS_WIDTH = 1080
SHORTS_HEIGHT = 1920

# 日本語フォントパス（macOS 標準）
FONT_PATH_HEAVY = "/System/Library/Fonts/ヒラギノ角ゴシック W9.ttc"
FONT_PATH_REGULAR = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"

# アセットディレクトリ
ASSETS_DIR = pathlib.Path(__file__).parent / "assets"
PHOTOS_DIR = ASSETS_DIR / "photos"

CHANNEL_NAME = "ガチホのモチベ"

# ── v2（写真型）レイアウト定数 ──
PHOTO_RATIO = 0.55  # 上部写真エリアの割合
PHOTO_HEIGHT = int(SHORTS_HEIGHT * PHOTO_RATIO)  # 1056px
TEXT_AREA_HEIGHT = SHORTS_HEIGHT - PHOTO_HEIGHT    # 864px

# ロール → 写真カテゴリ（ChatGPT提案に基づく）
ROLE_PHOTO_CATEGORY = {
    "hook": "anxiety",
    "empathy": "comparison",
    "data": "data",
    "resolve": "recovery",
    "closing": "steady",
}

# v2用の下部背景色（ロール別、紺系で統一感）
V2_TEXT_BG = {
    "hook": (20, 15, 35),
    "empathy": (15, 18, 38),
    "data": (12, 22, 42),
    "resolve": (15, 30, 30),
    "closing": (20, 18, 30),
}

# v2用の写真補正パラメータ（note画像と統一）
V2_PHOTO_BRIGHTNESS = 0.75
V2_PHOTO_SATURATION = 0.85
V2_PHOTO_BLUR = 1
V2_PHOTO_OVERLAY = (15, 20, 45, 100)  # 薄いネイビー

# ── テーマ×ロール → 画像ファイル名のマッピング ──
THEME_IMAGE_MAP = {
    "メリット": {
        "hook": "01_chart_worried.png",
        "empathy": "03_person_thinking.png",
        "data": "08_long_term_chart.png",
        "resolve": "06_person_happy.png",
        "closing": "05_person_relieved.png",
    },
    "格言": {
        "hook": "04_person_down.png",
        "empathy": "03_person_thinking.png",
        "data": "08_long_term_chart.png",
        "resolve": "05_person_relieved.png",
        "closing": "11_calm_ocean.png",
    },
    "あるある": {
        "hook": "01_chart_worried.png",
        "empathy": "02_phone_anxious.png",
        "data": "04_person_down.png",
        "resolve": "05_person_relieved.png",
        "closing": "06_person_happy.png",
    },
    "歴史データ": {
        "hook": "01_chart_worried.png",
        "empathy": "03_person_thinking.png",
        "data": "09_growth_graph.png",
        "resolve": "12_sunrise.png",
        "closing": "06_person_happy.png",
    },
    "ガチホモチベ": {
        "hook": "02_phone_anxious.png",
        "empathy": "04_person_down.png",
        "data": "08_long_term_chart.png",
        "resolve": "06_person_happy.png",
        "closing": "12_sunrise.png",
    },
    "後悔系": {
        "hook": "04_person_down.png",
        "empathy": "02_phone_anxious.png",
        "data": "08_long_term_chart.png",
        "resolve": "03_person_thinking.png",
        "closing": "05_person_relieved.png",
    },
    "具体数字系": {
        "hook": "01_chart_worried.png",
        "empathy": "03_person_thinking.png",
        "data": "09_growth_graph.png",
        "resolve": "06_person_happy.png",
        "closing": "12_sunrise.png",
    },
    "積立疲れ系": {
        "hook": "02_phone_anxious.png",
        "empathy": "04_person_down.png",
        "data": "08_long_term_chart.png",
        "resolve": "05_person_relieved.png",
        "closing": "11_calm_ocean.png",
    },
    "比較焦り系": {
        "hook": "02_phone_anxious.png",
        "empathy": "01_chart_worried.png",
        "data": "08_long_term_chart.png",
        "resolve": "03_person_thinking.png",
        "closing": "06_person_happy.png",
    },
    "継続モチベ系": {
        "hook": "03_person_thinking.png",
        "empathy": "05_person_relieved.png",
        "data": "09_growth_graph.png",
        "resolve": "06_person_happy.png",
        "closing": "12_sunrise.png",
    },
}

# 通常動画用のロール→画像マッピング
LONG_IMAGE_MAP = {
    "opening": "07_investment_app.png",
    "theme": "03_person_thinking.png",
    "data": "08_long_term_chart.png",
    "explain": "09_growth_graph.png",
    "summary": "05_person_relieved.png",
    "closing": "12_sunrise.png",
}

# ── ロール別のオーバーレイカラー（RGBA） ──
ROLE_OVERLAY = {
    "hook": (30, 10, 10, 210),
    "empathy": (10, 20, 50, 200),
    "data": (15, 35, 55, 190),
    "resolve": (20, 50, 30, 190),
    "closing": (40, 20, 10, 190),
    "opening": (10, 20, 50, 200),
    "explain": (20, 20, 40, 200),
    "theme": (20, 20, 40, 200),
    "summary": (20, 50, 30, 190),
}

# ── テキストカラー ──
ROLE_TEXT_COLOR = {
    "hook": (255, 120, 100),
    "empathy": (255, 255, 255),
    "data": (100, 200, 255),
    "resolve": (120, 230, 150),
    "closing": (255, 200, 100),
    "opening": (255, 255, 255),
    "explain": (200, 200, 200),
    "theme": (255, 215, 0),
    "summary": (120, 230, 150),
}

# ── フォールバック背景色 ──
ROLE_FALLBACK_BG = {
    "hook": (40, 10, 10),
    "empathy": (10, 20, 50),
    "data": (15, 35, 55),
    "resolve": (20, 50, 30),
    "closing": (40, 20, 10),
    "opening": (10, 20, 50),
    "explain": (20, 20, 40),
    "theme": (20, 20, 40),
    "summary": (20, 50, 30),
}


def generate_all_slides(
    scenes: list,
    output_dir: pathlib.Path,
    theme: str = "",
    use_photo: bool = False,
) -> list:
    """全シーンのスライド画像を生成する。

    Args:
        use_photo: True で v2（写真型）レイアウトを使用。
                   False で従来の v1（シルエット型）。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    layout = "v2（写真型）" if use_photo else "v1（シルエット型）"
    print(f"  レイアウト: {layout}")

    for i, scene in enumerate(scenes):
        idx = i + 1
        output_path = output_dir / f"slide_{idx:02d}.png"
        role = scene.get("role", "hook")
        text = scene.get("slide_text", scene.get("text", ""))

        print(f"  スライド{idx}（{role}）を生成中...")
        try:
            if use_photo:
                path = _generate_slide_v2(text, role, output_path)
            else:
                path = _generate_slide(text, role, theme, output_path)
            paths.append(path)
            size_kb = path.stat().st_size // 1024
            print(f"    保存完了: {path.name}（{size_kb}KB）")
        except Exception as e:
            print(f"    [エラー] スライド{idx}の生成に失敗: {e}")

    print(f"  スライド生成完了（{len(paths)}/{len(scenes)}枚成功）")
    return paths


def _generate_slide(
    text: str,
    role: str,
    theme: str,
    output_path: pathlib.Path,
) -> pathlib.Path:
    """1シーン分のスライド画像を生成する。"""

    # プリメイド画像を取得
    bg_img = _get_premade_image(role, theme)

    if bg_img:
        canvas = _crop_to_shorts(bg_img)
        canvas = canvas.filter(ImageFilter.GaussianBlur(radius=3))
        enhancer = ImageEnhance.Brightness(canvas)
        canvas = enhancer.enhance(0.4)
        canvas = canvas.convert("RGBA")
        overlay_color = ROLE_OVERLAY.get(role, (20, 20, 40, 200))
        overlay = Image.new("RGBA", (SHORTS_WIDTH, SHORTS_HEIGHT), overlay_color)
        canvas = Image.alpha_composite(canvas, overlay)
        canvas = canvas.convert("RGB")
    else:
        bg_color = ROLE_FALLBACK_BG.get(role, (30, 30, 30))
        canvas = Image.new("RGB", (SHORTS_WIDTH, SHORTS_HEIGHT), bg_color)

    draw = ImageDraw.Draw(canvas)

    # アクセントライン
    _draw_accent_lines(draw, role)

    # メインテキスト
    text_color = ROLE_TEXT_COLOR.get(role, (255, 255, 255))
    _draw_main_text(draw, text, text_color)

    # チャンネル名
    _draw_channel_name(draw)

    canvas.save(str(output_path), "PNG", optimize=True)
    return output_path


def _is_portrait(img: Image.Image) -> bool:
    """写真が縦型（高さ > 幅）かどうかを判定する。"""
    return img.size[1] > img.size[0]


def _apply_photo_correction(img: Image.Image) -> Image.Image:
    """写真に色補正+ネイビーオーバーレイを適用する（portrait/landscape共通）。"""
    img = ImageEnhance.Brightness(img).enhance(V2_PHOTO_BRIGHTNESS)
    img = ImageEnhance.Color(img).enhance(V2_PHOTO_SATURATION)
    if V2_PHOTO_BLUR > 0:
        img = img.filter(ImageFilter.GaussianBlur(radius=V2_PHOTO_BLUR))
    img = img.convert("RGBA")
    overlay = Image.new("RGBA", img.size, V2_PHOTO_OVERLAY)
    return Image.alpha_composite(img, overlay).convert("RGB")


def _generate_slide_v2(
    text: str,
    role: str,
    output_path: pathlib.Path,
) -> pathlib.Path:
    """v2: 写真の縦横で自動レイアウト切替。
    - 縦型写真: 全画面写真 + 下部グラデーション + テキスト重ね（没入型）
    - 横型写真: 上部55%写真 + 下部45%テキスト（従来型）
    """
    photo = _get_photo(role)

    if photo and _is_portrait(photo):
        return _generate_slide_v2_portrait(text, role, output_path, photo)
    else:
        return _generate_slide_v2_landscape(text, role, output_path, photo)


def _generate_slide_v2_portrait(
    text: str,
    role: str,
    output_path: pathlib.Path,
    photo: Image.Image,
) -> pathlib.Path:
    """v2 縦型: 写真を全画面に配置し、下部にグラデーション+テキストを重ねる。"""
    canvas = Image.new("RGB", (SHORTS_WIDTH, SHORTS_HEIGHT), (15, 15, 30))

    # 写真を全画面にフィット + 色補正
    photo_area = _fit_photo_to_area(photo, SHORTS_WIDTH, SHORTS_HEIGHT)
    photo_area = _apply_photo_correction(photo_area)
    canvas.paste(photo_area, (0, 0))

    # 下部45%にグラデーション（透明→暗色）でテキスト読みやすく
    bg_color = V2_TEXT_BG.get(role, (20, 18, 30))
    _blend_gradient(canvas, start_y=int(SHORTS_HEIGHT * 0.55),
                    bg_color=bg_color, exponent=1.5)

    draw = ImageDraw.Draw(canvas)

    # アクセントライン（上端と下端）
    accent_color = ROLE_TEXT_COLOR.get(role, (255, 255, 255))
    draw.rectangle([(0, 0), (SHORTS_WIDTH, 4)], fill=accent_color)
    draw.rectangle([(0, SHORTS_HEIGHT - 4), (SHORTS_WIDTH, SHORTS_HEIGHT)],
                   fill=accent_color)

    # テキスト（下部40%の中央に配置）
    text_color = ROLE_TEXT_COLOR.get(role, (255, 255, 255))
    text_area_top = int(SHORTS_HEIGHT * 0.60)
    text_area_h = SHORTS_HEIGHT - text_area_top - 60
    _draw_text_in_area(draw, text, text_color, text_area_top, text_area_h)

    # チャンネル名
    _draw_channel_name(draw)

    canvas.save(str(output_path), "PNG", optimize=True)
    return output_path


def _generate_slide_v2_landscape(
    text: str,
    role: str,
    output_path: pathlib.Path,
    photo: Image.Image | None,
) -> pathlib.Path:
    """v2 横型: 上部55%に写真 + 下部45%にテキストのレイアウト（従来型）。"""
    canvas = Image.new("RGB", (SHORTS_WIDTH, SHORTS_HEIGHT), (15, 15, 30))

    # ── 上部: 写真エリア ──
    if photo:
        photo_area = _fit_photo_to_area(photo, SHORTS_WIDTH, PHOTO_HEIGHT)
        photo_area = _apply_photo_correction(photo_area)
        canvas.paste(photo_area, (0, 0))

        # 写真下端にグラデーション
        _draw_gradient_border(canvas, role)
    else:
        fallback = Image.new("RGB", (SHORTS_WIDTH, PHOTO_HEIGHT),
                             ROLE_FALLBACK_BG.get(role, (30, 30, 30)))
        canvas.paste(fallback, (0, 0))

    # ── 下部: テキストエリア ──
    bg_color = V2_TEXT_BG.get(role, (20, 18, 30))
    text_bg = Image.new("RGB", (SHORTS_WIDTH, TEXT_AREA_HEIGHT), bg_color)
    canvas.paste(text_bg, (0, PHOTO_HEIGHT))

    draw = ImageDraw.Draw(canvas)

    # アクセントライン（上端と下端）
    accent_color = ROLE_TEXT_COLOR.get(role, (255, 255, 255))
    draw.rectangle([(0, 0), (SHORTS_WIDTH, 4)], fill=accent_color)
    draw.rectangle([(0, SHORTS_HEIGHT - 4), (SHORTS_WIDTH, SHORTS_HEIGHT)],
                   fill=accent_color)

    # 写真とテキストの境界に細いライン
    draw.rectangle([(40, PHOTO_HEIGHT - 1), (SHORTS_WIDTH - 40, PHOTO_HEIGHT + 1)],
                   fill=(*accent_color, 80) if len(accent_color) == 3 else accent_color)

    # メインテキスト（下部エリアの中央に配置）
    text_color = ROLE_TEXT_COLOR.get(role, (255, 255, 255))
    _draw_text_in_area(draw, text, text_color, PHOTO_HEIGHT, TEXT_AREA_HEIGHT)

    # チャンネル名
    _draw_channel_name(draw)

    canvas.save(str(output_path), "PNG", optimize=True)
    return output_path


def _get_photo(role: str) -> Image.Image | None:
    """ロールに対応する写真カテゴリからランダムに1枚取得する。"""
    category = ROLE_PHOTO_CATEGORY.get(role, "")
    if not category:
        return None

    photo_dir = PHOTOS_DIR / category
    if not photo_dir.exists():
        return None

    photos = list(photo_dir.glob("*.jpg")) + list(photo_dir.glob("*.png"))
    if not photos:
        return None

    try:
        return Image.open(random.choice(photos))
    except Exception:
        return None


def _fit_photo_to_area(
    img: Image.Image, target_w: int, target_h: int
) -> Image.Image:
    """写真を指定エリアにフィットさせる（1回のリサイズ + クロップ）。"""
    src_w, src_h = img.size

    # 幅・高さ両方をカバーする最小スケールを選択（1回で済む）
    scale = max(target_w / src_w, target_h / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    # はみ出し分をクロップ（横は中央、縦は上部優先）
    left = (new_w - target_w) // 2
    img = img.crop((left, 0, left + target_w, target_h))

    return img


def _blend_gradient(
    canvas: Image.Image, start_y: int, bg_color: tuple, exponent: float = 1.0,
):
    """canvas の start_y〜底辺にグラデーション合成する（alpha composite方式、高速）。"""
    w = canvas.size[0]
    h = canvas.size[1] - start_y
    if h <= 0:
        return

    # グラデーションマスク（上が透明、下が不透明）
    grad_mask = Image.new("L", (1, h))
    for y in range(h):
        alpha = int(((y / h) ** exponent) * 255)
        grad_mask.putpixel((0, y), alpha)
    grad_mask = grad_mask.resize((w, h), Image.NEAREST)

    # 暗色レイヤーをマスク付きで合成
    dark_layer = Image.new("RGB", (w, h), bg_color)
    region = canvas.crop((0, start_y, w, start_y + h))
    blended = Image.composite(dark_layer, region, grad_mask)
    canvas.paste(blended, (0, start_y))


def _draw_gradient_border(canvas: Image.Image, role: str):
    """写真下端にグラデーションを描画して、テキストエリアと滑らかに接続する。"""
    bg_color = V2_TEXT_BG.get(role, (20, 18, 30))
    _blend_gradient(canvas, start_y=PHOTO_HEIGHT - 80, bg_color=bg_color)


def _draw_text_in_area(
    draw: ImageDraw.Draw, text: str, color: tuple,
    area_top: int, area_height: int
):
    """指定エリアの中央にテキストを配置する（影付き）。"""
    font = _load_font(FONT_PATH_HEAVY, 110)

    wrapped = _wrap_text(text, 7)
    lines = wrapped.split("\n")

    line_height = 155
    total_height = len(lines) * line_height
    y_start = area_top + (area_height - total_height) // 2

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]
        x = (SHORTS_WIDTH - text_width) // 2
        y = y_start + i * line_height

        # 影
        for dx, dy in [(3, 3), (2, 2)]:
            draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=color)


def _get_premade_image(role: str, theme: str):
    """プリメイド画像を取得する。assets/ になければ None。"""
    # テーマ別マッピングから画像ファイル名を取得
    if theme and theme in THEME_IMAGE_MAP:
        filename = THEME_IMAGE_MAP[theme].get(role, "")
    else:
        filename = LONG_IMAGE_MAP.get(role, "")

    if not filename:
        return None

    img_path = ASSETS_DIR / filename
    if not img_path.exists():
        return None

    try:
        return Image.open(img_path)
    except Exception:
        return None


def _crop_to_shorts(img: Image.Image) -> Image.Image:
    """画像を Shorts サイズ（1080x1920）に中央クロップ＆リサイズする。"""
    src_w, src_h = img.size
    target_ratio = SHORTS_WIDTH / SHORTS_HEIGHT

    if src_w / src_h > target_ratio:
        crop_h = src_h
        crop_w = int(src_h * target_ratio)
    else:
        crop_w = src_w
        crop_h = int(src_w / target_ratio)

    left = (src_w - crop_w) // 2
    top = (src_h - crop_h) // 2
    img = img.crop((left, top, left + crop_w, top + crop_h))
    return img.resize((SHORTS_WIDTH, SHORTS_HEIGHT), Image.LANCZOS)


def _draw_accent_lines(draw: ImageDraw.Draw, role: str):
    """上部と下部にアクセントラインを描画する。"""
    color = ROLE_TEXT_COLOR.get(role, (255, 255, 255))
    draw.rectangle([(0, 0), (SHORTS_WIDTH, 6)], fill=color)
    draw.rectangle([(0, SHORTS_HEIGHT - 6), (SHORTS_WIDTH, SHORTS_HEIGHT)], fill=color)


def _draw_main_text(draw: ImageDraw.Draw, text: str, color: tuple):
    """メインテキストを中央に大きく配置する（影付き）。"""
    font = _load_font(FONT_PATH_HEAVY, 120)

    wrapped = _wrap_text(text, 7)
    lines = wrapped.split("\n")

    line_height = 170
    total_height = len(lines) * line_height
    y_start = (SHORTS_HEIGHT - total_height) // 2

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]
        x = (SHORTS_WIDTH - text_width) // 2
        y = y_start + i * line_height

        for dx, dy in [(4, 4), (3, 3), (2, 2)]:
            draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=color)


def _draw_channel_name(draw: ImageDraw.Draw):
    """右下にチャンネル名を半透明で表示する。"""
    font = _load_font(FONT_PATH_REGULAR, 28)
    bbox = draw.textbbox((0, 0), CHANNEL_NAME, font=font)
    text_width = bbox[2] - bbox[0]
    x = SHORTS_WIDTH - text_width - 40
    y = SHORTS_HEIGHT - 60
    draw.text((x + 1, y + 1), CHANNEL_NAME, font=font, fill=(0, 0, 0))
    draw.text((x, y), CHANNEL_NAME, font=font, fill=(200, 200, 200))


def _wrap_text(text: str, width: int) -> str:
    """日本語テキストを指定文字数で折り返す。単語の途中で割れないよう調整。"""
    # 割ってはいけない単語リスト
    no_break = [
        "チャンネル", "フォロー", "コメント", "ガチホ",
        "インデックス", "リターン", "バフェット", "マンガー",
    ]

    wrapped = textwrap.wrap(text, width=width)
    result = []
    for line in wrapped:
        # 単語が割れていないかチェック
        fixed = False
        for word in no_break:
            # 行末に単語の一部だけが残っている場合
            for i in range(1, len(word)):
                partial = word[:i]
                if line.endswith(partial) and not line.endswith(word):
                    # この行から部分を除去して次の行に回す
                    line = line[:-len(partial)]
                    fixed = True
                    break
            if fixed:
                break
        if line:
            result.append(line)

    return "\n".join(result)


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    """フォントを読み込む。失敗時はデフォルトフォント。"""
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()
