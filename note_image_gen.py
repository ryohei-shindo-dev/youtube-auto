"""
note_image_gen.py
note記事のトップ画像（見出し画像）を Pillow で生成するモジュール。

【設計】
  背景: AI生成の基幹ビジュアル（5枚）— 光の1点を残して暗くする
  テキスト: 短い見出し + 補足（レイアウト3型で単調さ回避）
  サイズ: 1280×670px（note推奨）

【レイアウト3型】
  left:     左寄せ大見出し（デフォルト）
  left_sub: 左寄せ + 下補足
  center:   中央寄せ短句

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
COLOR_SUBTITLE = (220, 220, 220)       # 薄グレー（少し明るく）
COLOR_ACCENT = (255, 210, 100)         # 落ち着いた黄
COLOR_OVERLAY = (15, 20, 45, 100)      # 薄いネイビー半透明（写真を活かす）

# ---------- レイアウト型 ----------
LAYOUT_LEFT = "left"           # 左寄せ大見出し
LAYOUT_LEFT_SUB = "left_sub"   # 左寄せ + 下補足
LAYOUT_CENTER = "center"       # 中央寄せ短句

# ---------- 背景写真 ----------
ASSETS_DIR = pathlib.Path(__file__).parent / "assets"
PHOTOS_DIR = ASSETS_DIR / "photos"

# テーマ → 写真カテゴリ（photos/カテゴリ名/ 内からランダム選択）
THEME_TO_PHOTO_CAT: dict[str, str] = {
    "不安":   "anxiety",
    "暴落":   "anxiety",
    "含み損": "anxiety",
    "積立":   "steady",
    "複利":   "data",
    "継続":   "steady",
    "行動":   "comparison",
    "利確":   "comparison",
    "売却":   "comparison",
    "比較":   "comparison",
    "SNS":    "comparison",
    "退場":   "anxiety",
    "余韻":   "recovery",
    "希望":   "recovery",
    "長期":   "data",
}
DEFAULT_PHOTO_CAT = "anxiety"


def generate_note_image(
    title: str,
    subtitle: str,
    output_path: pathlib.Path,
    bg_keyword: str = "",
    bg_path: Optional[pathlib.Path] = None,
    layout: str = LAYOUT_LEFT_SUB,
) -> Optional[pathlib.Path]:
    """
    note記事のトップ画像を生成する。

    Args:
        title: 見出し（短く、8〜14字目安）
        subtitle: 補足テキスト（1行）
        output_path: 保存先パス
        bg_keyword: 背景選択キーワード（BG_MAPのキー）
        bg_path: 背景画像を直接指定する場合のパス
        layout: レイアウト型（LAYOUT_LEFT / LAYOUT_LEFT_SUB / LAYOUT_CENTER）

    Returns:
        保存したファイルパス。失敗時は None。
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # --- 背景画像 ---
        bg = _load_background(bg_keyword, bg_path)

        # --- 写真を活かす処理（暗くしすぎない） ---
        bg = bg.filter(ImageFilter.GaussianBlur(radius=1))
        bg = ImageEnhance.Color(bg).enhance(0.85)        # 彩度を少し落とす
        bg = ImageEnhance.Brightness(bg).enhance(0.75)    # 暗さ控えめ

        # --- 半透明オーバーレイ ---
        canvas = bg.convert("RGBA")
        overlay = Image.new("RGBA", (NOTE_WIDTH, NOTE_HEIGHT), COLOR_OVERLAY)
        canvas = Image.alpha_composite(canvas, overlay)
        canvas = canvas.convert("RGB")

        draw = ImageDraw.Draw(canvas)

        # --- レイアウト別描画 ---
        if layout == LAYOUT_CENTER:
            _draw_center_layout(draw, title, subtitle)
        elif layout == LAYOUT_LEFT:
            _draw_left_layout(draw, title)
        else:
            _draw_left_sub_layout(draw, title, subtitle)

        canvas.save(str(output_path), "PNG", optimize=True)
        size_kb = output_path.stat().st_size // 1024
        print(f"  note画像生成完了: {output_path.name}（{size_kb}KB）")
        return output_path

    except Exception as e:
        print(f"  [エラー] note画像生成に失敗: {e}")
        return None


_bg_cache: dict[str, Image.Image] = {}
_cat_index: dict[str, int] = {}  # カテゴリごとの次に使うインデックス


def _pick_photo(category: str) -> pathlib.Path:
    """カテゴリフォルダから写真をローテーション選択する。"""
    cat_dir = PHOTOS_DIR / category
    if not cat_dir.exists():
        cat_dir = PHOTOS_DIR / DEFAULT_PHOTO_CAT
    photos = sorted(cat_dir.glob("*.jpg")) + sorted(cat_dir.glob("*.png"))
    if not photos:
        # フォールバック: 旧背景画像
        return ASSETS_DIR / "long_night_thinking.png"
    idx = _cat_index.get(category, 0)
    path = photos[idx % len(photos)]
    _cat_index[category] = idx + 1
    return path


def _load_background(
    keyword: str, explicit_path: Optional[pathlib.Path]
) -> Image.Image:
    """背景写真を読み込み、1280×670にクロップ＆リサイズする（キャッシュ付き）。"""
    if explicit_path and explicit_path.exists():
        path = explicit_path
    else:
        category = THEME_TO_PHOTO_CAT.get(keyword, DEFAULT_PHOTO_CAT)
        path = _pick_photo(category)

    cache_key = str(path)
    if cache_key in _bg_cache:
        return _bg_cache[cache_key].copy()

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
    _bg_cache[cache_key] = img
    return img.copy()


def _draw_accent_band(draw: ImageDraw.Draw, y_start: int, y_end: int, x: int = 40):
    """左端に黄色の太いアクセント帯を描画する。"""
    draw.rectangle([(x, y_start), (x + 20, y_end)], fill=COLOR_ACCENT)


def _draw_left_sub_layout(draw: ImageDraw.Draw, title: str, subtitle: str):
    """左寄せ + 下補足型（デフォルト）。"""
    # アクセント帯
    _draw_accent_band(draw, 200, 460)

    # 見出し（大きく、太く）
    font_title = _load_font(FONT_HEAVY, 58)
    lines = _wrap_lines(title, font_title, draw, max_width=1040)
    y = 240
    for line in lines:
        draw.text(
            (90, y), line, font=font_title, fill=COLOR_TITLE,
            stroke_width=2, stroke_fill=(0, 0, 0),
        )
        bbox = draw.textbbox((0, 0), line, font=font_title)
        y += (bbox[3] - bbox[1]) + 18

    # 補足テキスト
    if subtitle:
        font_sub = _load_font(FONT_REGULAR, 28)
        draw.text(
            (90, y + 24), subtitle, font=font_sub, fill=COLOR_SUBTITLE,
            stroke_width=1, stroke_fill=(0, 0, 0),
        )


def _draw_left_layout(draw: ImageDraw.Draw, title: str):
    """左寄せ大見出し型（補足なし、タイトルだけ大きく）。"""
    # アクセント帯
    _draw_accent_band(draw, 220, 440)

    font_title = _load_font(FONT_HEAVY, 64)
    lines = _wrap_lines(title, font_title, draw, max_width=1040)
    # 垂直中央寄せ
    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font_title)
        line_heights.append(bbox[3] - bbox[1])
    total_h = sum(line_heights) + 20 * (len(lines) - 1) if lines else 0
    y = (NOTE_HEIGHT - total_h) // 2

    for i, line in enumerate(lines):
        draw.text(
            (90, y), line, font=font_title, fill=COLOR_TITLE,
            stroke_width=3, stroke_fill=(0, 0, 0),
        )
        y += line_heights[i] + 20


def _draw_center_layout(draw: ImageDraw.Draw, title: str, subtitle: str):
    """中央寄せ短句型。"""
    # アクセント帯なし（中央配置では左帯が邪魔）
    # 代わりに見出しの下に短い黄色ライン
    font_title = _load_font(FONT_HEAVY, 62)
    lines = _wrap_lines(title, font_title, draw, max_width=1000)

    # 垂直中央寄せ
    line_heights = []
    line_widths = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font_title)
        line_heights.append(bbox[3] - bbox[1])
        line_widths.append(bbox[2] - bbox[0])
    total_h = sum(line_heights) + 20 * (len(lines) - 1) if lines else 0
    y = (NOTE_HEIGHT - total_h) // 2 - 30

    for i, line in enumerate(lines):
        x = (NOTE_WIDTH - line_widths[i]) // 2
        draw.text(
            (x, y), line, font=font_title, fill=COLOR_TITLE,
            stroke_width=3, stroke_fill=(0, 0, 0),
        )
        y += line_heights[i] + 20

    # 中央の短い黄色アクセントライン
    line_y = y + 10
    draw.rectangle(
        [(NOTE_WIDTH // 2 - 40, line_y), (NOTE_WIDTH // 2 + 40, line_y + 4)],
        fill=COLOR_ACCENT,
    )

    # 補足テキスト（中央寄せ）
    if subtitle:
        font_sub = _load_font(FONT_REGULAR, 26)
        bbox = draw.textbbox((0, 0), subtitle, font=font_sub)
        sw = bbox[2] - bbox[0]
        sx = (NOTE_WIDTH - sw) // 2
        draw.text(
            (sx, line_y + 24), subtitle, font=font_sub, fill=COLOR_SUBTITLE,
            stroke_width=1, stroke_fill=(0, 0, 0),
        )


def _wrap_lines(
    text: str, font, draw: ImageDraw.Draw, max_width: int
) -> list[str]:
    """テキストを最大幅に収まるように折り返す。明示的な改行(\n)も尊重する。"""
    if not text:
        return []

    # 明示的な改行を先に分割
    result: list[str] = []
    for segment in text.split("\n"):
        segment = segment.strip()
        if not segment:
            continue
        bbox = draw.textbbox((0, 0), segment, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            result.append(segment)
        else:
            # 1文字ずつ追加して折り返し位置を決定
            current = ""
            for ch in segment:
                test = current + ch
                bbox = draw.textbbox((0, 0), test, font=font)
                if (bbox[2] - bbox[0]) > max_width:
                    result.append(current)
                    current = ch
                else:
                    current = test
            if current:
                result.append(current)
    return result


_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    """フォントを読み込む（キャッシュ付き）。失敗時はデフォルトフォント。"""
    key = (path, size)
    if key in _font_cache:
        return _font_cache[key]
    try:
        font = ImageFont.truetype(path, size)
    except Exception:
        font = ImageFont.load_default()
    _font_cache[key] = font
    return font


# ---------- 全27記事分の一括生成 ----------
# 見出しは8〜14字目安（短く、止める力を優先）
# layout: left / left_sub / center をローテーションして一覧の単調さを回避

# 第1弾（note_01〜15）
NOTE_ARTICLES_BATCH1 = [
    {"id": "01", "title": "含み損の夜に",               "subtitle": "確認回数を減らすだけで変わること",     "bg": "含み損", "layout": LAYOUT_LEFT_SUB},
    {"id": "02", "title": "積立3年目の壁",              "subtitle": "一番地味な時期をどう越えるか",         "bg": "積立",   "layout": LAYOUT_CENTER},
    {"id": "03", "title": "暴落の夜に\n思い出す数字",   "subtitle": "15年持ち続けた人のデータ",             "bg": "暴落",   "layout": LAYOUT_LEFT},
    {"id": "04", "title": "爆益を見て焦る夜",           "subtitle": "比較をやめるための1つの視点",          "bg": "比較",   "layout": LAYOUT_LEFT_SUB},
    {"id": "05", "title": "利確と複利の境目",           "subtitle": "売った後に起きていること",             "bg": "利確",   "layout": LAYOUT_CENTER},
    {"id": "06", "title": "毎日口座を見る人へ",         "subtitle": "確認するたび不安が増える理由",         "bg": "不安",   "layout": LAYOUT_LEFT},
    {"id": "07", "title": "積立をやめたくなる瞬間",     "subtitle": "やめた人が口にする後悔",               "bg": "積立",   "layout": LAYOUT_LEFT_SUB},
    {"id": "08", "title": "暴落から1年後",              "subtitle": "売らなかった人が受け取った数字",       "bg": "暴落",   "layout": LAYOUT_CENTER},
    {"id": "09", "title": "20年と元本割れ",             "subtitle": "眠れない夜に思い出す数字",             "bg": "長期",   "layout": LAYOUT_LEFT},
    {"id": "10", "title": "初めての暴落の夜",           "subtitle": "売りたくなるのは正常です",             "bg": "不安",   "layout": LAYOUT_LEFT_SUB},
    {"id": "11", "title": "下がった時こそ",             "subtitle": "ドルコスト平均法の安く買える期間",     "bg": "積立",   "layout": LAYOUT_CENTER},
    {"id": "12", "title": "増えない10年間",             "subtitle": "複利は静かに動いている",               "bg": "複利",   "layout": LAYOUT_LEFT},
    {"id": "13", "title": "退場しない人の共通点",       "subtitle": "特別なことは何もない",                 "bg": "退場",   "layout": LAYOUT_LEFT_SUB},
    {"id": "14", "title": "つい売った人へ",             "subtitle": "直前にやっていたこと",                 "bg": "売却",   "layout": LAYOUT_CENTER},
    {"id": "15", "title": "バフェットの退潮時",         "subtitle": "含み損の夜に読む意味",                 "bg": "余韻",   "layout": LAYOUT_LEFT},
]

# 第2弾（note_16〜27）
NOTE_ARTICLES_BATCH2 = [
    {"id": "16", "title": "新NISAをやめたい夜",         "subtitle": "1〜2年目の離脱が一番多い傾向",         "bg": "不安",   "layout": LAYOUT_CENTER},
    {"id": "17", "title": "含み益なのに不安",           "subtitle": "利益が出ている状態ほど揺れやすい",     "bg": "含み損", "layout": LAYOUT_LEFT},
    {"id": "18", "title": "始めるのが遅かった夜",       "subtitle": "遅れたと感じるときの整理法",           "bg": "長期",   "layout": LAYOUT_LEFT_SUB},
    {"id": "19", "title": "老後資金が不安な夜",         "subtitle": "間に合わない気がするときの数字",       "bg": "不安",   "layout": LAYOUT_CENTER},
    {"id": "20", "title": "一括投資が怖い理由",         "subtitle": "怖さの中身を分けると整理しやすい",     "bg": "行動",   "layout": LAYOUT_LEFT},
    {"id": "21", "title": "今買って大丈夫か",           "subtitle": "積立なのに不安になる構造",             "bg": "積立",   "layout": LAYOUT_LEFT_SUB},
    {"id": "22", "title": "買っておけばの夜",           "subtitle": "機会損失の痛みは含み損より深い",       "bg": "含み損", "layout": LAYOUT_CENTER},
    {"id": "23", "title": "円高が怖い夜に",             "subtitle": "20年で見れば薄まりやすい傾向",        "bg": "暴落",   "layout": LAYOUT_LEFT},
    {"id": "24", "title": "一括か積立か",               "subtitle": "迷う人が見落としやすい前提",           "bg": "行動",   "layout": LAYOUT_LEFT_SUB},
    {"id": "25", "title": "現金のままだと",             "subtitle": "何が起きやすいかを数字で見る",         "bg": "長期",   "layout": LAYOUT_CENTER},
    {"id": "26", "title": "積立を止めない意味",         "subtitle": "下がっている時期にこそ効く仕組み",     "bg": "積立",   "layout": LAYOUT_LEFT},
    {"id": "27", "title": "何もしなかった日",           "subtitle": "動かないことは戦略の実行",             "bg": "希望",   "layout": LAYOUT_LEFT_SUB},
]

# 全記事結合
NOTE_ARTICLES = NOTE_ARTICLES_BATCH1 + NOTE_ARTICLES_BATCH2


def generate_all(output_dir: pathlib.Path | str = "note_images") -> list[pathlib.Path]:
    """全27記事分のnoteトップ画像を一括生成する。"""
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
            layout=art.get("layout", LAYOUT_LEFT_SUB),
        )
        if result:
            results.append(result)
    print(f"\n合計 {len(results)}/{len(NOTE_ARTICLES)} 枚生成完了")
    return results


if __name__ == "__main__":
    generate_all()
