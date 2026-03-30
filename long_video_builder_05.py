"""
long_video_builder_05.py
5本目「一括投資か積立投資かで揺れる人へ」の長尺動画を生成する。

long_video_builder.py のモジュール定数を上書きしてから関数を呼ぶ。
"""
from __future__ import annotations

import json
import pathlib
import random

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

BASE_DIR = pathlib.Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
LONG_DIR = BASE_DIR / "long_video" / "05_ikkatsu_tsumitate"
PHOTOS_DIR = ASSETS_DIR / "photos"

THUMB_WIDTH = 1280
THUMB_HEIGHT = 720

FONT_HEAVY = "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"

TITLE = "一括投資か積立投資かで揺れる人へ｜決める前に分けておきたい不安"
DESCRIPTION = (
    "まとまったお金がある。一括で入れたほうが得かもしれない。\n"
    "でも、入れた直後に下がったら怖い。\n\n"
    "この動画では、一括投資が怖い理由と、積立投資で不安になる理由を静かに整理します。\n"
    "バンガード社のレポートや過去のデータを使いながら、\n"
    "どちらが正解かではなく、何が怖くて迷っているのかを言葉にしていきます。\n\n"
    "長期投資 / 積立投資 / NISA / 資産形成 を前提にした内容です。\n\n"
    "※投資助言ではありません\n"
    "※特定の金融商品の購入・売却を勧めるものではありません\n\n"
    "YouTube Shorts「ガチホのモチベ」では、\n"
    "長期投資を続けるモチベーションを毎日投稿しています。\n\n"
    "#一括投資 #積立投資 #NISA #長期投資 #資産形成 #ガチホ"
)
TAGS = [
    "一括投資", "積立投資", "NISA", "長期投資",
    "資産形成", "投資信託", "S&P500", "ガチホのモチベ",
]

# 音声パス（8セクション）
ROLE_AUDIO_05 = {
    "hook": LONG_DIR / "audio" / "01_hook.mp3",
    "overview": LONG_DIR / "audio" / "02_overview.mp3",
    "why_painful": LONG_DIR / "audio" / "03_why_painful.mp3",
    "data": LONG_DIR / "audio" / "04_data.mp3",
    "interpret": LONG_DIR / "audio" / "05_interpret.mp3",
    "data2": LONG_DIR / "audio" / "06_data2.mp3",
    "action": LONG_DIR / "audio" / "07_action.mp3",
    "closing": LONG_DIR / "audio" / "08_closing.mp3",
}

ROLE_ORDER = [
    "hook", "overview", "why_painful", "data",
    "interpret", "data2", "action", "closing",
]


def _pick_photo(category: str) -> pathlib.Path:
    """横長（landscape）の写真のみ選択する。"""
    cat_dir = PHOTOS_DIR / category
    blacklist_dir = cat_dir / "blacklist"
    all_photos = [
        p for p in sorted(cat_dir.glob("*.jpg"))
        if not str(p).startswith(str(blacklist_dir))
    ]
    landscape = []
    for p in all_photos:
        with Image.open(p) as img:
            if img.width >= img.height:
                landscape.append(p)
    if not landscape:
        landscape = all_photos
    return random.choice(landscape)


# 背景画像 — セクション内でも画像を変えて飽きさせない
ROLE_BG_05 = {
    "hook": _pick_photo("anxiety"),
    "overview": _pick_photo("recovery"),
    "why_painful": _pick_photo("comparison"),
    "data": _pick_photo("data"),
    "interpret": _pick_photo("steady"),
    "data2": _pick_photo("data"),
    "action": _pick_photo("recovery"),
    "closing": _pick_photo("steady"),
}

# 長いセクション用に追加の背景画像（同じロール内で切り替える）
ROLE_BG_ALT_05 = {
    "why_painful": [_pick_photo("anxiety"), _pick_photo("comparison"), _pick_photo("anxiety")],
    "interpret": [_pick_photo("recovery"), _pick_photo("steady")],
    "data2": [_pick_photo("steady"), _pick_photo("data")],
    "action": [_pick_photo("steady"), _pick_photo("recovery")],
    "closing": [_pick_photo("recovery"), _pick_photo("steady")],
}

# ズーム方向
ROLE_ZOOM_DIR_05 = {
    "hook": "in",
    "overview": "in",
    "why_painful": "in",
    "data": "in",
    "interpret": "out",
    "data2": "in",
    "action": "out",
    "closing": "out",
}

# パン方向
ROLE_PAN_DIR_05 = {
    "hook": "left_to_right",
    "overview": "center",
    "why_painful": "right_to_left",
    "data": "bottom_to_top",
    "interpret": "center",
    "data2": "left_to_right",
    "action": "top_to_bottom",
    "closing": "center",
}

# ストーリーボード（26枚）
# bg_idx: ROLE_BG_ALT_05 のインデックス（省略時はROLE_BG_05を使用）
STORYBOARD = [
    # hook — 3枚（21秒）
    {"role": "hook", "title": "一括投資？\n積立投資？", "body": "", "share": 1.0, "layout": "full"},
    {"role": "hook", "title": "入れた直後に\n下がったら", "body": "", "share": 1.0, "layout": "full"},
    {"role": "hook", "title": "今日は整理する", "body": "この迷いを静かに", "share": 1.0, "layout": "corner"},

    # overview — 2枚（21秒）
    {"role": "overview", "title": "どちらが得か\nではなく", "body": "", "share": 1.0, "layout": "full"},
    {"role": "overview", "title": "怖い理由と\n不安になる理由", "body": "", "share": 1.0, "layout": "full"},

    # why_painful — 5枚（64秒）— 画像を切り替えて飽きさせない
    {"role": "why_painful", "title": "一括の恐怖", "body": "入れた直後に沈む", "share": 1.0, "layout": "corner"},
    {"role": "why_painful", "title": "5万円が\n一晩で消える", "body": "", "share": 0.8, "layout": "full", "bg_idx": 0},
    {"role": "why_painful", "title": "積立の不安", "body": "上がる相場を見ている", "share": 1.0, "layout": "corner", "bg_idx": 1},
    {"role": "why_painful", "title": "どちらを選んでも\nゆれる瞬間がある", "body": "", "share": 1.0, "layout": "full", "bg_idx": 2},
    {"role": "why_painful", "title": "手放した選択肢が\nよく見えやすい", "body": "", "share": 0.8, "layout": "full", "bg_idx": 2},

    # data — 3枚（41秒）— number レイアウトは1行titleに修正
    {"role": "data", "title": "約2/3で一括が優勢", "body": "バンガード社 2012年", "share": 1.0, "layout": "number"},
    {"role": "data", "title": "残り1/3は積立", "body": "直後に下がった時期", "share": 1.0, "layout": "number"},
    {"role": "data", "title": "どちらにも\n合理的な根拠", "body": "", "share": 1.0, "layout": "full"},

    # interpret — 3枚（55秒）— 画像切り替え
    {"role": "interpret", "title": "2/3勝てても\n1/3が怖い", "body": "", "share": 1.0, "layout": "full"},
    {"role": "interpret", "title": "損失回避", "body": "得より損を2倍重く感じる", "share": 1.0, "layout": "corner", "bg_idx": 0},
    {"role": "interpret", "title": "どちらを選んでも\n根拠はある", "body": "", "share": 1.0, "layout": "full", "bg_idx": 1},

    # data2 — 3枚（59秒）— 画像切り替え
    {"role": "data2", "title": "20年保有で回復", "body": "過去の長期データ", "share": 1.0, "layout": "number"},
    {"role": "data2", "title": "一括の強さ", "body": "早く市場に入る", "share": 1.0, "layout": "corner", "bg_idx": 0},
    {"role": "data2", "title": "積立の強さ", "body": "買い続けて単価を下げる", "share": 1.0, "layout": "corner", "bg_idx": 1},

    # action — 3枚（59秒）— 画像切り替え
    {"role": "action", "title": "どちらの不安が\n強いか", "body": "", "share": 1.0, "layout": "full"},
    {"role": "action", "title": "一行だけ\n書いてみる", "body": "", "share": 1.0, "layout": "full", "bg_idx": 0},
    {"role": "action", "title": "二択のまま\n抱え込まない", "body": "", "share": 1.0, "layout": "full", "bg_idx": 1},

    # closing — 3枚（45秒）— テキストを音声に合わせる
    {"role": "closing", "title": "今日すぐ\n答えを出さなくていい", "body": "", "share": 1.2, "layout": "full"},
    {"role": "closing", "title": "迷いを整える", "body": "毎日やっています", "share": 0.8, "layout": "corner", "bg_idx": 0},
    {"role": "closing", "title": "ガチホのモチベ", "body": "", "share": 1.0, "layout": "full", "bg_idx": 1},
]


def _render_thumbnail(output_path: pathlib.Path):
    bg_path = _pick_photo("comparison")
    print(f"サムネ背景: {bg_path}")
    bg = Image.open(bg_path).convert("RGB")

    target_ratio = THUMB_WIDTH / THUMB_HEIGHT
    img_ratio = bg.width / bg.height
    if img_ratio > target_ratio:
        crop_h = bg.height
        crop_w = int(crop_h * target_ratio)
    else:
        crop_w = bg.width
        crop_h = int(crop_w / target_ratio)
    left = (bg.width - crop_w) // 2
    top = (bg.height - crop_h) // 2
    bg = bg.crop((left, top, left + crop_w, top + crop_h))
    bg = bg.resize((THUMB_WIDTH, THUMB_HEIGHT), Image.LANCZOS)

    bg = bg.filter(ImageFilter.GaussianBlur(radius=1))
    bg = ImageEnhance.Brightness(bg).enhance(0.80)
    bg = bg.convert("RGBA")
    overlay = Image.new("RGBA", (THUMB_WIDTH, THUMB_HEIGHT), (15, 20, 40, 40))
    bg = Image.alpha_composite(bg, overlay).convert("RGB")

    draw = ImageDraw.Draw(bg)

    thumb_font_w8 = "/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc"
    main_font = ImageFont.truetype(thumb_font_w8, 126)
    sub_font = ImageFont.truetype(FONT_HEAVY, 62)

    main_lines = ["一括か積立か", "揺れる人へ"]
    sub_text = "決める前に分けておきたい不安"

    text_x = 60
    y = 140
    for line in main_lines:
        draw.text(
            (text_x, y), line, font=main_font, fill=(255, 210, 50),
            stroke_width=7, stroke_fill=(0, 0, 0),
        )
        y += 145

    sub_y = y + 15
    draw.text(
        (text_x, sub_y), sub_text, font=sub_font, fill=(255, 255, 255),
        stroke_width=4, stroke_fill=(0, 0, 0),
    )

    bg.save(str(output_path), "PNG", optimize=True)
    print(f"サムネイル生成: {output_path}")


def main():
    import long_video_builder as lvb

    # long_video_builder のモジュール定数を5本目用に上書き
    lvb.LONG_DIR = LONG_DIR
    lvb.SLIDES_DIR = LONG_DIR / "slides"
    lvb.OVERLAYS_DIR = LONG_DIR / "overlays"
    lvb.OUTPUT_VIDEO = LONG_DIR / "output.mp4"
    lvb.OUTPUT_THUMB = LONG_DIR / "thumbnail.png"
    lvb.OUTPUT_META = LONG_DIR / "video_meta.json"
    lvb.ROLE_AUDIO = ROLE_AUDIO_05
    lvb.ROLE_BG = ROLE_BG_05
    lvb.ROLE_ZOOM_DIR = ROLE_ZOOM_DIR_05
    lvb.ROLE_PAN_DIR = ROLE_PAN_DIR_05
    lvb.TITLE = TITLE
    lvb.DESCRIPTION = DESCRIPTION
    lvb.TAGS = TAGS
    lvb.ZOOM_RATIO = 0.07

    orig_accent = lvb._accent_color

    def _accent_color_extended(role: str):
        if role == "data2":
            return (100, 190, 255)
        return orig_accent(role)

    lvb._accent_color = _accent_color_extended

    slides_dir = LONG_DIR / "slides"
    overlays_dir = LONG_DIR / "overlays"
    slides_dir.mkdir(parents=True, exist_ok=True)
    overlays_dir.mkdir(parents=True, exist_ok=True)

    # ストーリーボードにdurationを付与
    cards_by_role: dict[str, list[dict]] = {}
    for card in STORYBOARD:
        cards_by_role.setdefault(card["role"], []).append(dict(card))

    resolved: list[dict] = []
    for role in ROLE_ORDER:
        cards = cards_by_role.get(role, [])
        if not cards:
            continue
        total_duration = lvb._audio_duration(ROLE_AUDIO_05[role])
        total_share = sum(c.get("share", 1.0) for c in cards)
        assigned = 0.0
        for index, card in enumerate(cards):
            new_card = dict(card)
            # bg_idx があれば代替写真を使用（同じセクション内で画像を変える）
            bg_idx = new_card.pop("bg_idx", None)
            if bg_idx is not None and role in ROLE_BG_ALT_05:
                alts = ROLE_BG_ALT_05[role]
                new_card["bg_path"] = str(alts[bg_idx % len(alts)])
            else:
                new_card["bg_path"] = str(ROLE_BG_05.get(role, ROLE_BG_05["hook"]))
            if index == len(cards) - 1:
                duration = total_duration - assigned
            else:
                duration = round(total_duration * card.get("share", 1.0) / total_share, 6)
                assigned += duration
            new_card["duration"] = duration
            resolved.append(new_card)

    # スライド生成
    background_paths = []
    overlay_paths = []
    for index, card in enumerate(resolved, start=1):
        bg_path = slides_dir / f"{index:02d}_{card['role']}.png"
        ov_path = overlays_dir / f"{index:02d}_{card['role']}.png"
        lvb._render_slide_layers(card, bg_path, ov_path)
        background_paths.append(bg_path)
        overlay_paths.append(ov_path)

    # サムネイル
    _render_thumbnail(LONG_DIR / "thumbnail.png")

    # 動画合成
    output_path = lvb._compose_video(resolved, background_paths, overlay_paths)

    # メタデータ
    meta = {
        "title": TITLE,
        "description": DESCRIPTION,
        "tags": TAGS,
        "video_path": str(output_path),
        "thumbnail_path": str(LONG_DIR / "thumbnail.png"),
        "slides": [
            {
                "role": card["role"],
                "title": card["title"],
                "duration": card["duration"],
                "slide_path": str(bg),
                "overlay_path": str(ov),
            }
            for card, bg, ov in zip(resolved, background_paths, overlay_paths)
        ],
        "thumbnail": {
            "source_photo_path": str(ROLE_BG_05["comparison"] if "comparison" in ROLE_BG_05 else ""),
            "main_text": "一括か積立か\n揺れる人へ",
            "sub_text": "決める前に分けておきたい不安",
            "font_size_main": 96,
            "font_size_sub": 40,
        },
    }
    (LONG_DIR / "video_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n動画生成完了: {output_path}")


if __name__ == "__main__":
    main()
