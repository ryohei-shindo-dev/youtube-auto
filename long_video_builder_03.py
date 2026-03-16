"""
long_video_builder_03.py
3本目「オルカンとS&P500で揺れる人へ」の長尺動画を生成する。

long_video_builder.py のモジュール定数を上書きしてから関数を呼ぶ。
"""
from __future__ import annotations

import json
import pathlib
import random

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

BASE_DIR = pathlib.Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
LONG_DIR = BASE_DIR / "long_video" / "03_allcountry_sp500"
PHOTOS_DIR = ASSETS_DIR / "photos"

THUMB_WIDTH = 1280
THUMB_HEIGHT = 720

FONT_HEAVY = "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"

TITLE = "オルカンとS&P500で揺れる人へ｜乗り換えたくなるときに整理したいこと"
DESCRIPTION = (
    "オルカンにしたけど、S&P500のほうがよかったんじゃないか。\n"
    "そう思って、また比較して、また揺れる。\n\n"
    "この動画では、なぜ揺れるのか、\n"
    "データで何がわかって何がわからないかを整理します。\n\n"
    "長期投資 / 積立投資 / NISA / 投資メンタル を前提にした内容です。\n\n"
    "※投資助言ではありません\n"
    "※特定の金融商品の購入・売却を勧めるものではありません\n\n"
    "YouTube Shorts「ガチホのモチベ」では、\n"
    "長期投資を続けるモチベーションを毎日投稿しています。\n\n"
    "#長期投資 #積立投資 #投資メンタル #オルカン #SP500"
)
TAGS = ["長期投資", "積立投資", "投資メンタル", "NISA", "オルカン", "S&P500", "ガチホ"]

# 3本目の音声パス
ROLE_AUDIO_03 = {
    "hook": LONG_DIR / "audio" / "01_hook.mp3",
    "overview": LONG_DIR / "audio" / "02_overview.mp3",
    "why_painful": LONG_DIR / "audio" / "03_why_painful.mp3",
    "data": LONG_DIR / "audio" / "04_data.mp3",
    "interpret": LONG_DIR / "audio" / "05_interpret.mp3",
    "action": LONG_DIR / "audio" / "06_action.mp3",
    "closing": LONG_DIR / "audio" / "07_closing.mp3",
}


def _pick_photo(category: str) -> pathlib.Path:
    cat_dir = PHOTOS_DIR / category
    photos = sorted(cat_dir.glob("*.jpg"))
    return random.choice(photos)


# 背景画像
ROLE_BG_03 = {
    "hook": _pick_photo("comparison"),
    "overview": _pick_photo("steady"),
    "why_painful": _pick_photo("comparison"),
    "data": _pick_photo("data"),
    "interpret": _pick_photo("data"),
    "action": _pick_photo("recovery"),
    "closing": _pick_photo("recovery"),
}

STORYBOARD = [
    {"role": "hook", "title": "オルカン？\nS&P500？", "body": "", "share": 1.0, "layout": "full"},
    {"role": "hook", "title": "また揺れる", "body": "比較して、また不安になる", "share": 1.0, "layout": "corner"},
    {"role": "overview", "title": "整理すること", "body": "なぜ揺れるのか\nデータで何がわかるか", "share": 1.0, "layout": "corner"},
    {"role": "overview", "title": "答えは出さない", "body": "少し落ち着けるように", "share": 1.0, "layout": "full"},
    {"role": "why_painful", "title": "比べる対象が\nすぐそこにある", "body": "", "share": 1.0, "layout": "full"},
    {"role": "why_painful", "title": "どちらを選んでも\n起きること", "body": "", "share": 1.0, "layout": "full"},
    {"role": "why_painful", "title": "選ばなかったほうを\n良く見積もりやすい", "body": "", "share": 1.0, "layout": "full"},
    {"role": "why_painful", "title": "脳の仕組み", "body": "性格の問題ではない", "share": 1.0, "layout": "corner"},
    {"role": "data", "title": "米国 約60%", "body": "オルカンの中身", "share": 1.0, "layout": "number"},
    {"role": "data", "title": "2000〜2010", "body": "米国低迷\n新興国が強かった時期", "share": 1.0, "layout": "split"},
    {"role": "data", "title": "直近10年", "body": "米国が上回る傾向", "share": 1.0, "layout": "split"},
    {"role": "data", "title": "10年単位で変わる", "body": "直近の成績は続くとは限らない", "share": 1.0, "layout": "corner"},
    {"role": "interpret", "title": "強かった\n≠今後も強い", "body": "", "share": 1.0, "layout": "full"},
    {"role": "interpret", "title": "メリット\nと代償", "body": "どちらにもある", "share": 1.0, "layout": "full"},
    {"role": "interpret", "title": "揺れにくいほうを\n選ぶ", "body": "", "share": 1.0, "layout": "full"},
    {"role": "action", "title": "選んだ理由を\n書いてみる", "body": "たった一行でいい", "share": 1.0, "layout": "corner"},
    {"role": "action", "title": "今すぐ\n動かなくていい", "body": "", "share": 1.0, "layout": "full"},
    {"role": "closing", "title": "揺れながらも\n続けている", "body": "", "share": 1.0, "layout": "full"},
    {"role": "closing", "title": "それで十分", "body": "", "share": 1.0, "layout": "full"},
]


def _render_thumbnail(output_path: pathlib.Path):
    bg_path = _pick_photo("comparison")
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

    # 暗くしすぎない（0.5→0.65）
    bg = bg.filter(ImageFilter.GaussianBlur(radius=1))
    bg = ImageEnhance.Brightness(bg).enhance(0.65)
    bg = bg.convert("RGBA")
    overlay = Image.new("RGBA", (THUMB_WIDTH, THUMB_HEIGHT), (15, 20, 40, 60))
    bg = Image.alpha_composite(bg, overlay).convert("RGB")

    draw = ImageDraw.Draw(bg)
    font = ImageFont.truetype(FONT_HEAVY, 64)

    lines = ["オルカンか", "S&P500か"]
    line_height = 90
    y_start = (THUMB_HEIGHT - len(lines) * line_height) // 2
    for i, line in enumerate(lines):
        y = y_start + i * line_height
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (THUMB_WIDTH - tw) // 2
        # 影を濃くして読みやすく
        for dx, dy in [(3, 3), (2, 2)]:
            draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=(255, 255, 255))

    bg.save(str(output_path), "PNG", optimize=True)
    print(f"サムネイル生成: {output_path}")


def main():
    import long_video_builder as lvb

    # ★ long_video_builder のモジュール定数を3本目用に上書き ★
    lvb.LONG_DIR = LONG_DIR
    lvb.SLIDES_DIR = LONG_DIR / "slides"
    lvb.OVERLAYS_DIR = LONG_DIR / "overlays"
    lvb.OUTPUT_VIDEO = LONG_DIR / "output.mp4"
    lvb.OUTPUT_THUMB = LONG_DIR / "thumbnail.png"
    lvb.OUTPUT_META = LONG_DIR / "video_meta.json"
    lvb.ROLE_AUDIO = ROLE_AUDIO_03
    lvb.ROLE_BG = ROLE_BG_03
    lvb.TITLE = TITLE
    lvb.DESCRIPTION = DESCRIPTION
    lvb.TAGS = TAGS

    slides_dir = LONG_DIR / "slides"
    overlays_dir = LONG_DIR / "overlays"
    slides_dir.mkdir(parents=True, exist_ok=True)
    overlays_dir.mkdir(parents=True, exist_ok=True)

    # ストーリーボードにdurationを付与
    cards_by_role: dict[str, list[dict]] = {}
    for card in STORYBOARD:
        cards_by_role.setdefault(card["role"], []).append(dict(card))

    resolved: list[dict] = []
    for role in ["hook", "overview", "why_painful", "data", "interpret", "action", "closing"]:
        cards = cards_by_role.get(role, [])
        if not cards:
            continue
        total_duration = lvb._audio_duration(ROLE_AUDIO_03[role])
        total_share = sum(c.get("share", 1.0) for c in cards)
        assigned = 0.0
        for index, card in enumerate(cards):
            new_card = dict(card)
            new_card["bg_path"] = str(ROLE_BG_03.get(role, ROLE_BG_03["hook"]))
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

    # 動画合成（上書きした定数が使われる）
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
