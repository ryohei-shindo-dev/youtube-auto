"""
youtube_upload.py
YouTube Data API v3 で動画をアップロードするモジュール。

使い方:
    import youtube_upload
    video_id = youtube_upload.upload_video(
        video_path="done/20260305_105657/output.mp4",
        title="長期投資で一番つらい時期",
        description="説明文...",
        tags=["長期投資", "ガチホ"],
    )
"""

import os
import time

from googleapiclient.http import MediaFileUpload


def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: list = None,
    privacy: str = "public",
    category_id: str = "22",
    thumbnail_path: str = None,
) -> str:
    """
    YouTube に動画をアップロードする。

    Args:
        video_path: 動画ファイルのパス（.mp4）
        title: 動画タイトル
        description: 動画の説明文
        tags: タグのリスト
        privacy: 公開設定（public / unlisted / private）
        category_id: カテゴリID（22 = People & Blogs）
        thumbnail_path: サムネイル画像のパス（省略可）

    Returns:
        アップロードされた動画のID（例: "IaCOIxgE80U"）
    """
    import sheets
    youtube = sheets.get_youtube_service()

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=10 * 1024 * 1024,  # 10MB chunks
    )

    print(f"  アップロード開始: {os.path.basename(video_path)}")
    print(f"  タイトル: {title}")
    print(f"  公開設定: {privacy}")

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    # Resumable upload（進捗表示付き）
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"  アップロード中... {pct}%")

    video_id = response["id"]
    print(f"  アップロード完了: https://youtube.com/shorts/{video_id}")

    # サムネイル設定
    if thumbnail_path and os.path.exists(thumbnail_path):
        _set_thumbnail(youtube, video_id, thumbnail_path)

    return video_id


def _set_thumbnail(youtube, video_id: str, thumbnail_path: str):
    """動画にカスタムサムネイルを設定する。"""
    try:
        media = MediaFileUpload(thumbnail_path, mimetype="image/png")
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=media,
        ).execute()
        print(f"  サムネイル設定完了: {os.path.basename(thumbnail_path)}")
    except Exception as e:
        print(f"  [警告] サムネイル設定に失敗（チャンネル認証が必要な場合があります）: {e}")
