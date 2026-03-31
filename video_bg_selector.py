"""hook シーン用の動画背景を自動選択する.

slide_gen でスライド画像を生成した後、hook シーンに video_bg パスを設定する。
video_gen が video_bg を検出すると、静止画の代わりに動画背景で合成する。
"""
from __future__ import annotations

import json
import pathlib
import random

SCRIPT_DIR = pathlib.Path(__file__).parent
VIDEOS_DIR = SCRIPT_DIR / "assets" / "videos" / "shorts_hook"
METADATA_PATH = VIDEOS_DIR / "metadata.json"

# 使用履歴（直近N本で同じ動画を使わない）
_HISTORY_PATH = SCRIPT_DIR / "data" / "state" / "video_bg_history.json"
_HISTORY_KEEP = 20


def _load_metadata() -> list[dict]:
    """動画素材のメタデータを読み込む。"""
    if not METADATA_PATH.exists():
        return []
    data = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    return data.get("videos", [])


def _load_history() -> list[str]:
    """使用済み動画IDの履歴を読み込む。"""
    if not _HISTORY_PATH.exists():
        return []
    try:
        return json.loads(_HISTORY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_history(history: list[str]):
    """使用履歴を保存。"""
    _HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _HISTORY_PATH.write_text(
        json.dumps(history[-_HISTORY_KEEP:], ensure_ascii=False),
        encoding="utf-8",
    )


def select_hook_video(category: str = "anxiety") -> str | None:
    """hook 用の動画素材パスを返す。重複回避あり。

    Args:
        category: 写真カテゴリ（anxiety/comparison/data/recovery/steady）

    Returns:
        動画ファイルの絶対パス。素材がない場合は None。
    """
    videos = _load_metadata()
    if not videos:
        return None

    history = _load_history()
    history_set = set(history)

    # カテゴリでフィルタ + 履歴で除外
    candidates = [
        v for v in videos
        if v["category"] == category
        and str(v["pexels_id"]) not in history_set
        and v.get("status") != "rejected"
    ]

    # カテゴリ候補が尽きたら全カテゴリから選択
    if not candidates:
        candidates = [
            v for v in videos
            if str(v["pexels_id"]) not in history_set
            and v.get("status") != "rejected"
        ]

    # 全て使用済みなら履歴リセット
    if not candidates:
        history = []
        candidates = [v for v in videos if v.get("status") != "rejected"]

    if not candidates:
        return None

    chosen = random.choice(candidates)
    video_path = VIDEOS_DIR / chosen["category"] / chosen["filename"]

    if not video_path.exists():
        return None

    # 履歴に記録
    history.append(str(chosen["pexels_id"]))
    _save_history(history)

    return str(video_path)


def assign_hook_video_bg(scenes: list, category: str = "anxiety") -> list:
    """scenes リストの hook シーンに video_bg を設定する。

    Args:
        scenes: slide_gen / voice_gen で作成されたシーンリスト
        category: hook 用の動画カテゴリ

    Returns:
        video_bg が設定された scenes リスト（同じオブジェクトを変更）
    """
    video_path = select_hook_video(category)
    if not video_path:
        print("  [動画背景] 素材が見つかりません。写真背景を維持します。")
        return scenes

    for scene in scenes:
        if scene.get("role") == "hook":
            scene["video_bg"] = video_path
            print(f"  [動画背景] hook に動画素材を設定: {pathlib.Path(video_path).name}")
            break

    return scenes
