"""data slide_textが重複している動画の差し替え+再生成ワンショットスクリプト。"""
from __future__ import annotations

import json
import pathlib

DONE_DIR = pathlib.Path(__file__).parent / "done"

# 差し替え対象: (folder, 新text, 新slide_text)
REPLACEMENTS = [
    (
        "20260305_143429",
        "15年以上保有した人は、全員プラスになっている。",
        "15年持った人、全員プラス",
    ),
    (
        "20260312_171047",
        "3年でやめた人は、翌年のリターンを丸ごと逃す。",
        "3年でやめると翌年を逃す",
    ),
]


def main():
    import slide_gen
    import video_gen

    for folder, new_text, new_slide in REPLACEMENTS:
        t_path = DONE_DIR / folder / "transcript.json"
        data = json.loads(t_path.read_text(encoding="utf-8"))
        scenes = data.get("scenes", [])

        for j, s in enumerate(scenes):
            if s.get("role") != "data":
                continue

            old_slide = s.get("slide_text", "")
            print(f"{folder}: 「{old_slide}」→「{new_slide}」")
            s["text"] = new_text
            s["slide_text"] = new_slide

            # data スライドだけ再生成
            idx = j + 1
            output_path = DONE_DIR / folder / f"slide_{idx:02d}.png"
            text = new_slide.rstrip("。")
            path, photo_asset = slide_gen._generate_slide_v2(text, "data", output_path)
            if photo_asset:
                s["photo_asset"] = photo_asset
            s["slide_path"] = str(path)
            print(f"  data スライド再生成: {path.name}")
            break

        # transcript.json 保存
        t_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        # 動画再生成
        video_path = video_gen.compose_shorts_video(
            scenes, DONE_DIR / folder / "output.mp4", use_photo=True,
        )
        if video_path:
            print(f"  動画再生成完了")
        else:
            print(f"  [失敗] 動画再生成エラー")

    print(f"\n完了: {len(REPLACEMENTS)}本")


if __name__ == "__main__":
    main()
