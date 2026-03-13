"""在庫全動画のスライド+動画をv2（縦型没入+横型分割の自動切替）で再生成する。

音声ファイルはそのまま流用し、スライド画像と動画のみ再生成する。
APIコストゼロ。
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

# プロジェクトルートをパスに追加
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import slide_gen
import video_gen

DONE_DIR = pathlib.Path(__file__).parent / "done"


def _get_target_folders() -> list[pathlib.Path]:
    """publish_queue.json に載っている未投稿フォルダのみ対象にする。"""
    queue_path = pathlib.Path(__file__).parent / "publish_queue.json"
    if not queue_path.exists():
        print("[エラー] publish_queue.json が見つかりません")
        return []

    queue = json.load(open(queue_path))
    queue_set = set(queue)

    folders = []
    for d in sorted(DONE_DIR.iterdir()):
        if not d.is_dir():
            continue
        if d.name not in queue_set:
            continue
        if not (d / "transcript.json").exists():
            continue
        audios = list(d.glob("audio_*.mp3"))
        if audios:
            folders.append(d)
    return folders


def _regen_one(folder: pathlib.Path) -> bool:
    """1フォルダのスライド+動画を再生成する。"""
    transcript = json.load(open(folder / "transcript.json"))
    scenes = transcript.get("scenes", [])
    if not scenes:
        print(f"  [スキップ] シーンなし: {folder.name}")
        return False

    # 音声ファイルの存在確認 + パス設定
    for i, scene in enumerate(scenes):
        audio_path = folder / f"audio_{i+1:02d}.mp3"
        if not audio_path.exists():
            print(f"  [スキップ] 音声なし: {folder.name}/audio_{i+1:02d}.mp3")
            return False
        scene["audio_path"] = str(audio_path)

    # Step 1: スライド再生成（v2 写真型、縦横自動切替）
    slide_paths = slide_gen.generate_all_slides(
        scenes, folder, theme="", use_photo=True,
    )
    if len(slide_paths) != len(scenes):
        print(f"  [エラー] スライド生成失敗: {len(slide_paths)}/{len(scenes)}")
        return False

    # スライドパスをシーンに設定
    for scene, sp in zip(scenes, slide_paths):
        scene["slide_path"] = str(sp)
        # 音声の実尺を設定
        audio_p = pathlib.Path(scene["audio_path"])
        scene["actual_duration_sec"] = video_gen._get_duration(audio_p)

    # Step 2: 動画再生成
    output_mp4 = folder / "output.mp4"
    result = video_gen.compose_shorts_video(
        scenes, output_mp4, use_photo=True,
    )
    if result is None:
        print(f"  [エラー] 動画生成失敗: {folder.name}")
        return False

    return True


def main():
    folders = _get_target_folders()
    print(f"対象フォルダ: {len(folders)}本")
    print()

    success = 0
    fail = 0
    failed_folders = []
    start = time.time()

    for i, folder in enumerate(folders):
        print(f"[{i+1}/{len(folders)}] {folder.name}")
        try:
            ok = _regen_one(folder)
            if ok:
                success += 1
            else:
                fail += 1
                failed_folders.append(folder.name)
        except Exception as e:
            print(f"  [例外] {e}")
            fail += 1
            failed_folders.append(folder.name)
        print()

    elapsed = time.time() - start
    print("=" * 50)
    print(f"完了: {success}/{len(folders)} 成功 / {fail} 失敗")
    print(f"所要時間: {elapsed/60:.1f}分")
    if failed_folders:
        print(f"失敗フォルダ: {failed_folders}")


if __name__ == "__main__":
    main()
