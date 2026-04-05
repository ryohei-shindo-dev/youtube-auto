"""キュー内の slide_text 途中切れを修復するスクリプト。

修復対象: slide_text が不自然に切れているが text は正常なシーン。
処理: slide_text を再導出 → スライド再生成 → 動画再生成。

Usage:
    python repair_slide_text.py [--dry-run]
"""
from __future__ import annotations

import json
import pathlib
import sys

import script_gen
import slide_gen
import video_gen

DONE_DIR = pathlib.Path("done")

# 修復対象: (folder, role) のリスト
# text自体が壊れている3件は除外（要台本再生成）:
#   20260313_221713/empathy, 20260402_113526/empathy, 20260402_113335/hook
TARGETS = [
    ("20260402_113135", "hook"),      # 20年待ってたら上が → 上がってた
    ("20260402_114512", "hook"),      # 暴落中に買う人、気が → 気が狂ってるのか
    ("20260402_112956", "data"),      # …逃すと差が → 差が広がる
    ("20260313_221041", "data"),      # NISA…20年で → 約200万
    ("20260312_192201", "empathy"),   # まだゼロで → ゼロですか
    ("20260402_120836", "hook"),      # FIRE報告を見て、→ 止めた
    ("20260402_120836", "empathy"),   # 自分の選択が → 正しいか分からなくなった
]

# 自動導出では収まらないケース用の手動オーバーライド
MANUAL_OVERRIDES: dict[tuple[str, str], str] = {
    ("20260402_112956", "data"): "上昇局面を逃すと差が広がる",
    ("20260313_221041", "data"): "NISA非課税、20年で約200万",
}


def _derive_slide_text(role: str, text: str) -> str:
    """ロール別に slide_text を再導出する。"""
    raw = text.rstrip("。？！ ")
    if role == "hook":
        return script_gen._safe_truncate_slide_text(raw, max_len=15)
    elif role == "empathy":
        return script_gen._safe_truncate_slide_text(raw, max_len=12)
    elif role == "data":
        return script_gen._data_slide_from_text(text)
    elif role == "resolve":
        return script_gen._resolve_slide_from_conclusion(text)
    elif role == "closing":
        return script_gen._closing_slide_from_text(text)
    return raw


def repair(dry_run: bool = False) -> None:
    # folder ごとにまとめる
    folder_fixes: dict[str, list[tuple[str, str]]] = {}
    for folder, role in TARGETS:
        folder_fixes.setdefault(folder, []).append((folder, role))

    fixed_count = 0
    for folder, items in folder_fixes.items():
        tp = DONE_DIR / folder / "transcript.json"
        if not tp.exists():
            print(f"[SKIP] {folder}: transcript.json なし")
            continue

        data = json.loads(tp.read_text())
        changed = False

        for _, role in items:
            for s in data["scenes"]:
                if s.get("role") != role:
                    continue
                text = s.get("text", "")
                old_st = s.get("slide_text", "")
                override_key = (folder, role)
                if override_key in MANUAL_OVERRIDES:
                    new_st = MANUAL_OVERRIDES[override_key]
                else:
                    new_st = _derive_slide_text(role, text)
                    new_st = script_gen._clean_slide_text(new_st)

                if old_st == new_st:
                    print(f"[OK]   {folder}/{role}: 変更なし「{old_st}」")
                    continue

                print(f"[FIX]  {folder}/{role}:")
                print(f"       text      = {text}")
                print(f"       old       = {old_st}")
                print(f"       new       = {new_st}")

                if not dry_run:
                    s["slide_text"] = new_st
                    changed = True
                    fixed_count += 1
                break

        if changed and not dry_run:
            # 1. transcript.json 保存
            tp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
            print(f"  → transcript.json 保存済み")

            # 2. スライド再生成
            out_dir = DONE_DIR / folder
            slide_gen.generate_all_slides(
                data["scenes"], out_dir, use_photo=True,
            )
            print(f"  → スライド再生成完了")

            # 3. 動画再生成
            for i, s in enumerate(data["scenes"], 1):
                audio_path = out_dir / f"audio_{i:02d}.mp3"
                if audio_path.exists():
                    s["audio_path"] = str(audio_path)
            output_mp4 = out_dir / "output.mp4"
            video_gen.compose_shorts_video(
                data["scenes"], output_mp4, use_photo=True,
            )
            print(f"  → 動画再生成完了")

    print(f"\n修復完了: {fixed_count}件")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("=== DRY RUN（変更なし） ===\n")
    repair(dry_run=dry_run)
