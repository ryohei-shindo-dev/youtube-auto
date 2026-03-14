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

FONT_HEAVY = "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"
FONT_BOLD = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"
FONT_REGULAR = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"
FONT_MINCHO = "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc"

TITLE = "含み損がつらい夜に聞く、静かな整理"
DESCRIPTION = (
    "含み損の夜は、数字そのものより、\n"
    "自分の判断が間違っていた気がしてつらくなります。\n\n"
    "この動画では、金融危機の数字を一つ置きながら、\n"
    "含み損で眠れない夜に、今日は何をしないのがいいのかを静かに整理します。\n\n"
    "長期投資 / 積立投資 / NISA / 投資メンタル を前提にした内容です。\n\n"
    "※投資助言ではありません\n"
    "※特定の金融商品の購入・売却を勧めるものではありません\n\n"
    "YouTube Shorts「ガチホのモチベ」では、\n"
    "長期投資を続けるモチベーションを毎日投稿しています。\n\n"
    "#長期投資 #積立投資 #投資メンタル"
)
TAGS = ["長期投資", "積立投資", "投資メンタル", "NISA", "資産形成", "含み損", "ガチホ"]

ROLE_AUDIO = {
    "hook": LONG_DIR / "audio" / "01_hook.mp3",
    "overview": LONG_DIR / "audio" / "02_overview.mp3",
    "why_painful": LONG_DIR / "audio" / "03_why_painful.mp3",
    "data": LONG_DIR / "audio" / "04_data.mp3",
    "interpret": LONG_DIR / "audio" / "05_interpret.mp3",
    "action": LONG_DIR / "audio" / "06_action.mp3",
    "closing": LONG_DIR / "audio" / "07_closing.mp3",
}

PHOTOS_DIR = ASSETS_DIR / "photos"
ROLE_BG = {
    "hook": PHOTOS_DIR / "anxiety" / "anxiety05.jpg",
    "overview": PHOTOS_DIR / "anxiety" / "anxiety03.jpg",
    "why_painful": PHOTOS_DIR / "comparison" / "comparison05.jpg",
    "data": PHOTOS_DIR / "data" / "data01.jpg",
    "interpret": PHOTOS_DIR / "steady" / "steady05.jpg",
    "action": PHOTOS_DIR / "recovery" / "recovery01.jpg",
    "closing": PHOTOS_DIR / "steady" / "steady02.jpg",
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

# scale→crop 方式のパラメータ（iMovie Ken Burns 方式）
UPSCALE = 1.5
ZOOM_RATIO = 0.035  # 100% → 103.5%

# ロールごとのパン方向（単調にならないようバリエーション）
ROLE_PAN_DIR: dict[str, str] = {
    "hook": "left_to_right",
    "overview": "center",
    "why_painful": "right_to_left",
    "data": "bottom_to_top",
    "interpret": "center",
    "action": "top_to_bottom",
    "closing": "center",
}

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
    bg_path = card.get("bg_path") or ROLE_BG[card["role"]]
    if isinstance(bg_path, str):
        bg_path = pathlib.Path(bg_path)
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
    # 背景画像を読み込み、暗め加工
    bg_path = PHOTOS_DIR / "anxiety" / "anxiety05.jpg"
    if bg_path.exists():
        bg = Image.open(bg_path).convert("RGB")
        bg = _crop_to_landscape(bg, THUMB_WIDTH, THUMB_HEIGHT)
        from PIL import ImageEnhance
        bg = ImageEnhance.Brightness(bg).enhance(0.70)
        canvas = bg
    else:
        canvas = Image.new("RGB", (THUMB_WIDTH, THUMB_HEIGHT), (10, 10, 10))
    draw = ImageDraw.Draw(canvas)

    # サムネ用フォント（本編より少し強め）
    thumb_font_w8 = "/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc"
    thumb_font_w6 = "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"
    pain_font = _load_font(thumb_font_w8, 126)
    body_font = _load_font(thumb_font_w6, 62)

    line1 = "含み損の夜"
    line2 = "今日は動かない"

    # 左寄せ配置（やや上寄り）
    text_x = 80
    draw.text(
        (text_x, 200), line1, font=pain_font,
        fill=(240, 200, 60), stroke_width=6, stroke_fill=(0, 0, 0),
    )
    draw.text(
        (text_x, 360), line2, font=body_font,
        fill=(255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0),
    )

    canvas.save(output_path, "PNG", optimize=True)


def _draw_panel_layout(draw: ImageDraw.Draw, card: dict):
    title_font = _load_font(FONT_HEAVY, 82)
    body_font = _load_font(FONT_BOLD, 58)
    text_x = 160
    text_y = 200

    draw.text(
        (text_x, text_y), card["title"], font=title_font,
        fill=(255, 255, 255), stroke_width=5, stroke_fill=(0, 0, 0),
    )
    wrapped_body = "\n".join(textwrap.wrap(card["body"], width=13, break_long_words=False))
    draw.multiline_text(
        (text_x + 2, text_y + 140), wrapped_body, font=body_font,
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
    accent = _accent_color(card["role"])

    bbox = draw.textbbox((0, 0), card["title"], font=title_font)
    title_w = bbox[2] - bbox[0]
    title_x = (VIDEO_WIDTH - title_w) // 2
    draw.text((title_x, 300), card["title"], font=title_font, fill=accent, stroke_width=6, stroke_fill=(0, 0, 0))

    wrapped_body = "\n".join(textwrap.wrap(card["body"], width=18, break_long_words=False))
    bbox_body = draw.multiline_textbbox((0, 0), wrapped_body, font=body_font, spacing=18)
    body_w = bbox_body[2] - bbox_body[0]
    body_x = (VIDEO_WIDTH - body_w) // 2
    draw.multiline_text(
        (body_x, 560), wrapped_body, font=body_font,
        fill=(245, 245, 245), spacing=18, align="center",
        stroke_width=4, stroke_fill=(0, 0, 0),
    )


def _draw_full_layout(draw: ImageDraw.Draw, card: dict):
    title_font = _load_font(FONT_MINCHO, 108)
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
    title_font = _load_font(FONT_HEAVY, 78)
    body_font = _load_font(FONT_BOLD, 56)

    text_x = 140
    text_y = 140
    draw.text(
        (text_x, text_y), card["title"], font=title_font,
        fill=(255, 255, 255), stroke_width=5, stroke_fill=(0, 0, 0),
    )

    if card["body"]:
        wrapped_body = "\n".join(textwrap.wrap(card["body"], width=14, break_long_words=False))
        draw.multiline_text(
            (text_x + 2, text_y + 130), wrapped_body, font=body_font,
            fill=(235, 240, 245), spacing=14,
            stroke_width=3, stroke_fill=(0, 0, 0),
        )


def _group_by_role(storyboard, background_paths, overlay_paths):
    """ストーリーボードを連続する同じロールごとにグループ化する。"""
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
) -> pathlib.Path:
    groups = _group_by_role(storyboard, background_paths, overlay_paths)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = pathlib.Path(tmp_dir)
        video_paths = []
        audio_paths = []

        for gi, group in enumerate(groups):
            role = group["role"]
            cards = group["cards"]
            total_dur = sum(c["duration"] for c in cards)

            # セクション切替時に間を挿入
            if gi > 0:
                prev_group = groups[gi - 1]
                prev_bg = prev_group["bgs"][-1]
                prev_ov = prev_group["overlays"][-1]
                pause_video = tmp / f"pause_{gi:02d}.mp4"
                pause_audio = tmp / f"pause_{gi:02d}.m4a"
                _make_pause_video(prev_bg, prev_ov, SECTION_PAUSE, pause_video)
                _make_silence_audio(SECTION_PAUSE, pause_audio)
                video_paths.append(pause_video)
                audio_paths.append(pause_audio)

            # ロール全体で1本の連続クリップ（背景カットなし、テキストだけ切替）
            zoom_dir = ROLE_ZOOM_DIR.get(role, "in")
            pan_dir = ROLE_PAN_DIR.get(role, "center")

            role_video = tmp / f"role_{gi:02d}_{role}.mp4"
            _make_role_clip(
                group["bgs"][0],
                group["overlays"],
                cards,
                total_dur,
                role_video,
                zoom_out=(zoom_dir == "out"),
                pan_dir=pan_dir,
            )
            video_paths.append(role_video)

            # 音声クリップ（ロール全体で1つ）
            audio_clip = tmp / f"audio_{gi:02d}_{role}.m4a"
            _make_audio_clip(ROLE_AUDIO[role], 0.0, total_dur, audio_clip)
            audio_paths.append(audio_clip)

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


def _make_role_clip(
    background_path: pathlib.Path,
    overlay_paths: list[pathlib.Path],
    cards: list[dict],
    total_dur: float,
    output_path: pathlib.Path,
    zoom_out: bool = False,
    pan_dir: str = "center",
):
    """ロール全体で1本の連続クリップを生成。
    背景はカットなしでKen Burnsパン、テキストだけ時間指定で切り替える。"""
    up_w = int(VIDEO_WIDTH * UPSCALE)
    up_h = int(VIDEO_HEIGHT * UPSCALE)
    cx = (up_w - VIDEO_WIDTH) // 2
    cy = (up_h - VIDEO_HEIGHT) // 2
    pan_x = int(VIDEO_WIDTH * ZOOM_RATIO / 2)
    pan_y = int(VIDEO_HEIGHT * ZOOM_RATIO / 2)

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

    crop_expr = (
        f"scale={up_w}:{up_h},"
        f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT}:"
        f"x={x_expr}:y={y_expr}"
    )

    # 入力: [0]=背景, [1]=overlay1, [2]=overlay2, ...
    inputs = ["-loop", "1", "-i", str(background_path)]
    for ov_path in overlay_paths:
        inputs += ["-loop", "1", "-i", str(ov_path)]

    # フィルタ: 背景にKen Burns → 各オーバーレイを時間指定で重ねる
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
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-t", str(total_dur),
        "-r", "30",
        "-an",
        str(output_path),
    ]
    _run(cmd, timeout=300)


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
            "[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=0[aout]"
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
