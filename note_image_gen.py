"""
note_image_gen.py
note記事のトップ画像（見出し画像）を Pillow で生成するモジュール。

【設計】
  背景: AI生成の基幹ビジュアル（5〜8枚）を暗くぼかして使い回す
  テキスト: 見出し1行 + 補足1行（左寄せ）
  サイズ: 1280×670px（note推奨）

【テーマ分類】
  不安系 → night_thinking  積立系 → lamp_room  行動系 → door_light
  余韻系 → dawn_road       待つ系 → waiting_person
"""

from __future__ import annotations

import pathlib
from typing import Optional

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

# ---------- サイズ ----------
NOTE_WIDTH = 1280
NOTE_HEIGHT = 670

# ---------- フォント ----------
FONT_HEAVY = "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"
FONT_REGULAR = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"

# ---------- 色 ----------
COLOR_TITLE = (255, 255, 255)          # 白
COLOR_SUBTITLE = (200, 200, 200)       # 薄グレー
COLOR_ACCENT = (255, 210, 100)         # 落ち着いた黄
COLOR_OVERLAY = (10, 10, 30, 180)      # 紺〜黒の半透明

# ---------- 背景画像 ----------
ASSETS_DIR = pathlib.Path(__file__).parent / "assets"

# テーマ → 背景ファイル名のマッピング
BG_MAP: dict[str, str] = {
    "不安":   "long_night_thinking.png",
    "暴落":   "long_night_thinking.png",
    "含み損": "long_night_thinking.png",
    "積立":   "long_lamp_room.png",
    "複利":   "long_lamp_room.png",
    "継続":   "long_lamp_room.png",
    "行動":   "long_door_light.png",
    "利確":   "long_door_light.png",
    "売却":   "long_door_light.png",
    "比較":   "long_waiting_person.png",
    "SNS":    "long_waiting_person.png",
    "退場":   "long_waiting_person.png",
    "余韻":   "long_dawn_road.png",
    "希望":   "long_dawn_road.png",
    "長期":   "long_dawn_road.png",
}
DEFAULT_BG = "long_night_thinking.png"

# ---------- チャンネル名 ----------
CHANNEL_NAME = "ガチホのモチベ"


def generate_note_image(
    title: str,
    subtitle: str,
    output_path: pathlib.Path,
    bg_keyword: str = "",
    bg_path: Optional[pathlib.Path] = None,
) -> Optional[pathlib.Path]:
    """
    note記事のトップ画像を生成する。

    Args:
        title: 見出し（1行、短く）
        subtitle: 補足テキスト（1行）
        output_path: 保存先パス
        bg_keyword: 背景選択キーワード（BG_MAPのキー）
        bg_path: 背景画像を直接指定する場合のパス

    Returns:
        保存したファイルパス。失敗時は None。
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # --- 背景画像 ---
        bg = _load_background(bg_keyword, bg_path)

        # --- 暗くぼかす ---
        bg = bg.filter(ImageFilter.GaussianBlur(radius=3))
        bg = ImageEnhance.Brightness(bg).enhance(0.35)

        # --- 半透明オーバーレイ ---
        canvas = bg.convert("RGBA")
        overlay = Image.new("RGBA", (NOTE_WIDTH, NOTE_HEIGHT), COLOR_OVERLAY)
        canvas = Image.alpha_composite(canvas, overlay)
        canvas = canvas.convert("RGB")

        draw = ImageDraw.Draw(canvas)

        # --- アクセントライン（左端） ---
        draw.rectangle([(60, 220), (64, 450)], fill=COLOR_ACCENT)

        # --- テキスト描画 ---
        _draw_title(draw, title)
        _draw_subtitle(draw, subtitle)

        # --- チャンネル名（右下） ---
        _draw_channel_name(draw)

        canvas.save(str(output_path), "PNG", optimize=True)
        size_kb = output_path.stat().st_size // 1024
        print(f"  note画像生成完了: {output_path.name}（{size_kb}KB）")
        return output_path

    except Exception as e:
        print(f"  [エラー] note画像生成に失敗: {e}")
        return None


def _load_background(
    keyword: str, explicit_path: Optional[pathlib.Path]
) -> Image.Image:
    """背景画像を読み込み、1280×670にクロップ＆リサイズする。"""
    if explicit_path and explicit_path.exists():
        path = explicit_path
    else:
        filename = BG_MAP.get(keyword, DEFAULT_BG)
        path = ASSETS_DIR / filename

    img = Image.open(path).convert("RGB")

    # 元画像を1280×670のアスペクト比でセンタークロップ
    target_ratio = NOTE_WIDTH / NOTE_HEIGHT
    img_ratio = img.width / img.height

    if img_ratio > target_ratio:
        # 横が余る → 左右をクロップ
        new_w = int(img.height * target_ratio)
        left = (img.width - new_w) // 2
        img = img.crop((left, 0, left + new_w, img.height))
    else:
        # 縦が余る → 上下をクロップ
        new_h = int(img.width / target_ratio)
        top = (img.height - new_h) // 2
        img = img.crop((0, top, img.width, top + new_h))

    img = img.resize((NOTE_WIDTH, NOTE_HEIGHT), Image.LANCZOS)
    return img


def _draw_title(draw: ImageDraw.Draw, text: str):
    """見出しテキストを左寄せで描画する。"""
    font = _load_font(FONT_HEAVY, 52)
    lines = _wrap_lines(text, font, draw, max_width=1060)
    y = 260
    for line in lines:
        draw.text(
            (90, y), line, font=font, fill=COLOR_TITLE,
            stroke_width=2, stroke_fill=(0, 0, 0),
        )
        bbox = draw.textbbox((0, 0), line, font=font)
        y += (bbox[3] - bbox[1]) + 16


def _draw_subtitle(draw: ImageDraw.Draw, text: str):
    """補足テキストを左寄せで描画する。"""
    if not text:
        return
    font = _load_font(FONT_REGULAR, 28)
    draw.text(
        (90, 420), text, font=font, fill=COLOR_SUBTITLE,
        stroke_width=1, stroke_fill=(0, 0, 0),
    )


def _draw_channel_name(draw: ImageDraw.Draw):
    """右下にチャンネル名を控えめに表示する。"""
    font = _load_font(FONT_REGULAR, 20)
    bbox = draw.textbbox((0, 0), CHANNEL_NAME, font=font)
    tw = bbox[2] - bbox[0]
    x = NOTE_WIDTH - tw - 30
    y = NOTE_HEIGHT - 40
    draw.text((x, y), CHANNEL_NAME, font=font, fill=(120, 120, 120))


def _wrap_lines(
    text: str, font, draw: ImageDraw.Draw, max_width: int
) -> list[str]:
    """テキストを最大幅に収まるように折り返す。"""
    if not text:
        return []
    bbox = draw.textbbox((0, 0), text, font=font)
    if (bbox[2] - bbox[0]) <= max_width:
        return [text]

    # 1文字ずつ追加して折り返し位置を決定
    lines = []
    current = ""
    for ch in text:
        test = current + ch
        bbox = draw.textbbox((0, 0), test, font=font)
        if (bbox[2] - bbox[0]) > max_width:
            lines.append(current)
            current = ch
        else:
            current = test
    if current:
        lines.append(current)
    return lines


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    """フォントを読み込む。失敗時はデフォルトフォント。"""
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


# ---------- 15記事分の一括生成 ----------
NOTE_ARTICLES = [
    {"id": "01", "title": "含み損の夜、\n確認回数を減らす",         "subtitle": "見る回数を減らすだけで、眠れる夜が増える", "bg": "含み損"},
    {"id": "02", "title": "積立3年目が\nしんどい理由",              "subtitle": "期待とのズレが、一番地味な時期を作る",     "bg": "積立"},
    {"id": "03", "title": "暴落ニュースの夜、\n思い出す数字",       "subtitle": "15年以上持ち続けた人の過去データ",         "bg": "暴落"},
    {"id": "04", "title": "SNSの爆益を見て\n焦る夜に",              "subtitle": "比較をやめるための、1つの視点",            "bg": "比較"},
    {"id": "05", "title": "利確したい気持ちと、\n複利が止まる感覚", "subtitle": "売った後に何が起きているか",               "bg": "利確"},
    {"id": "06", "title": "毎日口座を\n見てしまう人へ",             "subtitle": "確認するたびに不安が増える理由",           "bg": "不安"},
    {"id": "07", "title": "積立をやめたくなる\n瞬間",               "subtitle": "やめた人がよく口にする後悔",               "bg": "積立"},
    {"id": "08", "title": "暴落から1年、\n売らなかった人の数字",    "subtitle": "底値で持ち続けた人が受け取った回復",       "bg": "暴落"},
    {"id": "09", "title": "20年続けた場合の\n元本割れ確率",         "subtitle": "含み損で眠れない夜に思い出す数字",         "bg": "長期"},
    {"id": "10", "title": "初めての暴落で\n売りたくなった夜",       "subtitle": "その気持ちは、正常です",                   "bg": "不安"},
    {"id": "11", "title": "下がった時こそ\n多く買える",             "subtitle": "ドルコスト平均法の「安く買える期間」",     "bg": "積立"},
    {"id": "12", "title": "「増えてない」と感じる\n10年間",         "subtitle": "複利は静かに動いている",                   "bg": "複利"},
    {"id": "13", "title": "退場しない人が\nやっていること",         "subtitle": "特別なことは、たぶん何もない",             "bg": "退場"},
    {"id": "14", "title": "つい売ってしまった人の\n共通点",         "subtitle": "直前にやっていたこと",                     "bg": "売却"},
    {"id": "15", "title": "バフェットの「退潮時」\nという言葉",     "subtitle": "含み損の夜に読む意味",                     "bg": "余韻"},
]


def generate_all(output_dir: pathlib.Path | str = "note_images") -> list[pathlib.Path]:
    """15記事分のnoteトップ画像を一括生成する。"""
    out = pathlib.Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for art in NOTE_ARTICLES:
        path = out / f"note_{art['id']}.png"
        result = generate_note_image(
            title=art["title"],
            subtitle=art["subtitle"],
            output_path=path,
            bg_keyword=art["bg"],
        )
        if result:
            results.append(result)
    print(f"\n合計 {len(results)}/{len(NOTE_ARTICLES)} 枚生成完了")
    return results


if __name__ == "__main__":
    generate_all()
