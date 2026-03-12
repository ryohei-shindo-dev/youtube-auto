"""第1弾の継続モチベ系動画のresolve/closing/empathyを修正して再合成する。

変更したシーンのみ音声を再生成し、スライドを全面再生成して動画を再合成する。
"""
from __future__ import annotations

import json
import pathlib
import shutil

from dotenv import load_dotenv
load_dotenv(pathlib.Path(__file__).parent / ".env")

import voice_gen
import slide_gen
import video_gen
import subtitle_gen

DONE_DIR = pathlib.Path(__file__).parent / "done"
PENDING_DIR = pathlib.Path(__file__).parent / "pending"

# 修正定義: フォルダ名 → 変更するシーン
REPAIRS = {
    "20260312_091150": {
        # 「積立、変えなかった。それだけで十分です」
        "empathy": {
            "text": "あなたも、設定を変えたくなる。",
            "slide_text": "あなたも、設定を変えたくなる",
        },
        "resolve": {
            "text": "そう、変えなかったことも、積み上がっています。",
            "slide_text": "変えなかったことも積み上がっています",
        },
    },
    "20260312_091252": {
        # 「1年続けた人に、静かに起きていること」
        "resolve": {
            "text": "そう、何もしない日にも、意味があります。",
            "slide_text": "何もしない日にも意味があります",
        },
    },
    "20260312_091552": {
        # 「目立たない日々に、ちゃんと意味がある」
        "empathy": {
            "text": "あなただけじゃない。ガチホしてますか？",
            "slide_text": "ガチホしてますか",
        },
        "resolve": {
            "text": "そう、続いているなら、それで十分です。",
            "slide_text": "続いているならそれで十分です",
        },
        "closing": {
            "text": "それでも、今日もそのままでいい。フォローお願いします。",
            "slide_text": "今日もそのままでいい。フォロー",
        },
    },
}


def repair_one(folder_name: str, changes: dict):
    """1本の動画を修正・再合成する。"""
    done_path = DONE_DIR / folder_name
    transcript_path = done_path / "transcript.json"

    if not transcript_path.exists():
        print(f"  [スキップ] {folder_name}: transcript.json が見つかりません")
        return

    with open(transcript_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    scenes = data["scenes"]
    changed_roles = set()

    # テキストを修正
    for s in scenes:
        role = s.get("role", "")
        if role in changes:
            old_text = s["text"]
            s["text"] = changes[role]["text"]
            s["slide_text"] = changes[role]["slide_text"]
            changed_roles.add(role)
            print(f"  [{role}] 「{old_text}」→「{s['text']}」")

    if not changed_roles:
        print(f"  [スキップ] {folder_name}: 変更なし")
        return

    # pending/ を作業ディレクトリとして使用
    PENDING_DIR.mkdir(exist_ok=True)
    for f in PENDING_DIR.iterdir():
        if f.is_file():
            f.unlink()

    # 変更されていないシーンの音声ファイルをコピー
    for i, s in enumerate(scenes, 1):
        role = s.get("role", "")
        audio_src = done_path / f"audio_{i:02d}.mp3"
        if role not in changed_roles and audio_src.exists():
            shutil.copy2(audio_src, PENDING_DIR / f"audio_{i:02d}.mp3")

    # 変更されたシーンの音声を個別に再生成
    print(f"  音声再生成中（{len(changed_roles)}シーン）...")
    for i, s in enumerate(scenes, 1):
        role = s.get("role", "")
        if role not in changed_roles:
            audio_path = PENDING_DIR / f"audio_{i:02d}.mp3"
            s["audio_path"] = str(audio_path)
            s["actual_duration_sec"] = voice_gen._get_audio_duration(audio_path)
            continue

        # 1シーンだけのリストを作って voice_gen に渡す
        temp_dir = PENDING_DIR / "_temp_voice"
        temp_dir.mkdir(exist_ok=True)
        temp_scene = [dict(s)]
        voice_gen.generate_voice_for_scenes(temp_scene, temp_dir)

        # audio_01.mp3 として生成される → 正しい番号にリネーム
        temp_audio = temp_dir / "audio_01.mp3"
        target_audio = PENDING_DIR / f"audio_{i:02d}.mp3"
        if temp_audio.exists():
            shutil.move(str(temp_audio), str(target_audio))
        s["audio_path"] = str(target_audio)
        s["actual_duration_sec"] = temp_scene[0].get("actual_duration_sec", 0)
        # 一時ディレクトリを削除
        shutil.rmtree(temp_dir, ignore_errors=True)

    # スライド再生成（全シーン）
    print(f"  スライド再生成中...")
    theme_name = "継続モチベ系"
    slide_gen.generate_all_slides(scenes, PENDING_DIR, theme=theme_name)
    for i, s in enumerate(scenes, 1):
        s["slide_path"] = str(PENDING_DIR / f"slide_{i:02d}.png")

    # 動画再合成
    print(f"  動画再合成中...")
    video_gen.compose_shorts_video(scenes, PENDING_DIR / "output.mp4")

    # 尺を再計算
    total_sec = sum(s.get("actual_duration_sec", 0) for s in scenes)
    data["total_duration_sec"] = total_sec
    current = 0.0
    for s in scenes:
        dur = s.get("actual_duration_sec", s.get("duration_sec", 0))
        s["start_sec"] = round(current, 2)
        s["end_sec"] = round(current + dur, 2)
        s["duration_sec"] = round(dur, 2)
        current += dur

    # 字幕再生成
    subtitle_gen.generate_subtitle_files(data, scenes, PENDING_DIR)

    # audio_path, slide_path, actual_duration_sec はtranscript.jsonに不要
    for s in scenes:
        s.pop("audio_path", None)
        s.pop("slide_path", None)
        s.pop("actual_duration_sec", None)

    # done/ にコピーバック（元のファイルを上書き）
    for f in PENDING_DIR.iterdir():
        if f.is_file() and f.name != ".DS_Store":
            dest = done_path / f.name
            shutil.copy2(f, dest)

    print(f"  ✓ 修正完了: {folder_name}（{total_sec:.1f}秒）")


def main():
    print("=" * 60)
    print("  第1弾 継続モチベ系 修正スクリプト")
    print("=" * 60)

    for folder_name, changes in REPAIRS.items():
        print(f"\n--- {folder_name} ---")
        try:
            repair_one(folder_name, changes)
        except Exception as e:
            print(f"  ✗ 失敗: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n全修正完了")


if __name__ == "__main__":
    main()
