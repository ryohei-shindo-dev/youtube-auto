"""キュー内の表記揺れ（積立→積み立て等）を一括修正するワンショットスクリプト。

transcript.jsonの全フィールドを正規化し、slide_textが変わった動画のみスライド+動画を再生成。
"""
from __future__ import annotations

import json
import pathlib

from style_rules import normalize_text

DONE_DIR = pathlib.Path(__file__).parent / "done"
QUEUE_PATH = pathlib.Path(__file__).parent / "publish_queue.json"

# 正規化対象のフィールド
_TOP_FIELDS = ("title", "description", "topic")
_SCENE_FIELDS = ("text", "slide_text")


def _normalize_script(data: dict) -> tuple[bool, list[str]]:
    """transcript.json全体を正規化。変更があればTrue+変更箇所リストを返す。"""
    changes: list[str] = []

    for key in _TOP_FIELDS:
        val = data.get(key, "")
        if isinstance(val, str):
            new_val = normalize_text(val)
            if new_val != val:
                data[key] = new_val
                changes.append(key)

    for scene in data.get("scenes", []):
        role = scene.get("role", "")
        for key in _SCENE_FIELDS:
            val = scene.get(key, "")
            if isinstance(val, str):
                new_val = normalize_text(val)
                if new_val != val:
                    scene[key] = new_val
                    changes.append(f"{role}.{key}")

    return bool(changes), changes


def _slide_text_changed(changes: list[str]) -> bool:
    """slide_textが変わったかどうか。"""
    return any("slide_text" in c for c in changes)


def main():
    import slide_gen
    import video_gen

    queue = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
    print(f"キュー: {len(queue)}本\n")

    text_only = 0  # slide_text以外だけ変わった
    regen = 0      # スライド再生成が必要
    skip = 0       # 変更なし
    fail = 0

    for i, folder in enumerate(queue):
        t_path = DONE_DIR / folder / "transcript.json"
        if not t_path.exists():
            continue

        data = json.loads(t_path.read_text(encoding="utf-8"))
        modified, changes = _normalize_script(data)

        if not modified:
            skip += 1
            continue

        # transcript.json保存
        t_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        if not _slide_text_changed(changes):
            text_only += 1
            print(f"  [{i+1}] {folder}: テキスト修正のみ（{', '.join(changes)}）")
            continue

        # slide_textが変わった → 該当スライド+動画を再生成
        print(f"  [{i+1}] {folder}: スライド再生成（{', '.join(changes)}）")
        scenes = data.get("scenes", [])

        try:
            for j, scene in enumerate(scenes):
                if f"{scene.get('role')}.slide_text" not in changes:
                    continue
                idx = j + 1
                output_path = DONE_DIR / folder / f"slide_{idx:02d}.png"
                text = scene.get("slide_text", "").rstrip("。")
                role = scene.get("role", "hook")
                path, photo_asset = slide_gen._generate_slide_v2(text, role, output_path)
                if photo_asset:
                    scene["photo_asset"] = photo_asset
                scene["slide_path"] = str(path)

            # 動画再生成
            video_path = video_gen.compose_shorts_video(
                scenes, DONE_DIR / folder / "output.mp4", use_photo=True,
            )
            if video_path:
                # 更新されたスライドパスを保存
                t_path.write_text(
                    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                regen += 1
            else:
                print(f"    [失敗] 動画再生成エラー")
                fail += 1
        except Exception as e:
            print(f"    [エラー] {e}")
            fail += 1

    print(f"\n===== 結果 =====")
    print(f"変更なし: {skip}本")
    print(f"テキスト修正のみ: {text_only}本")
    print(f"スライド再生成: {regen}本")
    print(f"失敗: {fail}本")


if __name__ == "__main__":
    main()
