"""長尺動画2本をYouTubeに即時公開でアップロードする（デザイン改善版の再アップ用）。"""
from __future__ import annotations

import json
import pathlib

from dotenv import load_dotenv
load_dotenv()

import youtube_upload

LONG_DIR = pathlib.Path(__file__).parent / "long_video"

VIDEOS = [
    {
        "dir": LONG_DIR / "01_fukumison",
        "comment": (
            "含み損の夜は、数字より\n"
            "自分の判断が間違っていたかもしれないという感覚がつらくなりやすいです。\n"
            "この動画では、その夜に今日は何をしないかを静かに整理しています。"
        ),
    },
    {
        "dir": LONG_DIR / "02_tsumitate3",
        "comment": (
            "積立3年目は、いちばんしんどい時期です。\n"
            "新鮮さが消え、結果が出るには早すぎる。\n"
            "この動画では、なぜ3年目に気持ちが折れやすいのかを静かに整理しています。"
        ),
    },
]


def main():
    for v in VIDEOS:
        meta_path = v["dir"] / "video_meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))

        title = meta["title"]
        video_path = meta["video_path"]
        thumbnail_path = meta["thumbnail_path"]

        print(f"\n=== {title} ===")
        print(f"動画: {video_path}")
        print(f"サムネ: {thumbnail_path}")

        # 即時公開（publish_at=None）
        video_id = youtube_upload.upload_video(
            video_path=video_path,
            title=title,
            description=meta["description"],
            tags=meta["tags"],
            thumbnail_path=thumbnail_path,
            publish_at=None,
        )

        print(f"動画ID: {video_id}")
        print(f"URL: https://youtube.com/watch?v={video_id}")

        # 固定コメント
        print("固定コメントを投稿中...")
        _post_comment(video_id, v["comment"])

    print("\n=== 2本とも完了 ===")


def _post_comment(video_id: str, text: str):
    import sheets
    youtube = sheets.get_youtube_service()
    body = {
        "snippet": {
            "videoId": video_id,
            "topLevelComment": {
                "snippet": {"textOriginal": text}
            }
        }
    }
    result = youtube.commentThreads().insert(part="snippet", body=body).execute()
    print(f"  コメント投稿完了: {result['id']}")
    print("  ※固定設定は YouTube Studio から手動で行ってください")


if __name__ == "__main__":
    main()
