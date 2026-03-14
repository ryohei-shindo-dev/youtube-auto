"""
long_video_builder_02.py
2本目「積立3年目が一番つらい理由」のスライド生成・サムネイル・動画合成。

背景にストック写真（assets/photos/）を使用。
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import tempfile
import textwrap

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from long_voice_gen import SCRIPT_02_SCENES

BASE_DIR = pathlib.Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
PHOTOS_DIR = ASSETS_DIR / "photos"
LONG_DIR = BASE_DIR / "long_video" / "02_tsumitate3"
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
FONT_MINCHO = "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc"

TITLE = "積み立て3年目が一番つらい理由｜増えない時期に何が起きているか"
DESCRIPTION = (
    "積立3年目は、いちばんしんどい時期です。\n"
    "新鮮さが消え、結果が出るには早すぎる。\n\n"
    "この動画では、なぜ3年目に気持ちが折れやすいのか、\n"
    "増えない時期に何が起きているのかを、数字を使って静かに整理します。\n\n"
    "長期投資 / 積立投資 / NISA / 投資メンタル を前提にした内容です。\n\n"
    "※投資助言ではありません\n"
    "※特定の金融商品の購入・売却を勧めるものではありません\n\n"
    "YouTube Shorts「ガチホのモチベ」では、\n"
    "長期投資を続けるモチベーションを毎日投稿しています。\n\n"
    "#長期投資 #積立投資 #投資メンタル"
)
TAGS = ["長期投資", "積立投資", "投資メンタル", "NISA", "資産形成", "積立3年目", "ガチホ"]

ROLE_AUDIO = {
    "hook": LONG_DIR / "audio" / "01_hook.mp3",
    "overview": LONG_DIR / "audio" / "02_overview.mp3",
    "why_painful": LONG_DIR / "audio" / "03_why_painful.mp3",
    "data": LONG_DIR / "audio" / "04_data.mp3",
    "interpret": LONG_DIR / "audio" / "05_interpret.mp3",
    "action": LONG_DIR / "audio" / "06_action.mp3",
    "closing": LONG_DIR / "audio" / "07_closing.mp3",
}

# ストック写真を背景に使用（ChatGPT提案に基づく）
ROLE_BG = {
    "hook": PHOTOS_DIR / "comparison" / "comparison02.jpg",
    "overview": PHOTOS_DIR / "anxiety" / "anxiety02.jpg",
    "why_painful": PHOTOS_DIR / "anxiety" / "anxiety01.jpg",
    "data": PHOTOS_DIR / "data" / "data03.jpg",
    "interpret": PHOTOS_DIR / "steady" / "steady03.jpg",
    "action": PHOTOS_DIR / "recovery" / "recovery03.jpg",
    "closing": PHOTOS_DIR / "steady" / "steady01.jpg",
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

# ロールごとのパン方向（単調にならないようバリエーションを付ける）
# "center": ズームのみ、パンなし
# "left_to_right": 左→右にパン
# "right_to_left": 右→左にパン
# "top_to_bottom": 上→下にパン
# "bottom_to_top": 下→上にパン
ROLE_PAN_DIR: dict[str, str] = {
    "hook": "right_to_left",
    "overview": "center",
    "why_painful": "left_to_right",
    "data": "bottom_to_top",
    "interpret": "center",
    "action": "top_to_bottom",
    "closing": "center",
}

STORYBOARD = [
    # hook: 3カード
    {"role": "hook", "title": "積立3年目", "body": "いちばんしんどい", "share": 1.0, "layout": "number"},
    {"role": "hook", "title": "新鮮さが消えた", "body": "結果が出るには早すぎる", "share": 1.0, "layout": "corner"},
    {"role": "hook", "title": "今日の話", "body": "なぜ3年目がきついのか\nその正体を整理する", "share": 1.0, "layout": "split"},
    # overview: 2カード
    {"role": "overview", "title": "二つだけ整理する", "body": "3年目に折れやすい理由\n増えない時期に起きていること", "share": 1.0, "layout": "corner"},
    {"role": "overview", "title": "退場しない", "body": "Shorts の話を今日は少し丁寧に", "share": 1.0, "layout": "number"},
    # why_painful: 5カード（60秒と長いので多めに）
    {"role": "why_painful", "title": "1年目は新鮮", "body": "", "share": 0.7, "layout": "full"},
    {"role": "why_painful", "title": "2年目は慣れ", "body": "", "share": 0.5, "layout": "full"},
    {"role": "why_painful", "title": "3年目の問題", "body": "振れ幅は大きくなるのに\n複利の効果はまだ小さい", "share": 1.2, "layout": "split"},
    {"role": "why_painful", "title": "期待と現実のズレ", "body": "減る実感だけが先に来る", "share": 1.0, "layout": "corner"},
    {"role": "why_painful", "title": "期待と現実の差が\nいちばん開く", "body": "", "share": 0.6, "layout": "full"},
    # data: 4カード
    {"role": "data", "title": "2000年開始", "body": "3年後 元本割れ", "share": 1.0, "layout": "number"},
    {"role": "data", "title": "ITバブル崩壊", "body": "3年続けて まだマイナス", "share": 0.8, "layout": "split"},
    {"role": "data", "title": "10年後 回復", "body": "20年後 大きく増加", "share": 1.0, "layout": "number"},
    {"role": "data", "title": "3年で判断しない", "body": "切り取る期間で景色が変わる", "share": 1.2, "layout": "corner"},
    # interpret: 3カード
    {"role": "interpret", "title": "増えていない\n≠意味がない", "body": "", "share": 1.0, "layout": "full"},
    {"role": "interpret", "title": "種を蒔く時期", "body": "複利は後半に効く仕組み", "share": 1.0, "layout": "corner"},
    {"role": "interpret", "title": "分かれ目", "body": "まだ結果が出る時期ではない\nと整理できるかどうか", "share": 1.0, "layout": "split"},
    # action: 2カード
    {"role": "action", "title": "月に一度で十分", "body": "確認して 閉じて 忘れる", "share": 1.0, "layout": "corner"},
    {"role": "action", "title": "設定を変えない", "body": "退場する人としない人の違い", "share": 1.0, "layout": "number"},
    # closing: 1カード
    {"role": "closing", "title": "3年目は途中", "body": "退屈は順調の証拠", "share": 1.0, "layout": "corner"},
]


def main():
    SLIDES_DIR.mkdir(parents=True, exist_ok=True)
    OVERLAYS_DIR.mkdir(parents=True, exist_ok=True)
    resolved_storyboard = _resolve_storyboard()

    print(f"スライド生成中（{len(resolved_storyboard)}枚）...")
    background_paths = []
    overlay_paths = []
    for index, card in enumerate(resolved_storyboard, start=1):
        background_path = SLIDES_DIR / f"{index:02d}_{card['role']}.png"
        overlay_path = OVERLAYS_DIR / f"{index:02d}_{card['role']}.png"
        _render_slide_layers(card, background_path, overlay_path)
        background_paths.append(background_path)
        overlay_paths.append(overlay_path)
        print(f"  [{index:02d}] {card['role']:15s} {card['title']:15s} ({card['duration']:.1f}秒)")

    print("\nサムネイル生成中...")
    _render_thumbnail(OUTPUT_THUMB)

    print("\n動画合成中...")
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
                "overlay_path": str(ov_path),
            }
            for card, bg_path, ov_path in zip(resolved_storyboard, background_paths, overlay_paths)
        ],
    }
    OUTPUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    total_sec = sum(c["duration"] for c in resolved_storyboard)
    print(f"\n=== 完了 ===")
    print(f"動画: {output_path}（{total_sec:.1f}秒 / {total_sec/60:.1f}分）")
    print(f"サムネイル: {OUTPUT_THUMB}")
    print(f"メタデータ: {OUTPUT_META}")


def _resolve_storyboard() -> list[dict]:
    cards_by_role: dict[str, list[dict]] = {}
    for card in STORYBOARD:
        cards_by_role.setdefault(card["role"], []).append(dict(card))

    resolved: list[dict] = []
    for scene in SCRIPT_02_SCENES:
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
    """サムネイル: comparison02写真 + 左寄せテキスト2行"""
    bg_path = PHOTOS_DIR / "comparison" / "comparison02.jpg"
    if bg_path.exists():
        bg = Image.open(bg_path).convert("RGB")
        bg = _crop_to_landscape(bg, THUMB_WIDTH, THUMB_HEIGHT)
        bg = ImageEnhance.Brightness(bg).enhance(0.70)
        canvas = bg
    else:
        canvas = Image.new("RGB", (THUMB_WIDTH, THUMB_HEIGHT), (10, 10, 10))
    draw = ImageDraw.Draw(canvas)

    thumb_font_w8 = "/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc"
    thumb_font_w6 = "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"
    pain_font = _load_font(thumb_font_w8, 126)
    body_font = _load_font(thumb_font_w6, 62)

    line1 = "積立3年目"
    line2 = "一番つらい"

    text_x = 80
    # 1行目: 黄色（痛みワード）
    draw.text(
        (text_x, 200), line1, font=pain_font,
        fill=(240, 200, 60), stroke_width=6, stroke_fill=(0, 0, 0),
    )
    # 2行目: 白
    draw.text(
        (text_x, 360), line2, font=body_font,
        fill=(255, 255, 255), stroke_width=3, stroke_fill=(0, 0, 0),
    )

    canvas.save(output_path, "PNG", optimize=True)


# ── レイアウト描画（1本目と同じ） ──────────────────────

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


# ── 動画合成 ──────────────────────────────────────────

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

            # セクション切替時に0.9秒の間を挿入
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
            print(f"  ロール [{role}] {len(cards)}カード {total_dur:.1f}秒 （パン: {pan_dir}）...")

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

        print(f"  {len(video_paths)} クリップを結合中...")
        _concat_files(video_paths, raw_video)
        _concat_files(audio_paths, raw_audio)

        if BGM_PATH.exists():
            print(f"  BGMミキシング中（音量: {BGM_VOLUME}）...")
            _mix_bgm(raw_audio, final_audio)
        else:
            shutil.copy2(raw_audio, final_audio)

        print(f"  映像+音声を結合中...")
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
    # 各オーバーレイをスケール
    for i in range(len(overlay_paths)):
        filter_parts.append(f"[{i+1}:v]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}[ov{i}]")

    # 時間指定でオーバーレイを重ねる
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

    # 最終出力にフォーマット指定
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
        "-c:a", "aac", "-b:a", "192k",
        str(output_path),
    ]
    _run(cmd, timeout=240)


def _mux_video_audio(video_path: pathlib.Path, audio_path: pathlib.Path, output_path: pathlib.Path):
    cmd = [
        "ffmpeg", "-loglevel", "error", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", "-c:a", "copy",
        "-movflags", "+faststart",
        str(output_path),
    ]
    _run(cmd, timeout=240)


# ── ユーティリティ ──────────────────────────────────────

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


def _accent_color(role: str) -> tuple:
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
