"""
long_video_builder.py
長尺動画のスライド生成、サムネイル生成、動画合成をまとめて行う。

初回実装では 1本目「含み損で眠れない夜」の完成を対象にする。
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import tempfile
import textwrap

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from long_voice_gen import SCRIPT_01_SCENES

BASE_DIR = pathlib.Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
LONG_DIR = BASE_DIR / "long_video" / "01_fukumison"
SLIDES_DIR = LONG_DIR / "slides"
OVERLAYS_DIR = LONG_DIR / "overlays"
OUTPUT_VIDEO = LONG_DIR / "output.mp4"
OUTPUT_THUMB = LONG_DIR / "thumbnail.png"
OUTPUT_META = LONG_DIR / "video_meta.json"
BGM_PATH = ASSETS_DIR / "bgm_ambient.m4a"

VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
THUMB_WIDTH = 1280
THUMB_HEIGHT = 720
BGM_VOLUME = 0.06
SECTION_PAUSE = 0.9

FONT_HEAVY = "/System/Library/Fonts/ヒラギノ角ゴシック W9.ttc"
FONT_BOLD = "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"
FONT_REGULAR = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"

TITLE = "含み損で眠れない夜に、何をしないのが一番いいのか"
DESCRIPTION = (
    "含み損の夜は、数字そのものより、自分の判断が間違っていた気がしてつらくなります。"
    "この動画では、金融危機の数字を一つ置きながら、含み損の夜にどう考えれば少し落ち着けるのかを静かに整理します。\n\n"
    "※投資助言ではありません"
)
TAGS = ["長期投資", "積立投資", "NISA", "資産形成", "ガチホ", "投資メンタル"]

ROLE_AUDIO = {
    "hook": LONG_DIR / "audio" / "01_hook.mp3",
    "overview": LONG_DIR / "audio" / "02_overview.mp3",
    "why_painful": LONG_DIR / "audio" / "03_why_painful.mp3",
    "data": LONG_DIR / "audio" / "04_data.mp3",
    "interpret": LONG_DIR / "audio" / "05_interpret.mp3",
    "action": LONG_DIR / "audio" / "06_action.mp3",
    "closing": LONG_DIR / "audio" / "07_closing.mp3",
}

ROLE_BG = {
    "hook": "04_person_down.png",
    "overview": "03_person_thinking.png",
    "why_painful": "02_phone_anxious.png",
    "data": "08_long_term_chart.png",
    "interpret": "09_growth_graph.png",
    "action": "05_person_relieved.png",
    "closing": "12_sunrise.png",
}

# ロールごとのズーム方向（内面系=in / 余韻系=out）
ROLE_ZOOM_DIR: dict[str, str] = {
    "hook": "in",
    "overview": "in",
    "why_painful": "in",
    "data": "in",
    "interpret": "out",
    "action": "out",
    "closing": "out",
}

# scale→crop 方式のパラメータ
# 背景を UPSCALE 倍に拡大し、crop 範囲をゆっくり動かす（iMovie Ken Burns 方式）
UPSCALE = 1.5
ZOOM_RATIO = 0.035  # 100% → 103.5% のズーム量

STORYBOARD = [
    {"role": "hook", "title": "含み損", "body": "夜が長い", "share": 1.0, "layout": "number"},
    {"role": "hook", "title": "つらさの正体", "body": "判断まで疑い始める", "share": 1.0, "layout": "corner"},
    {"role": "hook", "title": "今夜の話", "body": "なぜつらいのか\n今夜どう動かないか", "share": 1.0, "layout": "split"},
    {"role": "overview", "title": "二つだけ整理する", "body": "夜がつらい理由\n今夜しない方がいいこと", "share": 1.0, "layout": "corner"},
    {"role": "overview", "title": "時間が武器", "body": "Shorts の話を今日は少し長く", "share": 1.0, "layout": "number"},
    {"role": "why_painful", "title": "戻らなかったら", "body": "", "share": 1.0, "layout": "full"},
    {"role": "why_painful", "title": "自分だけ失敗したら", "body": "", "share": 1.0, "layout": "full"},
    {"role": "why_painful", "title": "口座を何度も見る", "body": "朝見て 昼見て 夜見て", "share": 1.0, "layout": "split"},
    {"role": "why_painful", "title": "反応として普通", "body": "損失は重く感じやすい", "share": 1.0, "layout": "corner"},
    {"role": "data", "title": "-57%", "body": "2007年高値から\n2009年の底まで", "share": 1.0, "layout": "number"},
    {"role": "data", "title": "2007 → 2009", "body": "半分以上の下落", "share": 1.0, "layout": "split"},
    {"role": "data", "title": "2013回復", "body": "時間を伸ばすと景色が変わる", "share": 1.0, "layout": "number"},
    {"role": "interpret", "title": "同じではない", "body": "", "share": 0.6, "layout": "full"},
    {"role": "interpret", "title": "途中で決めない", "body": "今日の価格は途中\n途中の数字で全部を決めない", "share": 1.4, "layout": "corner"},
    {"role": "action", "title": "今夜やること", "body": "口座を開かない\n設定を変えない", "share": 1.0, "layout": "corner"},
    {"role": "action", "title": "何もしない", "body": "動かなかったことが正解になる", "share": 1.0, "layout": "number"},
    {"role": "closing", "title": "今日はそれで十分", "body": "途中の数字で全部を決めない", "share": 1.0, "layout": "corner"},
]


def main():
    SLIDES_DIR.mkdir(parents=True, exist_ok=True)
    OVERLAYS_DIR.mkdir(parents=True, exist_ok=True)
    resolved_storyboard = _resolve_storyboard()

    background_paths = []
    overlay_paths = []
    for index, card in enumerate(resolved_storyboard, start=1):
        background_path = SLIDES_DIR / f"{index:02d}_{card['role']}.png"
        overlay_path = OVERLAYS_DIR / f"{index:02d}_{card['role']}.png"
        _render_slide_layers(card, background_path, overlay_path)
        background_paths.append(background_path)
        overlay_paths.append(overlay_path)

    _render_thumbnail(OUTPUT_THUMB)
    output_path = _compose_video(resolved_storyboard, background_paths, overlay_paths)

    meta = {
        "title": TITLE,
        "description": DESCRIPTION,
        "tags": TAGS,
        "video_path": str(output_path),
        "thumbnail_path": str(OUTPUT_THUMB),
        "slides": [
            {
                "role": card["role"],
                "title": card["title"],
                "duration": card["duration"],
                "slide_path": str(bg_path),
                "overlay_path": str(overlay_path),
            }
            for card, bg_path, overlay_path in zip(resolved_storyboard, background_paths, overlay_paths)
        ],
    }
    OUTPUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"動画生成完了: {output_path}")
    print(f"サムネイル: {OUTPUT_THUMB}")
    print(f"メタデータ: {OUTPUT_META}")


def _resolve_storyboard() -> list[dict]:
    cards_by_role: dict[str, list[dict]] = {}
    for card in STORYBOARD:
        cards_by_role.setdefault(card["role"], []).append(dict(card))

    resolved: list[dict] = []
    for scene in SCRIPT_01_SCENES:
        role = scene["role"]
        cards = cards_by_role.get(role, [])
        if not cards:
            raise ValueError(f"storyboard missing role: {role}")

        total_duration = _audio_duration(ROLE_AUDIO[role])
        total_share = sum(card.get("share", 1.0) for card in cards)
        assigned = 0.0

        for index, card in enumerate(cards):
            new_card = dict(card)
            if index == len(cards) - 1:
                duration = total_duration - assigned
            else:
                duration = round(total_duration * card.get("share", 1.0) / total_share, 6)
                assigned += duration
            new_card["duration"] = duration
            resolved.append(new_card)

    return resolved


def _render_slide_layers(card: dict, background_path: pathlib.Path, overlay_path: pathlib.Path):
    bg_path = ASSETS_DIR / ROLE_BG[card["role"]]
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


def _render_thumbnail(output_path: pathlib.Path):
    canvas = Image.new("RGB", (THUMB_WIDTH, THUMB_HEIGHT), (10, 10, 10))
    draw = ImageDraw.Draw(canvas)

    pain_font = _load_font(FONT_HEAVY, 130)
    body_font = _load_font(FONT_BOLD, 62)
    small_font = _load_font(FONT_REGULAR, 24)

    line1 = "含み損の夜"
    line2 = "動かない方がいい"

    _draw_centered(draw, line1, pain_font, (255, 215, 0), 170)
    _draw_centered(draw, line2, body_font, (255, 255, 255), 360)
    draw.text((THUMB_WIDTH - 190, THUMB_HEIGHT - 55), "ガチホのモチベ", font=small_font, fill=(120, 120, 120))

    canvas.save(output_path, "PNG", optimize=True)


def _draw_panel_layout(draw: ImageDraw.Draw, card: dict):
    title_font = _load_font(FONT_HEAVY, 78)
    body_font = _load_font(FONT_BOLD, 42)
    text_x = 160
    text_y = 200

    draw.text(
        (text_x, text_y), card["title"], font=title_font,
        fill=(255, 255, 255), stroke_width=5, stroke_fill=(0, 0, 0),
    )
    wrapped_body = "\n".join(textwrap.wrap(card["body"], width=15, break_long_words=False))
    draw.multiline_text(
        (text_x + 2, text_y + 130), wrapped_body, font=body_font,
        fill=(230, 235, 240), spacing=16,
        stroke_width=3, stroke_fill=(0, 0, 0),
    )


def _draw_split_layout(draw: ImageDraw.Draw, card: dict):
    title_font = _load_font(FONT_HEAVY, 72)
    body_font = _load_font(FONT_BOLD, 38)

    draw.text(
        (140, 180), card["title"], font=title_font,
        fill=(255, 255, 255), stroke_width=5, stroke_fill=(0, 0, 0),
    )
    wrapped_body = "\n".join(textwrap.wrap(card["body"], width=15, break_long_words=False))
    draw.multiline_text(
        (140, 320), wrapped_body, font=body_font,
        fill=(235, 240, 245), spacing=18,
        stroke_width=3, stroke_fill=(0, 0, 0),
    )


def _draw_number_layout(draw: ImageDraw.Draw, card: dict):
    title_font = _load_font(FONT_HEAVY, 170)
    body_font = _load_font(FONT_BOLD, 44)
    accent = _accent_color(card["role"])

    bbox = draw.textbbox((0, 0), card["title"], font=title_font)
    title_w = bbox[2] - bbox[0]
    title_x = (VIDEO_WIDTH - title_w) // 2
    draw.text((title_x, 300), card["title"], font=title_font, fill=accent, stroke_width=6, stroke_fill=(0, 0, 0))

    wrapped_body = "\n".join(textwrap.wrap(card["body"], width=22, break_long_words=False))
    bbox_body = draw.multiline_textbbox((0, 0), wrapped_body, font=body_font, spacing=16)
    body_w = bbox_body[2] - bbox_body[0]
    body_x = (VIDEO_WIDTH - body_w) // 2
    draw.multiline_text(
        (body_x, 540), wrapped_body, font=body_font,
        fill=(245, 245, 245), spacing=16, align="center",
        stroke_width=3, stroke_fill=(0, 0, 0),
    )


def _draw_full_layout(draw: ImageDraw.Draw, card: dict):
    title_font = _load_font(FONT_HEAVY, 118)
    bbox = draw.multiline_textbbox((0, 0), card["title"], font=title_font, spacing=20)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    x = (VIDEO_WIDTH - width) // 2
    y = (VIDEO_HEIGHT - height) // 2
    draw.multiline_text(
        (x, y),
        card["title"],
        font=title_font,
        fill=(255, 255, 255),
        spacing=20,
        align="center",
        stroke_width=6,
        stroke_fill=(0, 0, 0),
    )


def _draw_corner_layout(draw: ImageDraw.Draw, card: dict):
    title_font = _load_font(FONT_HEAVY, 70)
    body_font = _load_font(FONT_BOLD, 34)

    text_x = 140
    text_y = 140
    draw.text(
        (text_x, text_y), card["title"], font=title_font,
        fill=(255, 255, 255), stroke_width=5, stroke_fill=(0, 0, 0),
    )

    if card["body"]:
        wrapped_body = "\n".join(textwrap.wrap(card["body"], width=16, break_long_words=False))
        draw.multiline_text(
            (text_x + 2, text_y + 110), wrapped_body, font=body_font,
            fill=(235, 240, 245), spacing=12,
            stroke_width=3, stroke_fill=(0, 0, 0),
        )


def _compose_video(
    storyboard: list[dict],
    background_paths: list[pathlib.Path],
    overlay_paths: list[pathlib.Path],
) -> pathlib.Path:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = pathlib.Path(tmp_dir)
        video_paths = []
        audio_paths = []
        role_offsets = {role: 0.0 for role in ROLE_AUDIO}

        previous_role = None
        previous_background = None
        previous_overlay = None

        for index, (card, background_path, overlay_path) in enumerate(
            zip(storyboard, background_paths, overlay_paths),
            start=1,
        ):
            role = card["role"]
            audio_path = ROLE_AUDIO[role]
            offset = role_offsets[role]
            role_offsets[role] += card["duration"]

            if previous_role and previous_role != role and previous_background is not None and previous_overlay is not None:
                pause_video = tmp / f"pause_{index:02d}.mp4"
                pause_audio = tmp / f"pause_{index:02d}.m4a"
                _make_pause_video(previous_background, previous_overlay, SECTION_PAUSE, pause_video)
                _make_silence_audio(SECTION_PAUSE, pause_audio)
                video_paths.append(pause_video)
                audio_paths.append(pause_audio)

            video_path = tmp / f"video_{index:02d}.mp4"
            audio_clip = tmp / f"audio_{index:02d}.m4a"
            zoom_dir = ROLE_ZOOM_DIR.get(role, "in")
            _make_video_clip(
                background_path,
                overlay_path,
                card["duration"],
                video_path,
                zoom_out=(zoom_dir == "out"),
            )
            _make_audio_clip(audio_path, offset, card["duration"], audio_clip)
            video_paths.append(video_path)
            audio_paths.append(audio_clip)

            previous_role = role
            previous_background = background_path
            previous_overlay = overlay_path

        raw_video = tmp / "raw_video.mp4"
        raw_audio = tmp / "raw_audio.m4a"
        final_audio = tmp / "final_audio.m4a"

        _concat_files(video_paths, raw_video)
        _concat_files(audio_paths, raw_audio)

        if BGM_PATH.exists():
            _mix_bgm(raw_audio, final_audio)
        else:
            shutil.copy2(raw_audio, final_audio)

        _mux_video_audio(raw_video, final_audio, OUTPUT_VIDEO)

    return OUTPUT_VIDEO


def _make_video_clip(
    background_path: pathlib.Path,
    overlay_path: pathlib.Path,
    duration: float,
    output_path: pathlib.Path,
    zoom_out: bool = False,
):
    # scale→crop 方式（iMovie Ken Burns 再現）
    # 背景を UPSCALE 倍に拡大し、crop 範囲をゆっくり動かす。
    # テキスト（overlay）は固定のまま合成する。
    up_w = int(VIDEO_WIDTH * UPSCALE)
    up_h = int(VIDEO_HEIGHT * UPSCALE)
    cx = (up_w - VIDEO_WIDTH) // 2
    cy = (up_h - VIDEO_HEIGHT) // 2
    # ズーム移動量（中央基準、片側のみ）
    pan_x = int(VIDEO_WIDTH * ZOOM_RATIO / 2)
    pan_y = int(VIDEO_HEIGHT * ZOOM_RATIO / 2)

    if zoom_out:
        # 狭い範囲 → 広い範囲（少し引いていく）
        crop_expr = (
            f"scale={up_w}:{up_h},"
            f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT}:"
            f"x='{cx + pan_x} - {2 * pan_x}*(t/{duration})':"
            f"y='{cy + pan_y} - {2 * pan_y}*(t/{duration})'"
        )
    else:
        # 広い範囲 → 狭い範囲（少し寄っていく）
        crop_expr = (
            f"scale={up_w}:{up_h},"
            f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT}:"
            f"x='{cx - pan_x} + {2 * pan_x}*(t/{duration})':"
            f"y='{cy - pan_y} + {2 * pan_y}*(t/{duration})'"
        )

    cmd = [
        "ffmpeg", "-loglevel", "error", "-y",
        "-loop", "1", "-i", str(background_path),
        "-loop", "1", "-i", str(overlay_path),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-filter_complex",
        (
            f"[0:v]{crop_expr}[bg];"
            f"[1:v]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}[fg];"
            "[bg][fg]overlay=0:0:format=auto,format=yuv420p[v]"
        ),
        "-map", "[v]",
        "-t", str(duration),
        "-r", "30",
        "-an",
        str(output_path),
    ]
    _run(cmd, timeout=120)


def _make_pause_video(
    background_path: pathlib.Path,
    overlay_path: pathlib.Path,
    duration: float,
    output_path: pathlib.Path,
):
    cmd = [
        "ffmpeg", "-loglevel", "error", "-y",
        "-loop", "1", "-i", str(background_path),
        "-loop", "1", "-i", str(overlay_path),
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-filter_complex",
        (
            f"[0:v]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}[bg];"
            f"[1:v]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}[fg];"
            "[bg][fg]overlay=0:0:format=auto,format=yuv420p[v]"
        ),
        "-map", "[v]",
        "-t", str(duration),
        "-an",
        str(output_path),
    ]
    _run(cmd, timeout=60)


def _make_audio_clip(audio_path: pathlib.Path, offset: float, duration: float, output_path: pathlib.Path):
    cmd = [
        "ffmpeg", "-loglevel", "error", "-y",
        "-ss", str(offset),
        "-t", str(duration),
        "-i", str(audio_path),
        "-vn",
        "-ac", "1",
        "-ar", "44100",
        "-c:a", "aac",
        "-b:a", "160k",
        str(output_path),
    ]
    _run(cmd, timeout=120)


def _make_silence_audio(duration: float, output_path: pathlib.Path):
    cmd = [
        "ffmpeg", "-loglevel", "error", "-y",
        "-f", "lavfi",
        "-i", "anullsrc=r=44100:cl=mono",
        "-t", str(duration),
        "-c:a", "aac",
        "-b:a", "128k",
        str(output_path),
    ]
    _run(cmd, timeout=60)


def _concat_files(paths: list[pathlib.Path], output_path: pathlib.Path):
    concat_list = output_path.parent / f"{output_path.stem}.txt"
    concat_list.write_text("".join(f"file '{path}'\n" for path in paths), encoding="utf-8")
    cmd = [
        "ffmpeg", "-loglevel", "error", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(output_path),
    ]
    _run(cmd, timeout=240)


def _mix_bgm(audio_path: pathlib.Path, output_path: pathlib.Path):
    cmd = [
        "ffmpeg", "-loglevel", "error", "-y",
        "-i", str(audio_path),
        "-stream_loop", "-1",
        "-i", str(BGM_PATH),
        "-filter_complex",
        (
            f"[1:a]volume={BGM_VOLUME},afade=t=in:d=2,afade=t=out:st=999:d=3[bgm];"
            "[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        ),
        "-map", "[aout]",
        "-c:a", "aac",
        "-b:a", "192k",
        str(output_path),
    ]
    _run(cmd, timeout=240)


def _mux_video_audio(video_path: pathlib.Path, audio_path: pathlib.Path, output_path: pathlib.Path):
    cmd = [
        "ffmpeg", "-loglevel", "error", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-map", "0:v",
        "-map", "1:a",
        "-c:v", "copy",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(output_path),
    ]
    _run(cmd, timeout=240)


def _prepare_background(bg_path: pathlib.Path) -> Image.Image:
    img = Image.open(bg_path).convert("RGB")
    img = _crop_to_landscape(img)
    img = img.filter(ImageFilter.GaussianBlur(radius=2))
    img = ImageEnhance.Brightness(img).enhance(0.50)
    return img


def _crop_to_landscape(img: Image.Image) -> Image.Image:
    src_w, src_h = img.size
    target_ratio = VIDEO_WIDTH / VIDEO_HEIGHT

    if src_w / src_h > target_ratio:
        crop_h = src_h
        crop_w = int(src_h * target_ratio)
    else:
        crop_w = src_w
        crop_h = int(src_w / target_ratio)

    left = (src_w - crop_w) // 2
    top = (src_h - crop_h) // 2
    img = img.crop((left, top, left + crop_w, top + crop_h))
    return img.resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.LANCZOS)


def _accent_color(role: str) -> tuple[int, int, int]:
    colors = {
        "hook": (220, 110, 90),
        "overview": (205, 170, 70),
        "why_painful": (145, 165, 210),
        "data": (100, 190, 255),
        "interpret": (120, 220, 180),
        "action": (255, 215, 120),
        "closing": (180, 235, 160),
    }
    return colors.get(role, (255, 255, 255))


def _draw_centered(draw: ImageDraw.Draw, text: str, font, color: tuple[int, int, int], y: int):
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    x = (THUMB_WIDTH - width) // 2
    draw.text((x, y), text, font=font, fill=color, stroke_width=5, stroke_fill=(0, 0, 0))


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
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    return float(result.stdout.strip())


def _run(cmd: list[str], timeout: int):
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "command failed")


if __name__ == "__main__":
    main()
