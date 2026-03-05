"""
slide_gen.py
プリメイド画像 + Pillow で YouTube Shorts 用のスライド画像（1080x1920）を生成するモジュール。

【素材設計】
  動画ごとに画像生成は行わない。
  assets/ フォルダに10〜15枚の汎用画像セットを用意し、テーマ×ロールで使い分ける。
  assets/ が未準備の場合はフォールバック（単色背景）を使用。

【画像セット（assets/ に配置）】
  01_chart_worried.png    — チャートを見て悩む人
  02_phone_anxious.png    — スマホを見て焦る人
  03_person_thinking.png  — 考え込む人
  04_person_down.png      — 落ち込む人
  05_person_relieved.png  — 安心している人
  06_person_happy.png     — 喜んでいる人
  07_investment_app.png   — 投資アプリを見る人
  08_long_term_chart.png  — 長期チャート
  09_growth_graph.png     — 成長グラフ
  10_money_growing.png    — お金が育つイメージ
  11_calm_ocean.png       — 穏やかな海（安心感）
  12_sunrise.png          — 日の出（希望）

【テーマ×ロール→画像マッピング】
  テロップ位置: 画面中央（上下左右中央寄せ）
  フォント: ヒラギノ角ゴシック W9（最太字）96pt
  テキスト折り返し: 7文字/行
"""

import pathlib
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

CHANNEL_NAME = "ガチホのモチベ"

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
) -> list:
    """全シーンのスライド画像を生成する。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []

    for i, scene in enumerate(scenes):
        idx = i + 1
        output_path = output_dir / f"slide_{idx:02d}.png"
        role = scene.get("role", "hook")
        text = scene.get("slide_text", scene.get("text", ""))

        print(f"  スライド{idx}（{role}）を生成中...")
        try:
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
