"""
video_gen.py
FFmpeg subprocess でスライド画像 + 音声 → 動画を合成するモジュール。

処理フロー:
  1. 各シーンを「静止画 + 音声」のクリップに変換
  2. 全クリップを concat で結合
  3. BGM をミキシング（assets/bgm_ambient.m4a）
  4. H.264 + AAC でエンコード

BGM設定:
  - ファイル: assets/bgm_ambient.m4a（差し替え可能）
  - 音量: -28〜-32 LUFS（ナレーションの邪魔をしないレベル）
  - ループ再生（動画の長さに合わせて自動ループ）
"""

import pathlib
import subprocess
import tempfile
from typing import Optional

# Shorts 解像度
SHORTS_WIDTH = 1080
SHORTS_HEIGHT = 1920

# BGM設定
ASSETS_DIR = pathlib.Path(__file__).parent / "assets"
BGM_PATH = ASSETS_DIR / "bgm_ambient.m4a"
BGM_VOLUME = 0.08  # ナレーション対比のBGM音量（0.08 ≈ -22dB、かなり小さい）


def compose_shorts_video(
    scenes: list,
    output_path: pathlib.Path,
) -> Optional[pathlib.Path]:
    """
    各シーンの画像+音声を結合して Shorts 動画を生成する。

    Args:
        scenes: audio_path と slide 情報を含む scenes リスト
        output_path: 出力する動画ファイルパス

    Returns:
        動画パス。失敗時は None。
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 音声がないシーンはスキップ
    valid_scenes = [s for s in scenes if s.get("audio_path")]
    if not valid_scenes:
        print("  [エラー] 音声のあるシーンがありません。動画生成をスキップします。")
        return None

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = pathlib.Path(tmp_dir)
        clip_paths = []

        # Step 1: 各シーンのクリップを生成
        for i, scene in enumerate(valid_scenes):
            idx = i + 1
            role = scene.get("role", "")
            clip_path = tmp / f"clip_{idx:02d}.mp4"
            slide_path = scene.get("slide_path", "")
            audio_path = scene.get("audio_path", "")
            duration = scene.get("actual_duration_sec", 5)

            # resolve の前に0.5秒の無音（間）を挿入
            if role == "resolve" and i > 0:
                prev_slide = valid_scenes[i - 1].get("slide_path", slide_path)
                pause_path = tmp / f"pause_{idx:02d}.mp4"
                if _make_silence_clip(prev_slide, 0.7, pause_path):
                    clip_paths.append(pause_path)
                    print(f"  断言前の間（0.7秒）を挿入...")

            subtitle_text = scene.get("text", "")
            print(f"  クリップ{idx}を生成中（{duration:.1f}秒）...")
            success = _make_scene_clip(
                slide_path, audio_path, duration, clip_path,
                subtitle_text=subtitle_text, tmp_dir=tmp,
            )
            if success:
                clip_paths.append(clip_path)
            else:
                print(f"    [エラー] クリップ{idx}の生成に失敗しました。")

        if not clip_paths:
            print("  [エラー] クリップが1つも生成できませんでした。")
            return None

        # Step 2: concat で全クリップを結合
        print(f"  {len(clip_paths)}クリップを結合中...")
        concat_list = tmp / "concat.txt"
        with open(concat_list, "w") as f:
            for cp in clip_paths:
                f.write(f"file '{cp}'\n")

        # BGMがある場合: concat → 一時ファイル → BGMミキシング → 最終出力
        # BGMがない場合: concat → 最終出力
        has_bgm = BGM_PATH.exists()
        concat_output = tmp / "concat_raw.mp4" if has_bgm else output_path

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            str(concat_output),
        ]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
        )

        if result.returncode != 0:
            print(f"  [エラー] 動画結合に失敗しました。")
            _save_debug("ffmpeg_concat_error.txt", result.stderr)
            return None

        # Step 3: BGM ミキシング
        if has_bgm:
            print(f"  BGMをミキシング中（音量: {BGM_VOLUME}）...")
            bgm_success = _mix_bgm(concat_output, output_path)
            if not bgm_success:
                print("  [警告] BGMミキシングに失敗。BGMなしで出力します。")
                import shutil
                shutil.move(str(concat_output), str(output_path))

    # 結果確認
    duration = _get_duration(output_path)
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"  動画生成完了: {output_path.name}（{duration:.1f}秒 / {size_mb:.1f}MB）")
    return output_path


def _make_scene_clip(
    slide_path: str,
    audio_path: str,
    duration: float,
    output_path: pathlib.Path,
    subtitle_text: str = "",
    tmp_dir: pathlib.Path = None,
) -> bool:
    """1シーンのクリップを生成する（静止画 + 音声 + 字幕焼き込み）。"""

    # 字幕テキストがあれば Pillow でスライド画像に焼き込む
    actual_slide = slide_path
    if subtitle_text and tmp_dir:
        sub_slide = _burn_subtitle(slide_path, subtitle_text, tmp_dir, output_path.stem)
        if sub_slide:
            actual_slide = str(sub_slide)

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(actual_slide),
        "-i", str(audio_path),
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-c:a", "aac",
        "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-vf", f"scale={SHORTS_WIDTH}:{SHORTS_HEIGHT}",
        "-shortest",
        str(output_path),
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            _save_debug(f"ffmpeg_clip_error_{output_path.stem}.txt", result.stderr)
            return False
        return output_path.exists()
    except subprocess.TimeoutExpired:
        print("    FFmpeg タイムアウト（60秒）")
        return False
    except Exception as e:
        print(f"    FFmpeg エラー: {e}")
        return False


def _burn_subtitle(
    slide_path: str,
    text: str,
    tmp_dir: pathlib.Path,
    stem: str,
) -> pathlib.Path:
    """Pillow でスライド画像に字幕テキストを焼き込む。"""
    try:
        import textwrap
        from PIL import Image, ImageDraw, ImageFont

        img = Image.open(slide_path).copy()
        draw = ImageDraw.Draw(img)

        # フォント読み込み
        font_path = "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"
        font = ImageFont.truetype(font_path, size=42)

        # 15文字で改行
        wrapped = "\n".join(textwrap.wrap(text, width=15))

        # テキストサイズを計測して中央下に配置
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=12)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (img.width - text_w) // 2
        y = img.height - text_h - 420

        # 黒縁（ストローク）+ 白文字
        draw.multiline_text(
            (x, y), wrapped, font=font, fill="white",
            stroke_width=3, stroke_fill="black",
            spacing=12, align="center",
        )

        out_path = tmp_dir / f"sub_{stem}.png"
        img.save(out_path)
        return out_path
    except Exception as e:
        print(f"    字幕焼き込みエラー: {e}")
        return None


def _mix_bgm(
    video_path: pathlib.Path,
    output_path: pathlib.Path,
) -> bool:
    """動画にBGMをミキシングする。BGMはループ再生、動画の長さに合わせて自動カット。"""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-stream_loop", "-1",  # BGMを無限ループ
        "-i", str(BGM_PATH),
        "-filter_complex",
        f"[1:a]volume={BGM_VOLUME},afade=t=in:d=1,afade=t=out:st=999:d=2[bgm];"
        f"[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]",
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",  # 映像は再エンコードなし
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(output_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            _save_debug("ffmpeg_bgm_error.txt", result.stderr)
            return False
        return output_path.exists()
    except Exception as e:
        print(f"    BGMミキシングエラー: {e}")
        return False


def _make_silence_clip(
    slide_path: str,
    duration: float,
    output_path: pathlib.Path,
) -> bool:
    """無音の静止画クリップを生成する（断言前の「間」用）。"""
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(slide_path),
        "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-c:a", "aac",
        "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-vf", f"scale={SHORTS_WIDTH}:{SHORTS_HEIGHT}",
        "-t", str(duration),
        str(output_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0 and output_path.exists()
    except Exception:
        return False


def _get_duration(video_path: pathlib.Path) -> float:
    """FFprobe で動画の長さ（秒）を取得する。"""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def _save_debug(filename: str, content: str):
    """デバッグ情報を debug/ に保存する。"""
    debug_dir = pathlib.Path(__file__).parent / "debug"
    debug_dir.mkdir(exist_ok=True)
    try:
        (debug_dir / filename).write_text(content, encoding="utf-8")
    except Exception:
        pass
