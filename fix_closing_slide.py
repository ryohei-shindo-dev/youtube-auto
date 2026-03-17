"""キュー内の closing slide_text を修正し、スライド+動画を再生成するワンショットスクリプト。

修正対象: slide_text に「フォロー」「ガチホ仲間」「明日もガチホ」を含む動画
修正内容: closing slide_text を「続けてますか」等に統一
再生成: closing スライド画像 + 動画（APIコストゼロ、ローカル処理のみ）

使い方:
    source venv/bin/activate
    python fix_closing_slide.py
"""
from __future__ import annotations

import json
import pathlib

SCRIPT_DIR = pathlib.Path(__file__).parent
DONE_DIR = SCRIPT_DIR / "done"
QUEUE_PATH = SCRIPT_DIR / "publish_queue.json"


def _closing_slide_from_text(text: str) -> str:
    """script_gen.py と同じロジック。"""
    if "コメント" in text:
        return "同じ人いる？"
    if "フォロー" in text or "持つ" in text or "続けよう" in text:
        return "続けてますか"
    return "続けてますか"


def _needs_fix(slide_text: str) -> bool:
    return any(w in slide_text for w in ["フォロー", "ガチホ仲間", "明日もガチホ"])


def fix_and_regenerate():
    import slide_gen
    import video_gen

    queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    print(f"キュー: {len(queue)}本")

    # Step 1: transcript.json の slide_text を修正（データはメモリに保持）
    targets: list[tuple[str, pathlib.Path, dict]] = []
    for folder in queue:
        t_path = DONE_DIR / folder / "transcript.json"
        if not t_path.exists():
            continue

        data = json.loads(t_path.read_text(encoding="utf-8"))
        scenes = data.get("scenes", [])
        modified = False

        for s in scenes:
            if s.get("role") != "closing":
                continue
            old_slide = s.get("slide_text", "")
            if not _needs_fix(old_slide):
                break

            narration = s.get("text", "")
            new_slide = _closing_slide_from_text(narration)
            print(f"  {folder}: 「{old_slide}」→「{new_slide}」")
            s["slide_text"] = new_slide
            modified = True
            break

        if modified:
            t_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            targets.append((folder, t_path, data))

    print(f"\ntranscript.json 修正完了: {len(targets)}本")

    if not targets:
        print("修正対象なし。終了します。")
        return

    # Step 2: closing スライド + 動画を再生成
    print(f"\nスライド + 動画を再生成中（{len(targets)}本）...")
    success = 0
    fail = 0

    for i, (folder, t_path, data) in enumerate(targets):
        folder_path = DONE_DIR / folder
        print(f"\n[{i+1}/{len(targets)}] {folder}")

        scenes = data.get("scenes", [])
        theme = data.get("theme", "")

        try:
            # closing スライドだけ再生成（他シーンはスキップ）
            for j, scene in enumerate(scenes):
                if scene.get("role") != "closing":
                    continue
                idx = j + 1
                output_path = folder_path / f"slide_{idx:02d}.png"
                text = scene.get("slide_text", "").rstrip("。")
                path, photo_asset = slide_gen._generate_slide_v2(
                    text, "closing", output_path,
                )
                if photo_asset:
                    scene["photo_asset"] = photo_asset
                scene["slide_path"] = str(path)
                print(f"  closing スライド再生成: {path.name}")
                break

            # 動画再生成
            video_path = video_gen.compose_shorts_video(
                scenes, folder_path / "output.mp4", use_photo=True,
            )
            if not video_path:
                print(f"  [失敗] 動画合成エラー")
                fail += 1
                continue

            # transcript.json にスライドパスを更新保存
            t_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            success += 1
            print(f"  完了")
        except Exception as e:
            print(f"  [エラー] {e}")
            fail += 1

    print(f"\n===== 結果 =====")
    print(f"成功: {success}本, 失敗: {fail}本")


if __name__ == "__main__":
    fix_and_regenerate()
