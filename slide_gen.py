"""
slide_gen.py
プリメイド画像 + Pillow で YouTube Shorts 用のスライド画像（1080x1920）を生成するモジュール。

【レイアウト2型】
  v1（従来型）: シルエット画像を全画面に暗くぼかして配置、テキスト中央
  v2（写真型）: 写真の縦横で自動レイアウト切替
    - 縦型写真: 全画面写真 + 下部グラデーション + テキスト重ね（没入型）
    - 横型写真: 上部55%写真 + 下部45%テキスト（分割型）
    - 写真は assets/photos/ のカテゴリ別素材を使用
    - 色補正はロール別（hook=やや暗→closing=ほぼ原色、感情曲線に連動）

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

import json
import os
import pathlib
import random
import re
import textwrap

from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from thumbnail_gen import _auto_font_size

# Shorts 解像度（縦型 9:16）
SHORTS_WIDTH = 1080
SHORTS_HEIGHT = 1920

# Instagram Reels / Shorts の下部UIと重ならないための安全域
BOTTOM_SAFE_AREA = 360
BOTTOM_TEXT_MARGIN = 80
SPLIT_LAYOUT_TEXT_TOP_PADDING = 96
TEXT_SIDE_MARGIN_LEFT = 72
TEXT_SIDE_MARGIN_RIGHT = 160  # YouTube Shorts の右側UIボタン（いいね等）と重ならないため

# 日本語フォントパス（macOS 標準）
FONT_PATH_HEAVY = "/System/Library/Fonts/ヒラギノ角ゴシック W9.ttc"
FONT_PATH_REGULAR = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"

# アセットディレクトリ
ASSETS_DIR = pathlib.Path(__file__).parent / "assets"
PHOTOS_DIR = ASSETS_DIR / "photos"
PHOTO_HISTORY_PATH = pathlib.Path(__file__).parent / "debug" / "photo_history.json"
PHOTO_HISTORY_KEEP = 30

CHANNEL_NAME = "ガチホのモチベ"
BRAND_LABEL_COLOR = (180, 180, 180)

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

# v2用の下部背景色（ロール別、感情曲線に沿って hook=暗め → closing=やや明るい）
V2_TEXT_BG = {
    "hook": (38, 30, 52),
    "empathy": (32, 36, 58),
    "data": (28, 42, 66),
    "resolve": (32, 52, 52),
    "closing": (40, 44, 62),
}

# v2用の写真補正パラメータ（ロール別、感情曲線に沿って段階的に明るくする）
V2_PHOTO_PARAMS = {
    "hook":    {"brightness": 0.94, "saturation": 0.95, "overlay": (18, 24, 48, 45)},
    "empathy": {"brightness": 0.92, "saturation": 0.95, "overlay": (16, 22, 44, 40)},
    "data":    {"brightness": 0.96, "saturation": 0.98, "overlay": (12, 20, 38, 28)},
    "resolve": {"brightness": 1.00, "saturation": 1.00, "overlay": (10, 18, 32, 18)},
    "closing": {"brightness": 1.02, "saturation": 1.00, "overlay": (8, 16, 28, 10)},
}
V2_PHOTO_BLUR = 1
# フォールバック（ロール不明時）
_V2_PHOTO_DEFAULT = {"brightness": 0.95, "saturation": 0.95, "overlay": (15, 20, 45, 30)}

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

# ── ロール別のオーバーレイカラー（RGBA）── v1用、画像の上に被せる
ROLE_OVERLAY = {
    "hook": (30, 12, 16, 120),
    "empathy": (12, 24, 52, 105),
    "data": (14, 34, 56, 95),
    "resolve": (18, 46, 34, 90),
    "closing": (32, 22, 18, 90),
    "opening": (12, 24, 52, 105),
    "explain": (20, 20, 40, 100),
    "theme": (20, 20, 40, 100),
    "summary": (18, 46, 34, 90),
}

# ── テキストカラー ──
ROLE_TEXT_COLOR = {
    "hook": (255, 120, 100),
    "empathy": (255, 255, 255),
    "data": (100, 200, 255),
    "resolve": (120, 230, 150),
    "closing": (236, 196, 122),
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
        # スライド上の句点は不要（短文なので視覚的に邪魔）
        text = text.rstrip("。")

        print(f"  スライド{idx}（{role}）を生成中...")
        try:
            if use_photo:
                path, photo_asset = _generate_slide_v2(text, role, output_path)
                if photo_asset:
                    scene["photo_asset"] = photo_asset
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
        canvas = enhancer.enhance(0.65)
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
    _draw_main_text(draw, text, text_color, role=role)

    # ブランド名はclosingのみ下中央寄りに表示
    _draw_channel_name(draw, role=role)

    canvas.save(str(output_path), "PNG", optimize=True)
    return output_path


def _is_portrait(img: Image.Image) -> bool:
    """写真が縦型（高さ > 幅）かどうかを判定する。"""
    return img.size[1] > img.size[0]


def _apply_photo_correction(img: Image.Image, role: str = "") -> Image.Image:
    """写真に色補正+ネイビーオーバーレイを適用する（portrait/landscape共通）。

    ロール別に明度・彩度・オーバーレイ濃度を変え、感情曲線（hook=暗→closing=明）を反映。
    """
    params = V2_PHOTO_PARAMS.get(role, _V2_PHOTO_DEFAULT)
    img = ImageEnhance.Brightness(img).enhance(params["brightness"])
    img = ImageEnhance.Color(img).enhance(params["saturation"])
    if V2_PHOTO_BLUR > 0:
        img = img.filter(ImageFilter.GaussianBlur(radius=V2_PHOTO_BLUR))
    img = img.convert("RGBA")
    overlay = Image.new("RGBA", img.size, params["overlay"])
    return Image.alpha_composite(img, overlay).convert("RGB")


def _generate_slide_v2(
    text: str,
    role: str,
    output_path: pathlib.Path,
) -> tuple[pathlib.Path, str]:
    """v2: 全画面没入型レイアウトに統一。

    写真の縦横に関わらず、全画面にフィットさせて下部グラデーション+テキスト重ね。
    横型写真は中央クロップで縦型にフィットする（_fit_photo_to_area が処理）。
    """
    photo, photo_asset = _get_photo(role)

    return _generate_slide_v2_portrait(text, role, output_path, photo), photo_asset


def _generate_slide_v2_portrait(
    text: str,
    role: str,
    output_path: pathlib.Path,
    photo: Image.Image,
) -> pathlib.Path:
    """v2 縦型: 写真を全画面に配置し、下部にグラデーション+テキストを重ねる。"""
    canvas = Image.new("RGB", (SHORTS_WIDTH, SHORTS_HEIGHT), (15, 15, 30))

    # 写真を全画面にフィット + 色補正（ロール別）
    photo_area = _fit_photo_to_area(photo, SHORTS_WIDTH, SHORTS_HEIGHT)
    photo_area = _apply_photo_correction(photo_area, role=role)
    canvas.paste(photo_area, (0, 0))

    # 下部45%にグラデーション（透明→暗色）でテキスト読みやすく
    bg_color = V2_TEXT_BG.get(role, (40, 44, 62))
    _blend_gradient(canvas, start_y=int(SHORTS_HEIGHT * 0.55),
                    bg_color=bg_color, exponent=1.5)

    draw = ImageDraw.Draw(canvas)

    # アクセントライン（上端と下端）
    accent_color = ROLE_TEXT_COLOR.get(role, (255, 255, 255))
    draw.rectangle([(0, 0), (SHORTS_WIDTH, 4)], fill=accent_color)
    draw.rectangle([(0, SHORTS_HEIGHT - 4), (SHORTS_WIDTH, SHORTS_HEIGHT)],
                   fill=accent_color)

    # テキストは下部UI安全域を除いた範囲に配置
    text_color = ROLE_TEXT_COLOR.get(role, (255, 255, 255))
    text_area_top = int(SHORTS_HEIGHT * 0.60)
    text_area_bottom = SHORTS_HEIGHT - BOTTOM_SAFE_AREA
    text_area_h = max(0, text_area_bottom - text_area_top)
    _draw_text_in_area(draw, text, text_color, text_area_top, text_area_h, role=role)

    # ブランド名はclosingのみ下中央寄りに表示
    _draw_channel_name(draw, role=role)

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
        photo_area = _apply_photo_correction(photo_area, role=role)
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

    # メインテキストは下部UI安全域を除いた範囲に配置
    text_color = ROLE_TEXT_COLOR.get(role, (255, 255, 255))
    text_area_top = PHOTO_HEIGHT + SPLIT_LAYOUT_TEXT_TOP_PADDING
    text_area_bottom = SHORTS_HEIGHT - BOTTOM_SAFE_AREA
    text_area_h = max(0, text_area_bottom - text_area_top)
    _draw_text_in_area(draw, text, text_color, text_area_top, text_area_h, role=role)

    # ブランド名はclosingのみ下中央寄りに表示
    _draw_channel_name(draw, role=role)

    canvas.save(str(output_path), "PNG", optimize=True)
    return output_path


def _get_photo(role: str) -> tuple[Image.Image | None, str]:
    """ロールに対応する写真カテゴリからランダムに1枚取得する。"""
    category = ROLE_PHOTO_CATEGORY.get(role, "")
    if not category:
        return None, ""

    photo_dir = PHOTOS_DIR / category
    if not photo_dir.exists():
        return None, ""

    photos = sorted(list(photo_dir.glob("*.jpg")) + list(photo_dir.glob("*.png")))
    if not photos:
        return None, ""

    history = _load_photo_history()
    blocked_names = set(history.get(category, [])[-PHOTO_HISTORY_KEEP:])
    if role == "hook":
        blocked_names.update(_get_recent_published_hook_photo_names(limit=6))
    candidates = [p for p in photos if p.name not in blocked_names] or photos
    selected = random.choice(candidates)

    try:
        img = Image.open(selected)
        _remember_photo_choice(category, selected.name, history)
        return img, selected.name
    except Exception:
        return None, ""


def _get_recent_published_hook_photo_names(limit: int = 1) -> list[str]:
    """直近の YouTube 投稿済み動画の hook 画像ファイル名を取得する。"""
    sheet_id = os.getenv("YOUTUBE_SHEET_ID", "")
    if sheet_id:
        try:
            import sheets

            rows = sheets.get_service().spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=f"{sheets.SHEET_NAME}!A:N",
            ).execute().get("values", [])
            published = []
            for row in rows[1:]:
                folder = sheets.get_cell(row, sheets.COL["folder"])
                pub_date = sheets.get_cell(row, sheets.COL["pub_date"])
                gen_date = sheets.get_cell(row, sheets.COL["gen_date"])
                youtube_url = sheets.get_cell(row, sheets.COL["youtube_url"])
                if folder and youtube_url:
                    published.append((pub_date or gen_date or folder, folder))

            published.sort(key=lambda item: item[0], reverse=True)
            names = []
            for _, folder in published:
                asset = _read_hook_photo_asset_from_folder(folder)
                if asset:
                    names.append(asset)
                if len(names) >= limit:
                    return names
        except Exception:
            pass

    names = []
    for transcript_path in sorted(
        pathlib.Path(__file__).parent.joinpath("done").glob("*/transcript.json"),
        reverse=True,
    ):
        asset = _read_hook_photo_asset_from_transcript(transcript_path)
        if asset:
            names.append(asset)
        if len(names) >= limit:
            break
    if not names:
        history = _load_photo_history()
        latest = history.get("anxiety", [])[-1:]
        names.extend(latest)
    return names


def _read_hook_photo_asset_from_folder(folder_name: str) -> str:
    transcript_path = pathlib.Path(__file__).parent / "done" / folder_name / "transcript.json"
    return _read_hook_photo_asset_from_transcript(transcript_path)


def _read_hook_photo_asset_from_transcript(transcript_path: pathlib.Path) -> str:
    try:
        data = json.loads(transcript_path.read_text(encoding="utf-8"))
    except Exception:
        return ""

    for scene in data.get("scenes", []):
        if scene.get("role") == "hook":
            return scene.get("photo_asset", "")
    return ""


def _load_photo_history() -> dict:
    """最近使った写真名をカテゴリ別に読み込む。"""
    try:
        return json.loads(PHOTO_HISTORY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _remember_photo_choice(category: str, filename: str, history: dict):
    """選択した写真を履歴に保存し、直近の重複を避ける。"""
    items = history.get(category, [])
    items.append(filename)
    history[category] = items[-PHOTO_HISTORY_KEEP:]
    PHOTO_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    PHOTO_HISTORY_PATH.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


_face_cascade: cv2.CascadeClassifier | None = None


def _get_face_cascade() -> cv2.CascadeClassifier:
    """Haar Cascade をキャッシュして返す（ファイル読み込みは初回のみ）。"""
    global _face_cascade
    if _face_cascade is None:
        _face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
    return _face_cascade


def _detect_face_center_x(img: Image.Image) -> int | None:
    """顔検出して顔の中心X座標を返す。検出できなければ None。"""
    gray = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
    faces = _get_face_cascade().detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=4
    )
    if len(faces) == 0:
        return None
    largest = max(faces, key=lambda f: f[2] * f[3])
    x, _y, w, _h = largest
    return x + w // 2


def _fit_photo_to_area(
    img: Image.Image, target_w: int, target_h: int
) -> Image.Image:
    """写真を指定エリアにフィットさせる（顔検出でクロップ位置を調整）。"""
    src_w, src_h = img.size

    # 横長→縦長など大きくクロップされる場合のみ顔検出を試みる
    scale = max(target_w / src_w, target_h / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)

    # クロップ幅が元画像の10%以上ある場合のみ顔検出（軽量化）
    crop_margin_x = new_w - target_w
    face_cx = None
    if crop_margin_x > src_w * 0.1:
        face_cx = _detect_face_center_x(img)

    img = img.resize((new_w, new_h), Image.LANCZOS)

    # 横方向クロップ: 顔があれば顔中心、なければ画像中心
    if face_cx is not None:
        # 顔の中心をリサイズ後の座標に変換
        scaled_cx = int(face_cx * scale)
        left = max(0, min(new_w - target_w, scaled_cx - target_w // 2))
    else:
        left = (new_w - target_w) // 2

    # 縦方向クロップ: 上部優先（人物の顔は上半分にあることが多い）
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
    area_top: int, area_height: int,
    role: str = "",
):
    """指定エリアの中央にテキストを配置する（影付き）。
    hookスライドは15%大きいフォントで表示（冒頭で視線を止める効果）。
    """
    is_hook = role == "hook"
    font_size = 126 if is_hook else 110
    line_height = 178 if is_hook else 155
    font, lines, line_height = _fit_text_layout(
        draw, text, FONT_PATH_HEAVY, font_size, line_height,
        SHORTS_WIDTH - TEXT_SIDE_MARGIN_LEFT - TEXT_SIDE_MARGIN_RIGHT,
        role=role,
    )
    total_height = len(lines) * line_height
    available_space = max(0, area_height - total_height - BOTTOM_TEXT_MARGIN)
    # 下部テキストエリアは中央寄せだと短文時に間延びして見えるため、
    # やや上寄せで配置して写真との境界付近から読み始める。
    y_start = area_top + int(available_space * 0.22)

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]
        x = TEXT_SIDE_MARGIN_LEFT + (SHORTS_WIDTH - TEXT_SIDE_MARGIN_LEFT - TEXT_SIDE_MARGIN_RIGHT - text_width) // 2
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


def _draw_main_text(draw: ImageDraw.Draw, text: str, color: tuple, role: str = ""):
    """メインテキストを中央に大きく配置する（影付き）。
    hookスライドは15%大きいフォントで表示。
    """
    is_hook = role == "hook"
    font_size = 138 if is_hook else 120
    line_height = 195 if is_hook else 170
    font, lines, line_height = _fit_text_layout(
        draw, text, FONT_PATH_HEAVY, font_size, line_height,
        SHORTS_WIDTH - TEXT_SIDE_MARGIN_LEFT - TEXT_SIDE_MARGIN_RIGHT,
        role=role,
    )
    total_height = len(lines) * line_height
    y_start = (SHORTS_HEIGHT - total_height) // 2

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        text_width = bbox[2] - bbox[0]
        x = TEXT_SIDE_MARGIN_LEFT + (SHORTS_WIDTH - TEXT_SIDE_MARGIN_LEFT - TEXT_SIDE_MARGIN_RIGHT - text_width) // 2
        y = y_start + i * line_height

        for dx, dy in [(4, 4), (3, 3), (2, 2)]:
            draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=color)


def _draw_channel_name(draw: ImageDraw.Draw, role: str = ""):
    """closing のみ下中央寄りにチャンネル名を小さく表示する。"""
    if role != "closing":
        return
    font = _load_font(FONT_PATH_REGULAR, 28)
    bbox = draw.textbbox((0, 0), CHANNEL_NAME, font=font)
    text_width = bbox[2] - bbox[0]
    x = TEXT_SIDE_MARGIN_LEFT + (SHORTS_WIDTH - TEXT_SIDE_MARGIN_LEFT - TEXT_SIDE_MARGIN_RIGHT - text_width) // 2
    y = SHORTS_HEIGHT - BOTTOM_SAFE_AREA + 56
    draw.text((x + 1, y + 1), CHANNEL_NAME, font=font, fill=(0, 0, 0))
    draw.text((x, y), CHANNEL_NAME, font=font, fill=BRAND_LABEL_COLOR)


def _wrap_text_lines(text: str, width: int) -> list[str]:
    """折り返し後の各行を返す。

    日本語テキスト（スペースなし）を指定文字数で折り返す。
    割ってはいけない単語はUnicode PUA文字（1文字）に置換し、
    折り返し後に復元する。
    """
    # 割ってはいけない単語リスト
    no_break = [
        "チャンネル", "フォロー", "コメント", "ガチホ",
        "インデックス", "リターン", "バフェット", "マンガー",
    ]
    placeholder_map: dict[str, str] = {}
    protected = text

    # 数字+単位+助詞（6000万、30年後、1800万円等）を分断しない
    for m in re.finditer(r"\d+[万億千百兆円%％年月日本倍回件人]+[後前目間分]*", protected):
        word = m.group()
        if word not in no_break:
            no_break.append(word)
    # 分数（1/3、１／３、3分の1等）を分断しない
    for m in re.finditer(r"\d+[/／]\d+|\d+分の\d+", protected):
        word = m.group()
        if word not in no_break:
            no_break.append(word)
    # 単位なしの数字列（S&P500等）も分断しない
    for m in re.finditer(r"\d{2,}", protected):
        word = m.group()
        if word not in no_break:
            no_break.append(word)

    for idx, word in enumerate(no_break):
        # Unicode PUA 1文字をプレースホルダに使う（折り返しで分断されない）
        token = chr(0xE000 + idx)
        if word in protected:
            protected = protected.replace(word, token)
            placeholder_map[token] = word

    wrapped = textwrap.wrap(protected, width=width, break_long_words=True, break_on_hyphens=False)
    restored = []
    for line in wrapped:
        for token, word in placeholder_map.items():
            line = line.replace(token, word)
        restored.append(line)

    # 禁則処理: 行頭の「、」「。」を前の行の末尾に戻す
    for i in range(1, len(restored)):
        while restored[i] and restored[i][0] in ("、", "。"):
            restored[i - 1] += restored[i][0]
            restored[i] = restored[i][1:]

    # 空行が生まれた場合は除去
    restored = [line for line in restored if line]

    return restored or [text]


def _fit_text_layout(
    draw: ImageDraw.Draw,
    text: str,
    font_path: str,
    font_size: int,
    line_height: int,
    max_width: int,
    role: str = "",
) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    """指定幅に収まるまで折り返しとフォントサイズを調整する。"""
    # 意味切れ目の候補はテキストとロールだけで決まるので、ループ外で1回だけ計算
    semantic_candidates = _semantic_break_candidates(text.strip(), role) if role in {"data", "resolve"} else []
    width = 7
    current_size = font_size
    current_line_height = line_height

    while current_size >= 84:
        font = _load_font(font_path, current_size)
        # data/resolve はセマンティック改行を試行（フォントサイズごとに1回）
        lines = _preferred_role_lines(text, role, draw, font, max_width, semantic_candidates) if semantic_candidates else []
        if lines:
            return font, lines, current_line_height
        # セマンティック改行が不可なら文字数ベースで折り返し
        lines = _wrap_text_lines(text, width)
        widest = 0
        for line in lines:
            bb = draw.textbbox((0, 0), line, font=font)
            widest = max(widest, bb[2] - bb[0])
        if widest <= max_width:
            return font, lines, current_line_height
        width += 1
        if width > 12:
            current_size -= 6
            current_line_height = max(110, int(current_line_height * 0.92))
            width = 7

    # フォールバック: 最小フォントサイズでも収まらなかった場合
    # 文字数を減らしながらピクセル幅に収まるまで折り返す
    font = _load_font(font_path, current_size)
    for w in range(12, 3, -1):
        lines = _wrap_text_lines(text, w)
        widest = 0
        for line in lines:
            bb = draw.textbbox((0, 0), line, font=font)
            widest = max(widest, bb[2] - bb[0])
        if widest <= max_width:
            return font, lines, current_line_height
    return font, _wrap_text_lines(text, 5), current_line_height


def _preferred_role_lines(
    text: str,
    role: str,
    draw: ImageDraw.Draw,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    candidates: list[int] | None = None,
) -> list[str]:
    """ロール別に、意味の切れ目を優先した改行候補を返す。"""
    stripped = text.strip()
    if len(stripped) < 8:
        return []

    if candidates is None:
        candidates = _semantic_break_candidates(stripped, role)
    if not candidates:
        return []

    best_lines = []
    best_score = None
    for idx in candidates:
        left = stripped[:idx].strip("、。 ")
        right = stripped[idx:].strip("、。 ")
        if not left or not right:
            continue
        widths = []
        for line in (left, right):
            bbox = draw.textbbox((0, 0), line, font=font)
            widths.append(bbox[2] - bbox[0])
        if max(widths) > max_width:
            continue
        score = abs(len(left) - len(right))
        if best_score is None or score < best_score:
            best_score = score
            best_lines = [left, right]
    return best_lines


def _semantic_break_candidates(text: str, role: str) -> list[int]:
    """意味の切れ目として使いやすい位置を返す。"""
    tokens = [
        "ほど", "人ほど", "人は", "判断が", "日が", "時は", "時ほど",
        "だから", "結局", "やっぱり", "つまり", "焦らない日が",
        "売らない判断が", "暴落の後", "暴落は", "下がる時期も",
        "口座を見るほど", "見るほど", "見ない強さも", "比べない日ほど",
    ]
    if role == "data":
        tokens = ["、", "から", "だけ"] + tokens

    seen = set()
    points = []
    for token in tokens:
        start = 0
        while True:
            idx = text.find(token, start)
            if idx == -1:
                break
            split_at = idx + len(token)
            if 2 <= split_at <= len(text) - 2 and split_at not in seen:
                seen.add(split_at)
                points.append(split_at)
            start = idx + 1

    center = len(text) / 2
    return sorted(points, key=lambda p: abs(p - center))


@lru_cache(maxsize=32)
def _load_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    """フォントを読み込む。失敗時はデフォルトフォント。キャッシュ付き。"""
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


# ── Shorts サムネイル生成（16:9 横型） ──

THUMB_WIDTH = 1280
THUMB_HEIGHT = 720


def generate_shorts_thumbnail(
    scenes: list,
    output_path: pathlib.Path,
    title: str = "",
) -> pathlib.Path | None:
    """Shortsサムネイル専用画像（縦型1080x1920）を新規生成する。

    動画スライドの流用はしない。
    顔が大きい人物写真 + titleから生成した短いテキスト で構成。
    """
    from PIL import ImageEnhance

    # ── テキスト: titleから短いサムネ専用文を作る ──
    thumb_text = _make_thumbnail_text(title, scenes)
    if not thumb_text:
        return None

    # ── 写真: 縦型で顔が大きい人物写真を優先 ──
    photo = None
    # まず各シーンの写真から縦型を探す
    for photo_role in ("hook", "empathy", "hook", "empathy"):
        for s in scenes:
            if s.get("role") == photo_role and s.get("photo_asset"):
                category = ROLE_PHOTO_CATEGORY.get(photo_role, "anxiety")
                photo_path = PHOTOS_DIR / category / s["photo_asset"]
                if photo_path.exists():
                    try:
                        candidate = Image.open(photo_path)
                        # 縦型写真を優先（横型だと顔が切れる）
                        if candidate.height >= candidate.width:
                            photo = candidate
                            break
                        elif photo is None:
                            photo = candidate  # 横型でもフォールバックとして保持
                    except Exception:
                        continue
        if photo and photo.height >= photo.width:
            break

    # フォールバック: anxietyから縦型写真をランダム取得
    if photo is None or photo.height < photo.width:
        portrait_photos = []
        for cat in ("anxiety", "comparison", "recovery"):
            cat_dir = PHOTOS_DIR / cat
            if cat_dir.exists():
                for p in cat_dir.glob("*.jpg"):
                    try:
                        img = Image.open(p)
                        if img.height >= img.width:
                            portrait_photos.append(p)
                    except Exception:
                        continue
        if portrait_photos:
            selected = random.choice(portrait_photos)
            photo = Image.open(selected)

    if photo is None:
        return None

    # ── サムネ画像を組み立て ──
    photo = photo.convert("RGB")
    photo = _fit_photo_to_area(photo, SHORTS_WIDTH, SHORTS_HEIGHT)

    # 明るさ調整（暗くしすぎない）
    photo = ImageEnhance.Brightness(photo).enhance(0.88)

    # 下部にグラデーション（テキスト読みやすく、でも暗すぎない）
    _blend_gradient(photo, start_y=int(SHORTS_HEIGHT * 0.55),
                    bg_color=(20, 20, 30), exponent=1.2)

    draw = ImageDraw.Draw(photo)

    # テキスト描画（下寄せ中央、2行、太字）
    lines = thumb_text.split("\n")
    font_size = 100 if max(len(l) for l in lines) <= 8 else 80
    font = _load_font(FONT_PATH_HEAVY, font_size)

    # 各行の描画位置を計算
    line_heights = []
    line_widths = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])

    gap = 20
    total_h = sum(line_heights) + gap * (len(lines) - 1)
    # 下から30%の位置に配置
    start_y = int(SHORTS_HEIGHT * 0.65) - total_h // 2

    for i, line in enumerate(lines):
        x = (SHORTS_WIDTH - line_widths[i]) // 2
        y = start_y + i * (line_heights[0] + gap)
        # 1行目は黄色（強調）、2行目は白
        color = (240, 200, 60) if i == 0 else (255, 255, 255)
        draw.text((x, y), line, font=font, fill=color,
                  stroke_width=5, stroke_fill=(0, 0, 0))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    photo.save(str(output_path), "PNG", optimize=True)
    size_kb = output_path.stat().st_size // 1024
    print(f"  サムネイル生成完了: {output_path.name}（{size_kb}KB）")
    return output_path


def _make_thumbnail_text(title: str, scenes: list) -> str:
    """タイトルからサムネ用見出しを再構成する（2行、各行14文字以内）。

    タイトルを機械的に切るのではなく、主題語を抽出して見出しを作り直す。
    """
    if not title:
        return ""

    # タイトルから「|」「｜」「#Shorts」以降を除去
    clean = title.split("|")[0].split("｜")[0].split("#")[0].strip()
    clean = clean.rstrip("。、！？!? ")

    # 短いならそのまま
    if len(clean) <= 10:
        return clean

    # 1. 句読点で自然に2行に分割できるか
    for sep in ["。", "、", "…", "―"]:
        if sep in clean:
            parts = clean.split(sep, 1)
            line1 = parts[0].strip().rstrip("。、 ")
            line2 = parts[1].strip().rstrip("。、 ") if len(parts) > 1 else ""
            if line1 and line2 and len(line1) <= 14 and len(line2) <= 14:
                return f"{line1}\n{line2}"
            if line1 and len(line1) <= 14:
                return line1

    # 2. dataのslide_text（各動画固有の数字データ、意味が通りやすい）
    for s in scenes:
        if s.get("role") == "data" and s.get("slide_text"):
            data_text = s["slide_text"].rstrip("。")
            if len(data_text) <= 14:
                return data_text

    # 3. タイトルの助詞で自然に区切る
    for m in re.finditer(r"[をにでとは]", clean):
        pos = m.end()
        if 6 <= pos <= 14:
            return clean[:pos]

    # 4. resolveのslide_text（結論、ただしempathyは使わない）
    for s in scenes:
        if s.get("role") == "resolve" and s.get("slide_text"):
            resolve_text = s["slide_text"].rstrip("。")
            if len(resolve_text) <= 14:
                return resolve_text

    # 5. hookのslide_text
    for s in scenes:
        if s.get("role") == "hook" and s.get("slide_text"):
            hook_text = s["slide_text"].rstrip("。")
            if len(hook_text) <= 14:
                return hook_text

    return clean[:14]


# ── サムネフレーム（動画内埋め込み用） ──────────────────────

THUMBNAIL_DIR = PHOTOS_DIR / "thumbnail"
THUMBNAIL_REGISTRY_PATH = pathlib.Path(__file__).parent / "thumbnail_registry.json"
_THUMBNAIL_NO_REUSE_WINDOW = 30  # 直近30本で同じ写真を使わない


def _normalize_thumb_text(text: str) -> str:
    """サムネテキストを正規化して類似判定に使う。

    改行除去 + 文末の「です」「だ」「ですね」等を除去して比較する。
    例: 「時間が最大の武器です」→「時間が最大の武器」
    """
    t = text.replace("\n", "")
    # 文末の丁寧表現・断定表現を除去（長い順にマッチ）
    for suffix in ("ですね", "です", "だね", "だよ", "だ", "ね", "よ"):
        if t.endswith(suffix) and len(t) > len(suffix) + 2:
            t = t[: -len(suffix)]
            break
    return t


def _load_thumbnail_registry() -> list[dict]:
    """thumbnail_registry.json を読み込む。"""
    if THUMBNAIL_REGISTRY_PATH.exists():
        try:
            return json.loads(THUMBNAIL_REGISTRY_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save_thumbnail_registry(registry: list[dict]) -> None:
    """thumbnail_registry.json を保存する（直近100件に切り詰め）。"""
    registry = registry[-100:]
    THUMBNAIL_REGISTRY_PATH.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8",
    )


def _pick_thumbnail_photo(registry: list[dict]) -> pathlib.Path | None:
    """thumbnail/ フォルダからサムネ用写真を1枚選ぶ（直近で使った写真を避ける）。"""
    if not THUMBNAIL_DIR.exists():
        return None

    all_photos = sorted(THUMBNAIL_DIR.glob("*.jpg"))
    if not all_photos:
        return None

    # 直近N本で使った写真パスを集める
    recent_photos = set()
    for entry in registry[-_THUMBNAIL_NO_REUSE_WINDOW:]:
        p = entry.get("thumbnail_photo", "")
        if p:
            recent_photos.add(pathlib.Path(p).name)

    # 未使用の写真を優先
    available = [p for p in all_photos if p.name not in recent_photos]
    if not available:
        # 全部使い切った場合は最も古い使用のものから再利用
        available = all_photos

    return random.choice(available)


def _make_thumbnail_text_v2(title: str, scenes: list) -> str:
    """タイトルからサムネ用見出しを再構成する（2行、合計10〜18文字）。

    タイトルの「短縮」ではなく、主題語を使った見出しの「再構成」を行う。
    empathyのslide_textへのフォールバックは禁止。
    """
    if not title:
        return ""

    # タイトルから「|」「｜」「#Shorts」以降を除去
    clean = title.split("|")[0].split("｜")[0].split("#")[0].strip()
    clean = clean.rstrip("。、！？!? ")

    # ── 1. 句読点で自然に2行分割 ──
    for sep in ["。", "、", "…", "―"]:
        if sep in clean:
            parts = clean.split(sep, 1)
            line1 = parts[0].strip().rstrip("。、 ")
            line2 = parts[1].strip().rstrip("。、 ") if len(parts) > 1 else ""
            if line1 and line2 and len(line1) <= 12 and len(line2) <= 12:
                total = len(line1) + len(line2)
                if 8 <= total <= 20:
                    return f"{line1}\n{line2}"

    # ── 2. タイトル全体が短ければそのまま ──
    if 10 <= len(clean) <= 18:
        # 助詞で2行に分割を試みる
        for m in re.finditer(r"[をにでとはがも]", clean):
            pos = m.end()
            if 4 <= pos <= 12 and 4 <= len(clean) - pos <= 12:
                return f"{clean[:pos]}\n{clean[pos:]}"
        # 分割できなければ1行で
        if len(clean) <= 12:
            return clean

    # ── 3. タイトルから主題語を抽出して2行に再構成 ──
    # dataのslide_text（各動画固有の数字データ）
    data_text = ""
    for s in scenes:
        if s.get("role") == "data" and s.get("slide_text"):
            data_text = s["slide_text"].rstrip("。")
            break

    # hookのslide_text
    hook_text = ""
    for s in scenes:
        if s.get("role") == "hook" and s.get("slide_text"):
            hook_text = s["slide_text"].rstrip("。")
            break

    # resolveのslide_text
    resolve_text = ""
    for s in scenes:
        if s.get("role") == "resolve" and s.get("slide_text"):
            resolve_text = s["slide_text"].rstrip("。")
            break

    # ── 3a. dataテキストが使えるなら、hook+dataの組み合わせ ──
    if data_text and hook_text and len(hook_text) <= 12 and len(data_text) <= 12:
        total = len(hook_text) + len(data_text)
        if 8 <= total <= 20:
            return f"{hook_text}\n{data_text}"

    # ── 3b. dataテキスト単体（14文字以内で意味が通る） ──
    if data_text and 6 <= len(data_text) <= 14:
        return data_text

    # ── 3c. 助詞でタイトルを区切る ──
    for m in re.finditer(r"[をにでとはがも]", clean):
        pos = m.end()
        line1 = clean[:pos]
        line2 = clean[pos:]
        if 4 <= len(line1) <= 12 and 4 <= len(line2) <= 12:
            total = len(line1) + len(line2)
            if 8 <= total <= 20:
                return f"{line1}\n{line2}"

    # ── 3d. resolveテキスト（結論）── ただしempathyは使わない
    if resolve_text and 6 <= len(resolve_text) <= 14:
        return resolve_text

    # ── 4. フォールバック: タイトル先頭14文字 ──
    if len(clean) > 14:
        # 助詞の位置で切る
        for m in re.finditer(r"[をにでとはがも]", clean[:15]):
            pos = m.end()
            if 6 <= pos:
                return clean[:pos]
        return clean[:14]

    return clean


# ========== サムネフレーム用 禁則処理 ==========
# ChatGPT組版レビュー（2026-03-19）に基づく

# 行頭禁止文字（句読点・閉じ括弧・助詞・機能語の一部）
_NO_HEAD_CHARS = set("、。，．・：；！？）」』】〉》!?,.)]}%‰+をにへとがはもでの")

# 行末禁止文字（開き括弧・「第」「約」など）
_NO_TAIL_CHARS = set("（「『【〈《([{第約")

# 2行目先頭に来てはいけない2文字機能語
_NO_HEAD_BIGRAMS = {
    "より", "では", "とは", "にも", "でも", "への",
    "から", "まで", "だけ", "ほど", "など", "のは",
}

# 分割してはいけないパターン（数字+単位・分数・英数字語）
_NO_SPLIT_PATTERNS = re.compile(
    r"\d+/\d+"                                       # 分数 1/3
    r"|\d+\.\d+"                                     # 小数 2.5
    r"|\d+(?:年目|ヶ月目|か月目|年|ヶ月|か月|月|日|時間"
    r"|分|秒|回|人|倍|割|％|%|万|億|円|ドル|点|歳|代|本|枚|件)"  # 数字+単位
    r"|[+\-]\d+[%％]?"                               # +40%, -3%
    r"|S&P500|NASDAQ100|NISA|iDeCo"                  # 英数字混在語
)

# 3文字以上のカタカナ語（途中で切らない）
_KATAKANA_WORD = re.compile(r"[ァ-ヶー]{3,}")

# 保護語辞書（複合語の途中で切らない）
_PROTECTED_WORDS = [
    "非課税効果", "元本割れ", "長期投資家", "長期投資", "積み立て",
    "積立投資", "配当再投資", "信託報酬", "平均取得単価",
    "ドルコスト平均法", "インデックス投資", "インフレ",
    "レバレッジ", "リターン", "バフェット", "資産", "複利",
]

# 各行の最小文字数
_MIN_LINE_CHARS = 5


def _find_split_pos(text: str) -> int | None:
    """テキストの適切な分割位置を返す。禁則処理付き。

    ChatGPT組版レビューに基づく3段方式:
    1. 絶対に切らない塊を守る
    2. 切るなら助詞・読点の直後だけに寄せる
    3. 不自然に短い行を禁止する
    """
    n = len(text)
    if n <= 6:
        return None

    # --- 分割禁止区間を収集 ---
    no_split: set[int] = set()

    # 数字+単位、英数字語（内部での分割のみ禁止、直前での分割は許可）
    for m in _NO_SPLIT_PATTERNS.finditer(text):
        for i in range(m.start() + 1, m.end()):
            no_split.add(i)

    # カタカナ語
    for m in _KATAKANA_WORD.finditer(text):
        for i in range(m.start() + 1, m.end()):
            no_split.add(i)

    # 保護語辞書（内部での分割のみ禁止、直前での分割は許可）
    for word in _PROTECTED_WORDS:
        start = 0
        while True:
            idx = text.find(word, start)
            if idx == -1:
                break
            for i in range(idx + 1, idx + len(word)):
                no_split.add(i)
            start = idx + 1

    # 2文字機能語の途中分割を禁止
    for bigram in _NO_HEAD_BIGRAMS:
        start = 0
        while True:
            idx = text.find(bigram, start)
            if idx == -1:
                break
            # bigram の途中（idx + 1）での分割を禁止
            no_split.add(idx + 1)
            start = idx + 1

    def _is_valid_split(pos: int) -> bool:
        """pos の位置で分割したとき、禁則違反がないか。"""
        if pos <= 0 or pos >= n:
            return False
        # 各行の最小文字数チェック
        if pos < _MIN_LINE_CHARS or (n - pos) < _MIN_LINE_CHARS:
            return False
        # 分割禁止区間の途中でないか
        if pos in no_split:
            return False
        # 2行目の先頭が行頭禁止文字でないか
        if text[pos] in _NO_HEAD_CHARS:
            return False
        # 2行目の先頭が2文字機能語でないか
        if text[pos:pos + 2] in _NO_HEAD_BIGRAMS:
            return False
        # 1行目の末尾が行末禁止文字でないか
        if text[pos - 1] in _NO_TAIL_CHARS:
            return False
        return True

    # --- 候補を集めてスコア付け（中央に近いほど良い） ---
    center = n // 2
    best_pos = None
    best_score = float("inf")

    # 1. 助詞・読点の後で分割（最も自然）
    for m in re.finditer(r"[をにとがの、]|(?<=[ぁ-んァ-ヶ\u4e00-\u9fff0-9])[でもは]", text):
        pos = m.end()
        if _is_valid_split(pos):
            score = abs(center - pos)
            if score < best_score:
                best_score = score
                best_pos = pos

    if best_pos is not None:
        return best_pos

    # 2. 助詞がない場合: 中央付近の有効位置で分割（サムネ用フォールバック）
    for dist in range(n):
        for pos in [center + dist, center - dist]:
            if 0 < pos < n and _is_valid_split(pos):
                return pos

    return None


def _split_long_lines_for_thumb(
    lines: list[str], draw, max_width: int,
) -> list[str]:
    """はみ出す行を自動改行で分割する。禁則処理付き。

    9文字以上の1行テキストは強制分割（インスタグリッドで縮小表示されるため）。
    """
    result = []
    for line in lines:
        # 9文字以上の行は幅に収まっていても分割を試みる（フォント縮小防止）
        needs_split = len(line) >= 9

        if not needs_split:
            sz = _auto_font_size(line, max_size=160, min_size=90)
            font = _load_font(FONT_PATH_HEAVY, sz)
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            if w <= max_width:
                result.append(line)
                continue
            needs_split = True

        if needs_split:
            # サムネ用: 最小文字数を緩和して分割（通常の禁則処理は厳しすぎる）
            split_pos = _find_split_pos_for_thumb(line)
            if split_pos is not None:
                result.append(line[:split_pos].strip())
                result.append(line[split_pos:].strip())
            else:
                result.append(line)

    return result


def _find_split_pos_for_thumb(text: str) -> int | None:
    """サムネ用の緩い分割位置検索。最小3文字、中央寄りで分割。"""
    n = len(text)
    if n <= 6:
        return None

    min_chars = 3  # サムネ用は3文字から許可
    center = n // 2

    # 分割禁止区間を収集（内部のみ）
    no_split: set[int] = set()
    for m in _NO_SPLIT_PATTERNS.finditer(text):
        for i in range(m.start() + 1, m.end()):
            no_split.add(i)
    for m in _KATAKANA_WORD.finditer(text):
        for i in range(m.start() + 1, m.end()):
            no_split.add(i)
    for word in _PROTECTED_WORDS:
        start = 0
        while True:
            idx = text.find(word, start)
            if idx == -1:
                break
            for i in range(idx + 1, idx + len(word)):
                no_split.add(i)
            start = idx + 1

    def _ok(pos: int) -> bool:
        if pos < min_chars or (n - pos) < min_chars:
            return False
        if pos in no_split:
            return False
        if text[pos] in _NO_HEAD_CHARS:
            return False
        return True

    # 1. 助詞・読点の後（最も自然）
    best_pos = None
    best_score = float("inf")
    for m in re.finditer(r"[をにとがの、]|(?<=[ぁ-んァ-ヶ\u4e00-\u9fff0-9])[でもは]", text):
        pos = m.end()
        if _ok(pos):
            score = abs(center - pos)
            if score < best_score:
                best_score = score
                best_pos = pos

    if best_pos is not None:
        return best_pos

    # 2. 中央付近の任意位置
    for dist in range(n):
        for pos in [center + dist, center - dist]:
            if 0 < pos < n and _ok(pos):
                return pos

    return None


def generate_thumbnail_frame(
    scenes: list,
    output_path: pathlib.Path,
    title: str = "",
    used_texts: list[str] | None = None,
) -> dict | None:
    """サムネフレーム画像を生成する（動画先頭に埋め込み用）。

    Returns:
        {"path": output_path, "text": thumb_text, "photo": photo_name}
        失敗時は None。
    """
    registry = _load_thumbnail_registry()

    # ── テキスト生成 ──
    thumb_text = _make_thumbnail_text_v2(title, scenes)
    if not thumb_text:
        print("  [サムネフレーム] テキスト生成失敗")
        return None

    # サムネテキスト重複チェック（バッチ内 + レジストリの過去100本）
    all_existing: set[str] = set()
    # レジストリ（公開済み・キュー内）のテキストを正規化して追加
    for entry in registry:
        if entry.get("thumbnail_text"):
            all_existing.add(_normalize_thumb_text(entry["thumbnail_text"]))
    # バッチ内のテキストも追加
    if used_texts is not None:
        for t in used_texts:
            all_existing.add(_normalize_thumb_text(t))

    if _normalize_thumb_text(thumb_text) in all_existing:
        print(f"  [サムネフレーム] テキスト重複: {thumb_text.replace(chr(10), ' ')}")
        # data → resolve → hookの順でフォールバック
        for role in ("data", "resolve", "hook"):
            for s in scenes:
                if s.get("role") == role and s.get("slide_text"):
                    alt = s["slide_text"].rstrip("。")
                    if 6 <= len(alt) <= 14 and _normalize_thumb_text(alt) not in all_existing:
                        thumb_text = alt
                        break
            else:
                continue
            break

    # ── 写真選択 ──
    photo_path = _pick_thumbnail_photo(registry)
    if not photo_path:
        print("  [サムネフレーム] サムネ用写真がありません（assets/photos/thumbnail/）")
        return None

    # ── 画像生成 ──
    photo = Image.open(photo_path).convert("RGB")
    photo = _fit_photo_to_area(photo, SHORTS_WIDTH, SHORTS_HEIGHT)
    photo = ImageEnhance.Brightness(photo).enhance(0.88)
    _blend_gradient(photo, start_y=int(SHORTS_HEIGHT * 0.55),
                    bg_color=(20, 20, 30), exponent=1.2)

    draw = ImageDraw.Draw(photo)

    # テキスト描画（1行目は大きく、2行目はやや小さく — thumbnail_gen と同方式）
    # 左右マージン確保（テキストが画面幅をはみ出さないように）
    text_max_width = SHORTS_WIDTH - 80  # 左右40pxずつ余白

    # はみ出す行を自動改行で分割
    lines = _split_long_lines_for_thumb(thumb_text.split("\n"), draw, text_max_width)

    fonts = []
    for i, line in enumerate(lines):
        if i == 0:
            sz = _auto_font_size(line, max_size=160, min_size=90)
        else:
            sz = _auto_font_size(line, max_size=120, min_size=70)
        # 改行で収まらなかった場合のフォールバック: フォントサイズ縮小
        while sz > 40:
            font = _load_font(FONT_PATH_HEAVY, sz)
            bbox = draw.textbbox((0, 0), line, font=font)
            if (bbox[2] - bbox[0]) <= text_max_width:
                break
            sz -= 4
        fonts.append(_load_font(FONT_PATH_HEAVY, sz))

    line_heights = []
    line_widths = []
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=fonts[i])
        line_widths.append(bbox[2] - bbox[0])
        line_heights.append(bbox[3] - bbox[1])

    gap = 24
    total_h = sum(line_heights) + gap * (len(lines) - 1)
    start_y = int(SHORTS_HEIGHT * 0.65) - total_h // 2

    cur_y = start_y
    for i, line in enumerate(lines):
        x = (SHORTS_WIDTH - line_widths[i]) // 2
        color = (240, 200, 60) if i == 0 else (255, 255, 255)
        draw.text((x, cur_y), line, font=fonts[i], fill=color,
                  stroke_width=5, stroke_fill=(0, 0, 0))
        cur_y += line_heights[i] + gap

    output_path.parent.mkdir(parents=True, exist_ok=True)
    photo.save(str(output_path), "PNG", optimize=True)
    size_kb = output_path.stat().st_size // 1024
    print(f"  サムネフレーム生成: {thumb_text.replace(chr(10), ' / ')}（{size_kb}KB）")

    # ── レジストリ更新 ──
    from datetime import datetime
    registry.append({
        "thumbnail_photo": photo_path.name,
        "thumbnail_text": thumb_text,
        "generated_at": datetime.now().isoformat(),
    })
    _save_thumbnail_registry(registry)

    return {
        "path": str(output_path),
        "text": thumb_text,
        "photo": photo_path.name,
    }
