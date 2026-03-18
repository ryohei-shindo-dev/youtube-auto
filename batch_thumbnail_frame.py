"""キュー内の全動画に thumbnail_frame.png を一括生成するスクリプト。

Usage:
    python batch_thumbnail_frame.py [--dry-run]
"""
from __future__ import annotations

import json
import pathlib
import sys

import slide_gen


def main():
    dry_run = "--dry-run" in sys.argv

    queue_path = pathlib.Path("publish_queue.json")
    queue = json.loads(queue_path.read_text())

    missing = []
    for folder in queue:
        frame_path = pathlib.Path("done") / folder / "thumbnail_frame.png"
        if not frame_path.exists():
            missing.append(folder)

    print(f"キュー総数: {len(queue)}, thumbnail_frame.png なし: {len(missing)}")

    if dry_run:
        for f in missing:
            print(f"  [dry-run] {f}")
        return

    success = 0
    fail = 0
    used_texts: list[str] = []

    for folder in missing:
        transcript_path = pathlib.Path("done") / folder / "transcript.json"
        if not transcript_path.exists():
            print(f"  [スキップ] {folder}: transcript.json なし")
            fail += 1
            continue

        data = json.loads(transcript_path.read_text())
        scenes = data.get("scenes", [])
        title = data.get("title", "")

        if not scenes:
            print(f"  [スキップ] {folder}: scenes が空")
            fail += 1
            continue

        output_path = pathlib.Path("done") / folder / "thumbnail_frame.png"
        result = slide_gen.generate_thumbnail_frame(
            scenes, output_path, title=title, used_texts=used_texts,
        )

        if result:
            used_texts.append(result["text"])
            success += 1
        else:
            fail += 1

    print(f"\n完了: 成功 {success}, 失敗 {fail}")


if __name__ == "__main__":
    main()
