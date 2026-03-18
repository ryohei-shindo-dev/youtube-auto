"""公開済みShorts動画のサムネイルを一括生成するワンショットスクリプト。

done/ 内の全動画に thumbnail.png を生成する。
生成後、YouTubeモバイルアプリから手動でサムネイルを設定する。

使い方:
    source venv/bin/activate
    python fix_shorts_thumbnails.py
"""
from __future__ import annotations

import json
import pathlib

DONE_DIR = pathlib.Path(__file__).parent / "done"
QUEUE_PATH = pathlib.Path(__file__).parent / "publish_queue.json"


def main():
    import slide_gen

    # キュー内のフォルダを除外（まだ公開されていない）
    queue = set()
    if QUEUE_PATH.exists():
        queue = set(json.loads(QUEUE_PATH.read_text(encoding="utf-8")))

    folders = sorted(
        f for f in DONE_DIR.iterdir()
        if f.is_dir() and (f / "transcript.json").exists() and f.name not in queue
    )
    print(f"公開済み動画: {len(folders)}本（キュー内{len(queue)}本は除外）\n")

    success = 0
    fail = 0
    skip = 0

    for i, folder in enumerate(folders):
        t_path = folder / "transcript.json"
        try:
            data = json.loads(t_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            skip += 1
            continue

        scenes = data.get("scenes", [])
        if not scenes:
            skip += 1
            continue

        title = data.get("title", "")[:35]
        output_path = folder / "thumbnail.png"

        result = slide_gen.generate_shorts_thumbnail(scenes, output_path)
        if result:
            success += 1
        else:
            print(f"  [{i+1}] {folder.name} | {title} → 生成失敗")
            fail += 1

    print(f"\n===== 結果 =====")
    print(f"成功: {success}本")
    print(f"失敗: {fail}本")
    print(f"スキップ: {skip}本")


if __name__ == "__main__":
    main()
