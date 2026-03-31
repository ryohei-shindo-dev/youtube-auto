"""
long_video_builder.py
長尺動画の汎用ビルドエンジン。

各動画の固有データは long_video/{folder}/build_config.json に格納し、
共通の描画・合成ロジックをこのファイルに集約する。

使い方:
    python long_video_builder.py 04_haitou_index
    python long_video_builder.py 05_ikkatsu_tsumitate --thumbnail-only
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import shutil
import subprocess
import tempfile
import textwrap

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

BASE_DIR = pathlib.Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
PHOTOS_DIR = ASSETS_DIR / "photos"
BGM_PATH = ASSETS_DIR / "bgm_ambient.m4a"

VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
THUMB_WIDTH = 1280
THUMB_HEIGHT = 720
BGM_VOLUME = 0.06
SECTION_PAUSE = 0.9

FONT_HEAVY = "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"
FONT_BOLD = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"
FONT_MINCHO = "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc"
FONT_W8 = "/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc"

# ロール別アクセントカラー
ACCENT_COLORS: dict[str, tuple[int, int, int]] = {
    "hook": (220, 110, 90),
    "overview": (205, 170, 70),
    "why_painful": (145, 165, 210),
    "data": (100, 190, 255),
    "data2": (100, 190, 255),
    "interpret": (120, 220, 180),
    "action": (255, 215, 120),
    "closing": (180, 235, 160),
}

# Ken Burns パラメータ
UPSCALE = 1.5
DEFAULT_ZOOM_RATIO = 0.035


# ── 設定読み込み ──────────────────────────────────────

def load_config(folder: str) -> dict:
    """long_video/{folder}/build_config.json を読み込む。"""
    config_path = BASE_DIR / "long_video" / folder / "build_config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"build_config.json が見つかりません: {config_path}")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["_folder"] = folder
    config["_long_dir"] = BASE_DIR / "long_video" / folder
    return config


def _resolve_audio_paths(config: dict) -> dict[str, pathlib.Path]:
    """設定の role_audio を実パスに変換する。"""
    long_dir = config["_long_dir"]
    return {
        role: long_dir / "audio" / filename
        for role, filename in config["role_audio"].items()
    }


def _resolve_bg_paths(config: dict) -> dict[str, pathlib.Path]:
    """背景画像パスを解決する。"random:category" 形式ならランダム選択。"""
    result = {}
    for role, spec in config.get("role_bg", {}).items():
        if isinstance(spec, str) and spec.startswith("random:"):
            category = spec.split(":", 1)[1]
            result[role] = _pick_landscape_photo(category)
        else:
            result[role] = pathlib.Path(spec) if not pathlib.Path(spec).is_absolute() else pathlib.Path(spec)
            if not result[role].is_absolute():
                result[role] = BASE_DIR / result[role]
    return result


def _resolve_bg_alt_paths(config: dict) -> dict[str, list[pathlib.Path]]:
    """代替背景画像パスを解決する。"""
    result = {}
    for role, specs in config.get("role_bg_alt", {}).items():
        paths = []
        for spec in specs:
            if isinstance(spec, str) and spec.startswith("random:"):
                category = spec.split(":", 1)[1]
                paths.append(_pick_landscape_photo(category))
            else:
                p = pathlib.Path(spec)
                paths.append(p if p.is_absolute() else BASE_DIR / p)
        result[role] = paths
    return result


def _pick_landscape_photo(category: str) -> pathlib.Path:
    """横長の写真のみランダム選択する。長尺動画は1920x1080なので縦長は不可。"""
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
    if not landscape:
        raise FileNotFoundError(f"写真が見つかりません: {cat_dir}")
    return random.choice(landscape)


VIDEOS_DIR = BASE_DIR / "assets" / "videos" / "long_emotion"


def _resolve_video_bg(role_video_bg: dict) -> dict[str, str]:
    """build_config の role_video_bg を実パスに解決する。

    値が "video:category" の場合、該当カテゴリからランダムに1本選択。
    値が既存パスの場合はそのまま使用。
    """
    resolved = {}
    for role, spec in role_video_bg.items():
        if spec.startswith("video:"):
            category = spec.split(":", 1)[1]
            cat_dir = VIDEOS_DIR / category
            if cat_dir.exists():
                videos = list(cat_dir.glob("*.mp4"))
                if videos:
                    chosen = random.choice(videos)
                    resolved[role] = str(chosen)
                    continue
            print(f"  [警告] 動画素材なし: {spec} → 写真背景にフォールバック")
        elif pathlib.Path(spec).exists():
            resolved[role] = spec
    return resolved


# ── メイン処理 ────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="長尺動画ビルドエンジン")
    parser.add_argument("folder", help="long_video/ 配下のフォルダ名")
    parser.add_argument("--thumbnail-only", action="store_true", help="サムネイルのみ生成")
    args = parser.parse_args()

    config = load_config(args.folder)
    long_dir = config["_long_dir"]
    slides_dir = long_dir / "slides"
    overlays_dir = long_dir / "overlays"
    slides_dir.mkdir(parents=True, exist_ok=True)
    overlays_dir.mkdir(parents=True, exist_ok=True)

    role_audio = _resolve_audio_paths(config)
    role_bg = _resolve_bg_paths(config)
    role_bg_alt = _resolve_bg_alt_paths(config)
    role_zoom_dir = config.get("role_zoom_dir", {})
    role_pan_dir = config.get("role_pan_dir", {})
    role_order = config.get("role_order", list(role_audio.keys()))
    zoom_ratio = config.get("zoom_ratio", DEFAULT_ZOOM_RATIO)
    storyboard = config["storyboard"]
    title = config["title"]
    description = config["description"]
    tags = config["tags"]

    # サムネイル生成
    thumb_path = long_dir / "thumbnail.png"
    _render_thumbnail(config, role_bg, thumb_path)
    print(f"サムネイル: {thumb_path}")

    if args.thumbnail_only:
        return

    # ストーリーボード解決（durationを計算）
    resolved = _resolve_storyboard(storyboard, role_order, role_audio, role_bg, role_bg_alt)

    # スライド生成
    print(f"スライド生成中（{len(resolved)}枚）...")
    background_paths = []
    overlay_paths = []
    for index, card in enumerate(resolved, start=1):
        bg_path = slides_dir / f"{index:02d}_{card['role']}.png"
        ov_path = overlays_dir / f"{index:02d}_{card['role']}.png"
        _render_slide_layers(card, bg_path, ov_path)
        background_paths.append(bg_path)
        overlay_paths.append(ov_path)
        print(f"  [{index:02d}] {card['role']:15s} {card['title']:15s} ({card['duration']:.1f}秒)")

    # 動画背景の解決（role_video_bg の "video:category" を実パスに変換）
    role_video_bg = _resolve_video_bg(config.get("role_video_bg", {}))

    # 動画合成
    print("\n動画合成中...")
    output_video = long_dir / "output.mp4"
    _compose_video(
        resolved, background_paths, overlay_paths,
        role_audio, role_zoom_dir, role_pan_dir,
        output_video, zoom_ratio,
        role_video_bg=role_video_bg,
    )

    # メタデータ
    meta = {
        "title": title,
        "description": description,
        "tags": tags,
        "video_path": str(output_video),
        "thumbnail_path": str(thumb_path),
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
    meta_path = long_dir / "video_meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    total_sec = sum(c["duration"] for c in resolved)
    print(f"\n=== 完了 ===")
    print(f"動画: {output_video}（{total_sec:.1f}秒 / {total_sec/60:.1f}分）")
    print(f"メタデータ: {meta_path}")


# ── ストーリーボード解決 ──────────────────────────────

def _resolve_storyboard(
    storyboard: list[dict],
    role_order: list[str],
    role_audio: dict[str, pathlib.Path],
    role_bg: dict[str, pathlib.Path],
    role_bg_alt: dict[str, list[pathlib.Path]],
) -> list[dict]:
    """ストーリーボードにdurationとbg_pathを付与する。"""
    cards_by_role: dict[str, list[dict]] = {}
    for card in storyboard:
        cards_by_role.setdefault(card["role"], []).append(dict(card))

    resolved: list[dict] = []
    for role in role_order:
        cards = cards_by_role.get(role, [])
        if not cards:
            continue
        total_duration = _audio_duration(role_audio[role])
        total_share = sum(c.get("share", 1.0) for c in cards)
        assigned = 0.0

        for index, card in enumerate(cards):
            new_card = dict(card)

            # 背景画像の解決
            bg_idx = new_card.pop("bg_idx", None)
            if bg_idx is not None and role in role_bg_alt:
                alts = role_bg_alt[role]
                new_card["bg_path"] = str(alts[bg_idx % len(alts)])
            elif "bg_path" not in new_card:
                new_card["bg_path"] = str(role_bg.get(role, ""))

            # duration計算
            if index == len(cards) - 1:
                duration = total_duration - assigned
            else:
                duration = round(total_duration * card.get("share", 1.0) / total_share, 6)
                assigned += duration
            new_card["duration"] = duration
            resolved.append(new_card)

    return resolved


# ── スライド描画 ──────────────────────────────────────

def _render_slide_layers(card: dict, background_path: pathlib.Path, overlay_path: pathlib.Path):
    bg_path_str = card.get("bg_path", "")
    if bg_path_str:
        bg_path = pathlib.Path(bg_path_str)
        if not bg_path.is_absolute():
            bg_path = BASE_DIR / bg_path
    else:
        bg_path = PHOTOS_DIR / "steady" / "steady01.jpg"  # フォールバック

    background = _prepare_background(bg_path)
    overlay = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    layout = card.get("layout", "panel")
    if layout == "number":
        _draw_number_layout(draw, card)
    elif layout == "full":
        _draw_full_layout(draw, card)
    elif layout == "corner":
        _draw_corner_layout(draw, card)
    elif layout == "split":
        _draw_split_layout(draw, card)
    else:
        _draw_panel_layout(draw, card)

    background.convert("RGB").save(background_path, "PNG", optimize=True)
    overlay.save(overlay_path, "PNG", optimize=True)


def _draw_panel_layout(draw: ImageDraw.Draw, card: dict):
    title_font = _load_font(FONT_HEAVY, 82)
    body_font = _load_font(FONT_BOLD, 58)
    draw.text(
        (160, 200), card["title"], font=title_font,
        fill=(255, 255, 255), stroke_width=5, stroke_fill=(0, 0, 0),
    )
    wrapped_body = "\n".join(textwrap.wrap(card["body"], width=13, break_long_words=False))
    draw.multiline_text(
        (162, 340), wrapped_body, font=body_font,
        fill=(230, 235, 240), spacing=16,
        stroke_width=4, stroke_fill=(0, 0, 0),
    )


def _draw_split_layout(draw: ImageDraw.Draw, card: dict):
    title_font = _load_font(FONT_HEAVY, 78)
    body_font = _load_font(FONT_BOLD, 58)
    draw.text(
        (140, 180), card["title"], font=title_font,
        fill=(255, 255, 255), stroke_width=5, stroke_fill=(0, 0, 0),
    )
    wrapped_body = "\n".join(textwrap.wrap(card["body"], width=13, break_long_words=False))
    draw.multiline_text(
        (140, 340), wrapped_body, font=body_font,
        fill=(235, 240, 245), spacing=18,
        stroke_width=4, stroke_fill=(0, 0, 0),
    )


def _draw_number_layout(draw: ImageDraw.Draw, card: dict):
    title_font = _load_font(FONT_HEAVY, 145)
    body_font = _load_font(FONT_BOLD, 62)
    accent = ACCENT_COLORS.get(card["role"], (255, 255, 255))

    title_y = 300
    bbox = draw.multiline_textbbox((0, 0), card["title"], font=title_font, spacing=20)
    title_w = bbox[2] - bbox[0]
    title_h = bbox[3] - bbox[1]
    title_x = (VIDEO_WIDTH - title_w) // 2
    draw.multiline_text(
        (title_x, title_y), card["title"], font=title_font, fill=accent,
        spacing=20, align="center", stroke_width=6, stroke_fill=(0, 0, 0),
    )

    body_y = title_y + title_h + 40
    wrapped_body = "\n".join(textwrap.wrap(card["body"], width=18, break_long_words=False))
    bbox_body = draw.multiline_textbbox((0, 0), wrapped_body, font=body_font, spacing=18)
    body_w = bbox_body[2] - bbox_body[0]
    body_x = (VIDEO_WIDTH - body_w) // 2
    draw.multiline_text(
        (body_x, body_y), wrapped_body, font=body_font,
        fill=(245, 245, 245), spacing=18, align="center",
        stroke_width=4, stroke_fill=(0, 0, 0),
    )


def _draw_full_layout(draw: ImageDraw.Draw, card: dict):
    font_path = card.get("full_font", FONT_HEAVY)
    title_font = _load_font(font_path, 108)
    bbox = draw.multiline_textbbox((0, 0), card["title"], font=title_font, spacing=20)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    x = (VIDEO_WIDTH - width) // 2
    y = (VIDEO_HEIGHT - height) // 2
    draw.multiline_text(
        (x, y), card["title"], font=title_font,
        fill=(255, 255, 255), spacing=20, align="center",
        stroke_width=6, stroke_fill=(0, 0, 0),
    )


def _draw_corner_layout(draw: ImageDraw.Draw, card: dict):
    title_font = _load_font(FONT_HEAVY, 78)
    body_font = _load_font(FONT_BOLD, 56)
    text_x = 140
    text_y = 140
    draw.text(
        (text_x, text_y), card["title"], font=title_font,
        fill=(255, 255, 255), stroke_width=5, stroke_fill=(0, 0, 0),
    )
    if card.get("body"):
        wrapped_body = "\n".join(textwrap.wrap(card["body"], width=14, break_long_words=False))
        draw.multiline_text(
            (text_x + 2, text_y + 130), wrapped_body, font=body_font,
            fill=(235, 240, 245), spacing=14,
            stroke_width=3, stroke_fill=(0, 0, 0),
        )


# ── サムネイル ────────────────────────────────────────

def _render_thumbnail(config: dict, role_bg: dict, output_path: pathlib.Path):
    """設定ファイルの thumbnail セクションからサムネイルを生成する。"""
    thumb_cfg = config.get("thumbnail", {})

    # 背景画像
    bg_spec = thumb_cfg.get("bg_photo", "")
    if bg_spec.startswith("random:"):
        bg_path = _pick_landscape_photo(bg_spec.split(":", 1)[1])
    elif bg_spec:
        bg_path = pathlib.Path(bg_spec)
        if not bg_path.is_absolute():
            bg_path = BASE_DIR / bg_spec
    else:
        first_bg = next(iter(role_bg.values()), None)
        bg_path = first_bg if first_bg else PHOTOS_DIR / "steady" / "steady01.jpg"

    bg = Image.open(bg_path).convert("RGB")
    bg = _crop_to_landscape(bg, THUMB_WIDTH, THUMB_HEIGHT)
    brightness = thumb_cfg.get("brightness", 0.75)
    blur = thumb_cfg.get("blur", 1)
    if blur > 0:
        bg = bg.filter(ImageFilter.GaussianBlur(radius=blur))
    bg = ImageEnhance.Brightness(bg).enhance(brightness)

    # オーバーレイ（暗くする）
    overlay_alpha = thumb_cfg.get("overlay_alpha", 40)
    if overlay_alpha > 0:
        bg = bg.convert("RGBA")
        ov = Image.new("RGBA", (THUMB_WIDTH, THUMB_HEIGHT), (15, 20, 40, overlay_alpha))
        bg = Image.alpha_composite(bg, ov).convert("RGB")

    draw = ImageDraw.Draw(bg)

    # テキスト描画
    main_lines = thumb_cfg.get("main_lines", [])
    sub_text = thumb_cfg.get("sub_text", "")
    main_font_size = thumb_cfg.get("main_font_size", 96)
    sub_font_size = thumb_cfg.get("sub_font_size", 40)
    main_color = tuple(thumb_cfg.get("main_color", [255, 210, 50]))
    sub_color = tuple(thumb_cfg.get("sub_color", [255, 255, 255]))
    text_x = thumb_cfg.get("text_x", 60)
    text_y = thumb_cfg.get("text_y", 200)
    line_height = thumb_cfg.get("line_height", 110)

    main_font = _load_font(FONT_W8, main_font_size)
    sub_font = _load_font(FONT_HEAVY, sub_font_size)

    y = text_y
    for line in main_lines:
        draw.text(
            (text_x, y), line, font=main_font, fill=main_color,
            stroke_width=6, stroke_fill=(0, 0, 0),
        )
        y += line_height

    if sub_text:
        draw.text(
            (text_x, y + 15), sub_text, font=sub_font, fill=sub_color,
            stroke_width=3, stroke_fill=(0, 0, 0),
        )

    bg.save(str(output_path), "PNG", optimize=True)


# ── 動画合成 ──────────────────────────────────────────

def _group_by_role(storyboard, background_paths, overlay_paths):
    groups = []
    current_role = None
    for card, bg, ov in zip(storyboard, background_paths, overlay_paths):
        if card["role"] != current_role:
            groups.append({"role": card["role"], "cards": [], "bgs": [], "overlays": []})
            current_role = card["role"]
        groups[-1]["cards"].append(card)
        groups[-1]["bgs"].append(bg)
        groups[-1]["overlays"].append(ov)
    return groups


def _compose_video(
    storyboard: list[dict],
    background_paths: list[pathlib.Path],
    overlay_paths: list[pathlib.Path],
    role_audio: dict[str, pathlib.Path],
    role_zoom_dir: dict[str, str],
    role_pan_dir: dict[str, str],
    output_video: pathlib.Path,
    zoom_ratio: float = DEFAULT_ZOOM_RATIO,
    role_video_bg: dict[str, str] = None,
):
    groups = _group_by_role(storyboard, background_paths, overlay_paths)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = pathlib.Path(tmp_dir)
        video_paths = []
        audio_paths = []

        for gi, group in enumerate(groups):
            role = group["role"]
            cards = group["cards"]
            total_dur = sum(c["duration"] for c in cards)

            if gi > 0:
                prev_group = groups[gi - 1]
                pause_video = tmp / f"pause_{gi:02d}.mp4"
                pause_audio = tmp / f"pause_{gi:02d}.m4a"
                _make_pause_video(prev_group["bgs"][-1], prev_group["overlays"][-1], SECTION_PAUSE, pause_video)
                _make_silence_audio(SECTION_PAUSE, pause_audio)
                video_paths.append(pause_video)
                audio_paths.append(pause_audio)

            zoom_dir = role_zoom_dir.get(role, "in")
            pan_dir = role_pan_dir.get(role, "center")
            print(f"  ロール [{role}] {len(cards)}カード {total_dur:.1f}秒 （パン: {pan_dir}）...")

            role_video = tmp / f"role_{gi:02d}_{role}.mp4"
            vbg = (role_video_bg or {}).get(role, "")
            if vbg:
                print(f"    動画背景: {pathlib.Path(vbg).name}")
            _make_role_clip(
                group["bgs"][0], group["overlays"], cards, total_dur,
                role_video, zoom_out=(zoom_dir == "out"), pan_dir=pan_dir,
                zoom_ratio=zoom_ratio,
                video_bg_path=vbg,
            )
            video_paths.append(role_video)

            audio_clip = tmp / f"audio_{gi:02d}_{role}.m4a"
            _make_audio_clip(role_audio[role], 0.0, total_dur, audio_clip)
            audio_paths.append(audio_clip)

        raw_video = tmp / "raw_video.mp4"
        raw_audio = tmp / "raw_audio.m4a"
        final_audio = tmp / "final_audio.m4a"

        print(f"  {len(video_paths)} クリップを結合中...")
        _concat_files(video_paths, raw_video)
        _concat_files(audio_paths, raw_audio)

        if BGM_PATH.exists():
            print(f"  BGMミキシング中（音量: {BGM_VOLUME}）...")
            _mix_bgm(raw_audio, final_audio)
        else:
            shutil.copy2(raw_audio, final_audio)

        print(f"  映像+音声を結合中...")
        _mux_video_audio(raw_video, final_audio, output_video)


def _make_role_clip(
    background_path: pathlib.Path,
    overlay_paths: list[pathlib.Path],
    cards: list[dict],
    total_dur: float,
    output_path: pathlib.Path,
    zoom_out: bool = False,
    pan_dir: str = "center",
    zoom_ratio: float = DEFAULT_ZOOM_RATIO,
    video_bg_path: str = "",
):
    use_video_bg = bool(video_bg_path and pathlib.Path(video_bg_path).exists())

    up_w = int(VIDEO_WIDTH * UPSCALE)
    up_h = int(VIDEO_HEIGHT * UPSCALE)
    cx = (up_w - VIDEO_WIDTH) // 2
    cy = (up_h - VIDEO_HEIGHT) // 2
    pan_x = int(VIDEO_WIDTH * zoom_ratio / 2)
    pan_y = int(VIDEO_HEIGHT * zoom_ratio / 2)

    if pan_dir == "left_to_right":
        dx_factor, dy_factor = 2 * pan_x, 0
    elif pan_dir == "right_to_left":
        dx_factor, dy_factor = -2 * pan_x, 0
    elif pan_dir == "top_to_bottom":
        dx_factor, dy_factor = 0, 2 * pan_y
    elif pan_dir == "bottom_to_top":
        dx_factor, dy_factor = 0, -2 * pan_y
    else:
        dx_factor, dy_factor = 0, 0

    if pan_dir == "center":
        x_expr = f"'{cx}'"
        y_expr = f"'{cy}'"
    elif zoom_out:
        x_expr = f"'{cx + abs(dx_factor)//2} + {dx_factor}*t/{total_dur}'"
        y_expr = f"'{cy + abs(dy_factor)//2} + {dy_factor}*t/{total_dur}'"
    else:
        x_expr = f"'{cx - abs(dx_factor)//2} + {dx_factor}*t/{total_dur}'"
        y_expr = f"'{cy - abs(dy_factor)//2} + {dy_factor}*t/{total_dur}'"

    if use_video_bg:
        # 動画背景: リサイズ+軽い暗め補正（Ken Burns不要、動画自体が動く）
        crop_expr = (
            f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},"
            f"eq=brightness=-0.06:saturation=0.85"
        )
        inputs = ["-stream_loop", "-1", "-i", str(video_bg_path)]
    else:
        # 静止画背景: Ken Burns ズーム/パン
        crop_expr = (
            f"scale={up_w}:{up_h},"
            f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT}:"
            f"x={x_expr}:y={y_expr}"
        )
        inputs = ["-loop", "1", "-i", str(background_path)]

    for ov_path in overlay_paths:
        inputs += ["-loop", "1", "-i", str(ov_path)]

    filter_parts = [f"[0:v]{crop_expr}[bg]"]
    for i in range(len(overlay_paths)):
        filter_parts.append(f"[{i+1}:v]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}[ov{i}]")

    prev_label = "bg"
    t_offset = 0.0
    for i, card in enumerate(cards):
        t_start = t_offset
        t_end = t_offset + card["duration"]
        out_label = f"tmp{i}" if i < len(cards) - 1 else "v"
        filter_parts.append(
            f"[{prev_label}][ov{i}]overlay=0:0:format=auto"
            f":enable='between(t,{t_start:.6f},{t_end:.6f})'[{out_label}]"
        )
        prev_label = out_label
        t_offset = t_end

    filter_parts[-1] = filter_parts[-1].rsplit("[", 1)[0] + ",format=yuv420p[v]"
    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-loglevel", "error", "-y",
        *inputs,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-filter_complex", filter_complex,
        "-map", "[v]", "-t", str(total_dur), "-r", "30", "-an",
        str(output_path),
    ]
    _run(cmd, timeout=300)


def _make_pause_video(bg_path: pathlib.Path, ov_path: pathlib.Path, duration: float, output_path: pathlib.Path):
    cmd = [
        "ffmpeg", "-loglevel", "error", "-y",
        "-loop", "1", "-i", str(bg_path),
        "-loop", "1", "-i", str(ov_path),
        "-c:v", "libx264", "-tune", "stillimage",
        "-filter_complex",
        (
            f"[0:v]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}[bg];"
            f"[1:v]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}[fg];"
            "[bg][fg]overlay=0:0:format=auto,format=yuv420p[v]"
        ),
        "-map", "[v]", "-t", str(duration), "-an",
        str(output_path),
    ]
    _run(cmd, timeout=60)


def _make_audio_clip(audio_path: pathlib.Path, offset: float, duration: float, output_path: pathlib.Path):
    cmd = [
        "ffmpeg", "-loglevel", "error", "-y",
        "-ss", str(offset), "-t", str(duration),
        "-i", str(audio_path),
        "-vn", "-ac", "1", "-ar", "44100",
        "-c:a", "aac", "-b:a", "160k",
        str(output_path),
    ]
    _run(cmd, timeout=120)


def _make_silence_audio(duration: float, output_path: pathlib.Path):
    cmd = [
        "ffmpeg", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
        "-t", str(duration),
        "-c:a", "aac", "-b:a", "128k",
        str(output_path),
    ]
    _run(cmd, timeout=60)


def _concat_files(paths: list[pathlib.Path], output_path: pathlib.Path):
    concat_list = output_path.parent / f"{output_path.stem}.txt"
    concat_list.write_text("".join(f"file '{path}'\n" for path in paths), encoding="utf-8")
    cmd = [
        "ffmpeg", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list), "-c", "copy",
        str(output_path),
    ]
    _run(cmd, timeout=240)


def _mix_bgm(audio_path: pathlib.Path, output_path: pathlib.Path):
    cmd = [
        "ffmpeg", "-loglevel", "error", "-y",
        "-i", str(audio_path),
        "-stream_loop", "-1", "-i", str(BGM_PATH),
        "-filter_complex",
        (
            f"[1:a]volume={BGM_VOLUME},afade=t=in:d=2,afade=t=out:st=999:d=3[bgm];"
            "[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=0[aout]"
        ),
        "-map", "[aout]", "-c:a", "aac", "-b:a", "192k",
        str(output_path),
    ]
    _run(cmd, timeout=240)


def _mux_video_audio(video_path: pathlib.Path, audio_path: pathlib.Path, output_path: pathlib.Path):
    cmd = [
        "ffmpeg", "-loglevel", "error", "-y",
        "-i", str(video_path), "-i", str(audio_path),
        "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", "-c:a", "copy",
        "-movflags", "+faststart",
        str(output_path),
    ]
    _run(cmd, timeout=240)


# ── ユーティリティ ────────────────────────────────────

def _prepare_background(bg_path: pathlib.Path) -> Image.Image:
    img = Image.open(bg_path).convert("RGB")
    img = _crop_to_landscape(img, VIDEO_WIDTH, VIDEO_HEIGHT)
    img = img.filter(ImageFilter.GaussianBlur(radius=2))
    img = ImageEnhance.Brightness(img).enhance(0.75)
    return img


def _crop_to_landscape(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    src_w, src_h = img.size
    target_ratio = target_w / target_h
    if src_w / src_h > target_ratio:
        crop_h = src_h
        crop_w = int(src_h * target_ratio)
    else:
        crop_w = src_w
        crop_h = int(src_w / target_ratio)
    left = (src_w - crop_w) // 2
    top = (src_h - crop_h) // 2
    img = img.crop((left, top, left + crop_w, top + crop_h))
    return img.resize((target_w, target_h), Image.LANCZOS)


def _load_font(path: str, size: int):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def _audio_duration(audio_path: pathlib.Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        capture_output=True, text=True, timeout=10, check=True,
    )
    return float(result.stdout.strip())


def _run(cmd: list[str], timeout: int):
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "command failed")


if __name__ == "__main__":
    main()
