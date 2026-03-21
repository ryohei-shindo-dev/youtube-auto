"""
long_video_builder_04.py
4本目「配当株とインデックスで揺れる人へ」の長尺動画を生成する。

long_video_builder.py のモジュール定数を上書きしてから関数を呼ぶ。
"""
from __future__ import annotations

import json
import pathlib
import random

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

BASE_DIR = pathlib.Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
LONG_DIR = BASE_DIR / "long_video" / "04_haitou_index"
PHOTOS_DIR = ASSETS_DIR / "photos"

THUMB_WIDTH = 1280
THUMB_HEIGHT = 720

FONT_HEAVY = "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"

TITLE = "高配当株とインデックスで揺れる人へ｜最初に整理したいちがい"
DESCRIPTION = (
    "高配当株とインデックスで揺れるとき、比べているのは商品だけではなく、安心の形かもしれません。\n\n"
    "この動画では、高配当株に安心を感じる理由と、インデックスに安心を感じる理由を静かに整理します。\n"
    "VOO（インデックスETF）とVYM（高配当ETF）の利回りや長期リターンの違いを見ながら、\n"
    "どちらが上かではなく、何に安心したくて迷っているのかを言葉にしていきます。\n\n"
    "長期投資 / 積立投資 / NISA / 資産形成 を前提にした内容です。\n\n"
    "※投資助言ではありません\n"
    "※特定の金融商品の購入・売却を勧めるものではありません\n\n"
    "YouTube Shorts「ガチホのモチベ」では、\n"
    "長期投資を続けるモチベーションを毎日投稿しています。\n\n"
    "#配当株 #インデックス投資 #高配当 #NISA #長期投資 #資産形成 #ガチホ"
)
TAGS = [
    "配当株", "インデックス投資", "高配当", "NISA",
    "長期投資", "資産形成", "投資信託", "VOO", "VYM", "ガチホのモチベ",
]

# 4本目の音声パス（8セクション: data2 が新規）
ROLE_AUDIO_04 = {
    "hook": LONG_DIR / "audio" / "01_hook.mp3",
    "overview": LONG_DIR / "audio" / "02_overview.mp3",
    "why_painful": LONG_DIR / "audio" / "03_why_painful.mp3",
    "data": LONG_DIR / "audio" / "04_data.mp3",
    "interpret": LONG_DIR / "audio" / "05_interpret.mp3",
    "data2": LONG_DIR / "audio" / "06_data2.mp3",
    "action": LONG_DIR / "audio" / "07_action.mp3",
    "closing": LONG_DIR / "audio" / "08_closing.mp3",
}

# ロールの処理順（data2 を含む）
ROLE_ORDER = [
    "hook", "overview", "why_painful", "data",
    "interpret", "data2", "action", "closing",
]


def _pick_photo(category: str) -> pathlib.Path:
    cat_dir = PHOTOS_DIR / category
    blacklist_dir = cat_dir / "blacklist"
    photos = [
        p for p in sorted(cat_dir.glob("*.jpg"))
        if not str(p).startswith(str(blacklist_dir))
    ]
    if not photos:
        photos = sorted(cat_dir.glob("*.jpg"))
    return random.choice(photos)


# 背景画像
ROLE_BG_04 = {
    "hook": _pick_photo("comparison"),
    "overview": _pick_photo("recovery"),
    "why_painful": _pick_photo("comparison"),
    "data": _pick_photo("data"),
    "interpret": _pick_photo("recovery"),
    "data2": _pick_photo("data"),
    "action": _pick_photo("steady"),
    "closing": _pick_photo("recovery"),
}

# ズーム方向（data2 追加）
ROLE_ZOOM_DIR_04 = {
    "hook": "in",
    "overview": "in",
    "why_painful": "in",
    "data": "in",
    "interpret": "out",
    "data2": "in",
    "action": "out",
    "closing": "out",
}

# パン方向（data2 追加）
ROLE_PAN_DIR_04 = {
    "hook": "left_to_right",
    "overview": "center",
    "why_painful": "right_to_left",
    "data": "bottom_to_top",
    "interpret": "center",
    "data2": "left_to_right",
    "action": "top_to_bottom",
    "closing": "center",
}

# ストーリーボード（26枚: 各セクション2〜5枚）
# スライドテキスト: 漢字とひらがなのバランスに注意
# ゆれる/おだやか はひらがなOK、感じる/実感/続ける/選ぶ/決める は漢字
STORYBOARD = [
    # hook — 3枚
    {"role": "hook", "title": "高配当株？\nインデックス？", "body": "", "share": 1.0, "layout": "full"},
    {"role": "hook", "title": "比べているのは", "body": "商品だけではない", "share": 1.0, "layout": "corner"},
    {"role": "hook", "title": "今日は整理する", "body": "その違いを静かに", "share": 1.0, "layout": "corner"},

    # overview — 2枚
    {"role": "overview", "title": "どちらが上か\nではなく", "body": "", "share": 1.0, "layout": "full"},
    {"role": "overview", "title": "安心を感じる\n理由の違い", "body": "", "share": 1.0, "layout": "full"},

    # why_painful — 5枚
    {"role": "why_painful", "title": "入金の実感", "body": "高配当株の安心", "share": 1.0, "layout": "corner"},
    {"role": "why_painful", "title": "続けやすさ", "body": "インデックスの安心", "share": 1.0, "layout": "corner"},
    {"role": "why_painful", "title": "どちらを選んでも\nゆれる", "body": "", "share": 1.0, "layout": "full"},
    {"role": "why_painful", "title": "選ばなかったほうが\nよく見える", "body": "", "share": 1.0, "layout": "full"},
    {"role": "why_painful", "title": "不安が形を変えて\n続いている", "body": "", "share": 1.0, "layout": "full"},

    # data — 4枚
    {"role": "data", "title": "VOO 1.09%", "body": "インデックスETF\n分配利回りの目安", "share": 1.0, "layout": "number"},
    {"role": "data", "title": "VYM 2.29%", "body": "高配当ETF\n分配利回りの目安", "share": 1.0, "layout": "number"},
    {"role": "data", "title": "受け取り方の\n違い", "body": "", "share": 1.0, "layout": "full"},
    {"role": "data", "title": "優劣ではなく\n形の違い", "body": "", "share": 1.0, "layout": "full"},

    # interpret — 3枚
    {"role": "interpret", "title": "安心の形を\n比べている", "body": "", "share": 1.0, "layout": "full"},
    {"role": "interpret", "title": "入金の安心か\n続けやすい安心か", "body": "", "share": 1.0, "layout": "full"},
    {"role": "interpret", "title": "軸が見えると\n気持ちが少し静まる", "body": "", "share": 1.0, "layout": "full"},

    # data2 — 3枚
    {"role": "data2", "title": "VOO 14.78%", "body": "インデックスETF\n10年平均年率", "share": 1.0, "layout": "number"},
    {"role": "data2", "title": "VYM 11.32%", "body": "高配当ETF\n10年平均年率", "share": 1.0, "layout": "number"},
    {"role": "data2", "title": "今の安心か\n長く持つ安心か", "body": "", "share": 1.0, "layout": "full"},

    # action — 3枚
    {"role": "action", "title": "何に安心したいか", "body": "", "share": 1.0, "layout": "full"},
    {"role": "action", "title": "迷いの正体が\n見えてくる", "body": "", "share": 1.0, "layout": "full"},
    {"role": "action", "title": "今すぐ\n乗り換えなくていい", "body": "", "share": 1.0, "layout": "full"},

    # closing — 3枚
    {"role": "closing", "title": "今日\n決めなくていい", "body": "", "share": 1.0, "layout": "full"},
    {"role": "closing", "title": "比べ方が\n静かになる", "body": "", "share": 1.2, "layout": "full"},
    {"role": "closing", "title": "それで十分", "body": "", "share": 0.8, "layout": "full"},
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
    bg = ImageEnhance.Brightness(bg).enhance(0.65)
    bg = bg.convert("RGBA")
    overlay = Image.new("RGBA", (THUMB_WIDTH, THUMB_HEIGHT), (15, 20, 40, 60))
    bg = Image.alpha_composite(bg, overlay).convert("RGB")

    draw = ImageDraw.Draw(bg)
    font = ImageFont.truetype(FONT_HEAVY, 64)

    lines = ["高配当株か", "インデックスか"]
    line_height = 90
    y_start = (THUMB_HEIGHT - len(lines) * line_height) // 2
    for i, line in enumerate(lines):
        y = y_start + i * line_height
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (THUMB_WIDTH - tw) // 2
        for dx, dy in [(3, 3), (2, 2)]:
            draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=(255, 255, 255))

    bg.save(str(output_path), "PNG", optimize=True)
    print(f"サムネイル生成: {output_path}")


def main():
    import long_video_builder as lvb

    # ★ long_video_builder のモジュール定数を4本目用に上書き ★
    lvb.LONG_DIR = LONG_DIR
    lvb.SLIDES_DIR = LONG_DIR / "slides"
    lvb.OVERLAYS_DIR = LONG_DIR / "overlays"
    lvb.OUTPUT_VIDEO = LONG_DIR / "output.mp4"
    lvb.OUTPUT_THUMB = LONG_DIR / "thumbnail.png"
    lvb.OUTPUT_META = LONG_DIR / "video_meta.json"
    lvb.ROLE_AUDIO = ROLE_AUDIO_04
    lvb.ROLE_BG = ROLE_BG_04
    lvb.ROLE_ZOOM_DIR = ROLE_ZOOM_DIR_04
    lvb.ROLE_PAN_DIR = ROLE_PAN_DIR_04
    lvb.TITLE = TITLE
    lvb.DESCRIPTION = DESCRIPTION
    lvb.TAGS = TAGS
    # Ken Burns の動きを大きくする（0.035 → 0.07）
    lvb.ZOOM_RATIO = 0.07

    # data2 のアクセントカラーを追加
    orig_accent = lvb._accent_color

    def _accent_color_extended(role: str):
        if role == "data2":
            return (100, 190, 255)  # data と同じ青系
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
        total_duration = lvb._audio_duration(ROLE_AUDIO_04[role])
        total_share = sum(c.get("share", 1.0) for c in cards)
        assigned = 0.0
        for index, card in enumerate(cards):
            new_card = dict(card)
            new_card["bg_path"] = str(ROLE_BG_04.get(role, ROLE_BG_04["hook"]))
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
    }
    (LONG_DIR / "video_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n動画生成完了: {output_path}")
    print(f"サムネイル: {LONG_DIR / 'thumbnail.png'}")


if __name__ == "__main__":
    main()
