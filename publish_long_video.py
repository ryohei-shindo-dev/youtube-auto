"""
publish_long_video.py
長尺動画をYouTubeに予約投稿するスクリプト。

使い方:
  venv/bin/python publish_long_video.py

3/10（火）21:00 JST に予約公開される。
アップロード自体は実行時に行われ、指定日時まで非公開で待機する。
"""
from __future__ import annotations

import json
import pathlib

META_PATH = pathlib.Path(__file__).parent / "long_video" / "01_fukumison" / "video_meta.json"

# 予約公開日時（ISO 8601 / UTC）
# 2026-03-10 21:00 JST = 2026-03-10 12:00 UTC
PUBLISH_AT = "2026-03-10T12:00:00Z"

# 固定コメント
PINNED_COMMENT = (
    "含み損の夜は、数字より\n"
    "自分の判断が間違っていたかもしれないという感覚がつらくなりやすいです。\n"
    "この動画では、その夜に今日は何をしないかを静かに整理しています。"
)


def main():
    meta = json.loads(META_PATH.read_text(encoding="utf-8"))

    video_path = meta["video_path"]
    title = meta["title"]
    description = meta["description"]
    tags = meta["tags"]
    thumbnail_path = meta["thumbnail_path"]

    print("=== 長尺動画 予約投稿 ===")
    print(f"タイトル: {title}")
    print(f"予約公開: {PUBLISH_AT} (2026/03/10 21:00 JST)")
    print(f"動画: {video_path}")
    print(f"サムネ: {thumbnail_path}")
    print()

    # 1. YouTube にアップロード（予約公開）
    import youtube_upload
    video_id = youtube_upload.upload_video(
        video_path=video_path,
        title=title,
        description=description,
        tags=tags,
        thumbnail_path=thumbnail_path,
        publish_at=PUBLISH_AT,
    )

    print(f"\n動画ID: {video_id}")
    print(f"URL: https://youtube.com/watch?v={video_id}")
    print(f"予約公開: 2026/03/10 21:00 JST")

    # 2. 固定コメントを投稿
    print("\n固定コメントを投稿中...")
    _post_pinned_comment(video_id, PINNED_COMMENT)

    print("\n=== 完了 ===")
    print("3/10 21:00 JST に自動公開されます。")
    print()
    print("当日の運用:")
    print("  7:00  Shorts 通常投稿（自動）")
    print("  19:00 Shorts 含み損テーマ連動")
    print("  21:00 長尺自動公開")
    print("  21:00〜 X告知・コミュニティ投稿")


def _post_pinned_comment(video_id: str, text: str):
    """動画に固定コメントを投稿する。"""
    import sheets
    youtube = sheets.get_youtube_service()

    # コメント投稿
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

    # 固定コメントに設定（moderateを使う: バナーコメント）
    # Note: YouTube API では直接「固定」する専用エンドポイントはない
    # YouTube Studio から手動で固定するか、コメントを投稿しておけば最上位に表示される
    print("  ※固定設定は YouTube Studio から手動で行ってください")


if __name__ == "__main__":
    main()
