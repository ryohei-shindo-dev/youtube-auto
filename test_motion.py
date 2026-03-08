"""
test_motion.py
長尺動画の動き方式を比較する検証スクリプト。
本編は一切触らず、5秒の短いクリップを3パターン出力する。

出力先: long_video/motion_test/
  - A_static.mp4       … 完全静止（基準線）
  - B_scalecrop_in.mp4  … scale→crop ズームイン（iMovie Ken Burns 方式）
  - B_scalecrop_out.mp4 … scale→crop ズームアウト
  - C_zoompan_in.mp4    … 現行 zoompan ズームイン（比較用）

使い方:
  venv/bin/python test_motion.py
"""
from __future__ import annotations

import pathlib
import subprocess

BASE_DIR = pathlib.Path(__file__).parent
OUT_DIR = BASE_DIR / "long_video" / "motion_test"
# 既存の背景・オーバーレイを借用（本編ファイルは読むだけ）
BG_PATH = BASE_DIR / "long_video" / "01_fukumison" / "slides" / "01_hook.png"
OV_PATH = BASE_DIR / "long_video" / "01_fukumison" / "overlays" / "01_hook.png"

WIDTH = 1920
HEIGHT = 1080
DURATION = 5.0
FPS = 30

# scale→crop 方式のパラメータ
# 背景を 1.5 倍に拡大し、crop 範囲をゆっくり動かす
UPSCALE_W = int(WIDTH * 1.5)   # 2880
UPSCALE_H = int(HEIGHT * 1.5)  # 1620
# ズーム移動量（ピクセル）: 片側80px = 全体で約8%の動き
PAN_X = 80
PAN_Y = 45


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not BG_PATH.exists() or not OV_PATH.exists():
        print("エラー: 背景またはオーバーレイが見つかりません。")
        print(f"  背景: {BG_PATH}")
        print(f"  オーバーレイ: {OV_PATH}")
        return

    print("=== 動き方式の比較テスト ===")
    print(f"各クリップ: {DURATION}秒 / {FPS}fps / {WIDTH}x{HEIGHT}")
    print()

    # --- A. 完全 static ---
    print("[A] 完全 static …")
    a_out = OUT_DIR / "A_static.mp4"
    _run_ffmpeg([
        "-loop", "1", "-i", str(BG_PATH),
        "-loop", "1", "-i", str(OV_PATH),
        "-filter_complex",
        (
            f"[0:v]scale={WIDTH}:{HEIGHT}[bg];"
            f"[1:v]scale={WIDTH}:{HEIGHT}[fg];"
            "[bg][fg]overlay=0:0:format=auto,format=yuv420p[v]"
        ),
        "-map", "[v]",
        "-t", str(DURATION),
        "-r", str(FPS),
        "-c:v", "libx264",
        "-tune", "stillimage",
        str(a_out),
    ])
    print(f"  -> {a_out}")

    # --- B. scale→crop 方式 (iMovie Ken Burns 再現) ---
    # ズームイン: 広い範囲から狭い範囲へ（中心に寄っていく）
    print("[B] scale→crop ズームイン …")
    b_in_out = OUT_DIR / "B_scalecrop_in.mp4"
    # 開始: crop の左上が (center-PAN, center-PAN)
    # 終了: crop の左上が (center+PAN, center+PAN)
    # → 見た目は「少し引いた状態から寄っていく」
    cx = (UPSCALE_W - WIDTH) // 2
    cy = (UPSCALE_H - HEIGHT) // 2
    crop_in = (
        f"scale={UPSCALE_W}:{UPSCALE_H},"
        f"crop={WIDTH}:{HEIGHT}:"
        f"x='{cx - PAN_X} + {2 * PAN_X}*(t/{DURATION})':"
        f"y='{cy - PAN_Y} + {2 * PAN_Y}*(t/{DURATION})'"
    )
    _run_ffmpeg([
        "-loop", "1", "-i", str(BG_PATH),
        "-loop", "1", "-i", str(OV_PATH),
        "-filter_complex",
        (
            f"[0:v]{crop_in}[bg];"
            f"[1:v]scale={WIDTH}:{HEIGHT}[fg];"
            "[bg][fg]overlay=0:0:format=auto,format=yuv420p[v]"
        ),
        "-map", "[v]",
        "-t", str(DURATION),
        "-r", str(FPS),
        "-c:v", "libx264",
        str(b_in_out),
    ])
    print(f"  -> {b_in_out}")

    # ズームアウト: 狭い範囲から広い範囲へ
    print("[B] scale→crop ズームアウト …")
    b_out_out = OUT_DIR / "B_scalecrop_out.mp4"
    crop_out = (
        f"scale={UPSCALE_W}:{UPSCALE_H},"
        f"crop={WIDTH}:{HEIGHT}:"
        f"x='{cx + PAN_X} - {2 * PAN_X}*(t/{DURATION})':"
        f"y='{cy + PAN_Y} - {2 * PAN_Y}*(t/{DURATION})'"
    )
    _run_ffmpeg([
        "-loop", "1", "-i", str(BG_PATH),
        "-loop", "1", "-i", str(OV_PATH),
        "-filter_complex",
        (
            f"[0:v]{crop_out}[bg];"
            f"[1:v]scale={WIDTH}:{HEIGHT}[fg];"
            "[bg][fg]overlay=0:0:format=auto,format=yuv420p[v]"
        ),
        "-map", "[v]",
        "-t", str(DURATION),
        "-r", str(FPS),
        "-c:v", "libx264",
        str(b_out_out),
    ])
    print(f"  -> {b_out_out}")

    # --- C. 現行 zoompan（比較用） ---
    print("[C] zoompan ズームイン（現行方式）…")
    c_out = OUT_DIR / "C_zoompan_in.mp4"
    total_frames = int(DURATION * FPS)
    z_expr = f"1.0+0.04*(on/{total_frames})"
    zp_filter = (
        f"zoompan=z='{z_expr}'"
        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={total_frames}:s={WIDTH}x{HEIGHT}:fps={FPS}"
    )
    _run_ffmpeg([
        "-loop", "1", "-i", str(BG_PATH),
        "-loop", "1", "-i", str(OV_PATH),
        "-filter_complex",
        (
            f"[0:v]{zp_filter}[bg];"
            f"[1:v]scale={WIDTH}:{HEIGHT}[fg];"
            "[bg][fg]overlay=0:0:format=auto,format=yuv420p[v]"
        ),
        "-map", "[v]",
        "-t", str(DURATION),
        "-c:v", "libx264",
        str(c_out),
    ])
    print(f"  -> {c_out}")

    print()
    print("=== 完了 ===")
    print("Finder で long_video/motion_test/ を開いて比較してください。")
    print("  A = 静止（基準）")
    print("  B = scale→crop（iMovie Ken Burns 方式）")
    print("  C = zoompan（現行 / 揺れの原因比較用）")


def _run_ffmpeg(args: list[str]):
    cmd = ["ffmpeg", "-loglevel", "error", "-y"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"  FFmpeg エラー: {result.stderr.strip()}")
        raise RuntimeError(result.stderr.strip() or "ffmpeg failed")


if __name__ == "__main__":
    main()
