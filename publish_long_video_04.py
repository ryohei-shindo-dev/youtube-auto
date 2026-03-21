"""
publish_long_video_04.py
4本目「高配当株とインデックスで揺れる人へ」をYouTubeに即時公開する。
"""
from __future__ import annotations

import json
import pathlib

META_PATH = pathlib.Path(__file__).parent / "long_video" / "04_haitou_index" / "video_meta.json"

PINNED_COMMENT = (
    "高配当株とインデックスで揺れるとき、\n"
    "比べているのは商品だけではなく、安心の形かもしれません。\n"
    "この動画では、その違いを静かに整理しています。"
)


def main():
    meta = json.loads(META_PATH.read_text(encoding="utf-8"))

    video_path = meta["video_path"]
    title = meta["title"]
    description = meta["description"]
    tags = meta["tags"]
    thumbnail_path = meta["thumbnail_path"]

    print("=== 長尺動画 4本目 即時公開 ===")
    print(f"タイトル: {title}")
    print(f"動画: {video_path}")
    print(f"サムネ: {thumbnail_path}")
    print()

    # 1. YouTube にアップロード（即時公開）
    import youtube_upload
    video_id = youtube_upload.upload_video(
        video_path=video_path,
        title=title,
        description=description,
        tags=tags,
        thumbnail_path=thumbnail_path,
        privacy="public",
    )

    print(f"\n動画ID: {video_id}")
    print(f"URL: https://youtube.com/watch?v={video_id}")

    # 2. 固定コメントを投稿
    print("\n固定コメントを投稿中...")
    _post_pinned_comment(video_id, PINNED_COMMENT)

    print("\n=== 完了 ===")
    print("YouTube Studio から固定コメントの設定を行ってください。")


def _post_pinned_comment(video_id: str, text: str):
    """動画に固定コメントを投稿する。"""
    import sheets
    youtube = sheets.get_youtube_service()

    comment_body = {
        "snippet": {
            "videoId": video_id,
            "topLevelComment": {
                "snippet": {
                    "textOriginal": text,
                }
            }
        }
    }
    result = youtube.commentThreads().insert(
        part="snippet",
        body=comment_body,
    ).execute()

    comment_id = result["id"]
    print(f"  コメント投稿完了: {comment_id}")
    print("  ※固定設定は YouTube Studio から手動で行ってください")


if __name__ == "__main__":
    main()
