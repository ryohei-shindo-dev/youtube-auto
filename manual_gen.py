"""手動台本からShortsパイプラインを実行する。

台本をClaude APIで生成せず、手動で定義した台本で
音声→スライド→動画→サムネ→字幕→note→SNSキャプションを一括生成する。

使い方:
    python manual_gen.py
"""
from __future__ import annotations

import json
import pathlib
import shutil
from datetime import datetime

from dotenv import load_dotenv

SCRIPT_DIR = pathlib.Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")

import voice_gen
import slide_gen
import video_gen
import subtitle_gen
import note_gen
import social_gen

PENDING_DIR = SCRIPT_DIR / "pending"
DONE_DIR = SCRIPT_DIR / "done"

# ━━━ 手動台本 ━━━
SCRIPT_DATA = {
    "title": "自分だけ増えてない｜比べなくていい理由",
    "topic": "比較焦りと個別株の勝率",
    "description": (
        "周りだけ増えているように見える日はありませんか。"
        "誰かの数字が気になるのは自然なことです。"
        "でも、個別株の勝者は全体の3割以下。"
        "他人の速度はあなたの答えじゃない。"
        "自分のペースで続けていれば、それでいい。"
        "※投資助言ではありません"
    ),
    "tags": [
        "比較焦り",
        "長期投資",
        "インデックス投資",
        "投資モチベーション",
        "ガチホ",
    ],
    "scenes": [
        {
            "role": "hook",
            "text": "自分だけ増えてない。",
            "slide_text": "自分だけ増えてない",
            "duration_sec": 2,
        },
        {
            "role": "empathy",
            "text": "誰かの数字が気になる日がある。",
            "slide_text": "誰かの数字が気になる",
            "duration_sec": 3,
        },
        {
            "role": "data",
            "text": "でも、個別株の勝者は全体の3割以下。",
            "slide_text": "勝者は全体の3割以下",
            "duration_sec": 4,
        },
        {
            "role": "resolve",
            "text": "だから、他人の速度はあなたの答えじゃない。",
            "slide_text": "あなたの答えじゃない",
            "duration_sec": 3,
        },
        {
            "role": "closing",
            "text": "自分のペースでいい。",
            "slide_text": "自分のペースでいい",
            "duration_sec": 2,
        },
    ],
}

THEME = "比較焦り系"


def main():
    PENDING_DIR.mkdir(exist_ok=True)
    DONE_DIR.mkdir(exist_ok=True)

    script_data = SCRIPT_DATA
    scenes = script_data["scenes"]

    print("=" * 50)
    print("手動台本 Shorts 生成パイプライン")
    print(f"  タイトル: {script_data['title']}")
    print(f"  テーマ: {THEME}")
    print("=" * 50)

    # ── Step 1: 音声生成 ──
    print("\n[Step 1/6] 音声生成")
    scenes = voice_gen.generate_voice_for_scenes(scenes, PENDING_DIR)
    success_audio = sum(1 for s in scenes if s.get("audio_path"))
    if success_audio == 0:
        print("\n[失敗] 音声が1つも生成できませんでした。")
        return

    # ── Step 2: スライド画像生成 ──
    print("\n[Step 2/6] スライド画像生成")
    slide_gen.generate_all_slides(scenes, PENDING_DIR, theme=THEME, use_photo=True)

    # ── Step 3: サムネフレーム生成 ──
    print("\n[Step 3/6] サムネフレーム生成")
    thumb_frame_path = ""
    thumb_result = slide_gen.generate_thumbnail_frame(
        scenes, PENDING_DIR / "thumbnail_frame.png",
        title=script_data.get("title", ""),
    )
    if thumb_result:
        thumb_frame_path = thumb_result["path"]
        script_data["thumbnail_text"] = thumb_result["text"]
        script_data["thumbnail_photo"] = thumb_result["photo"]
    else:
        print("  [警告] サムネフレーム生成失敗")

    # ── Step 4: 動画合成 ──
    print("\n[Step 4/6] 動画合成")
    video_path = video_gen.compose_shorts_video(
        scenes, PENDING_DIR / "output.mp4",
        use_photo=True,
        thumbnail_frame_path=thumb_frame_path,
    )
    if not video_path:
        print("\n[失敗] 動画合成に失敗しました。")
        return

    # ── Step 5: 字幕・文字起こし生成 ──
    print("\n[Step 5/6] 字幕・文字起こし生成")
    subtitle_gen.generate_subtitle_files(script_data, scenes, PENDING_DIR)

    # ── Step 6: SNSキャプション生成 ──
    print("\n[Step 6/6] SNSキャプション生成")
    social_gen.generate_social_captions(script_data, PENDING_DIR)

    # ── 結果サマリー ──
    print("\n" + "=" * 50)
    print("生成完了！")
    print("=" * 50)
    print(f"  タイトル: {script_data['title']}")
    print(f"  動画: {video_path}")
    if thumb_frame_path:
        print(f"  サムネフレーム: {thumb_frame_path}")

    # アーカイブ
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_dir = DONE_DIR / timestamp
    archive_dir.mkdir(parents=True, exist_ok=True)
    for f in PENDING_DIR.iterdir():
        if f.is_file():
            shutil.move(str(f), str(archive_dir / f.name))
    print(f"\n  アーカイブ: {archive_dir}")


if __name__ == "__main__":
    main()
