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

from __future__ import annotations

import json
import os
import pathlib
import time

from googleapiclient.http import MediaFileUpload

_DIR = pathlib.Path(__file__).parent
_PLAYLISTS_PATH = _DIR / "playlists.json"


def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: list = None,
    privacy: str = "public",
    category_id: str = "22",
    thumbnail_path: str = None,
    publish_at: str = None,
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
        publish_at: 予約公開日時（ISO 8601形式、例: "2026-03-10T12:00:00Z"）
                    指定すると privacy は自動で private になり、指定日時に公開される

    Returns:
        アップロードされた動画のID（例: "IaCOIxgE80U"）
    """
    import sheets
    youtube = sheets.get_youtube_service()

    status = {
        "privacyStatus": privacy,
        "selfDeclaredMadeForKids": False,
    }
    if publish_at:
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": category_id,
        },
        "status": status,
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=10 * 1024 * 1024,  # 10MB chunks
    )

    print(f"  アップロード開始: {os.path.basename(video_path)}")
    print(f"  タイトル: {title}")
    if publish_at:
        print(f"  予約公開: {publish_at}")
    else:
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


def add_to_playlists(
    video_id: str,
    topic: str = "",
    tags: list | None = None,
    title: str = "",
):
    """playlists.json のマッピングに基づいて動画を再生リストに追加する。

    1. topic で完全一致
    2. tags で完全一致
    3. title でキーワード部分一致
    4. 最後に必ず「全動画」リストに追加
    """
    if not _PLAYLISTS_PATH.exists():
        print("  [警告] playlists.json が見つかりません。再生リスト追加をスキップ。")
        return

    with open(_PLAYLISTS_PATH, encoding="utf-8") as f:
        config = json.load(f)

    all_id = config.get("all_playlist_id", "")
    mapping = config.get("topic_mapping", {})
    title_kw = config.get("title_keywords", {})

    # topic でマッチするリストを収集
    playlist_ids = set()
    if topic and topic in mapping:
        playlist_ids.update(mapping[topic])

    # tags でもマッチを試みる
    for tag in (tags or []):
        if tag in mapping:
            playlist_ids.update(mapping[tag])

    # title のキーワード部分一致（topic/tags でテーマ別にマッチしなかった場合の補助）
    if title:
        for keyword, pids in title_kw.items():
            if keyword in title:
                playlist_ids.update(pids)

    # 全動画リストを追加
    if all_id:
        playlist_ids.add(all_id)

    if not playlist_ids:
        return

    import sheets
    youtube = sheets.get_youtube_service()
    names = config.get("playlists", {})

    for pid in playlist_ids:
        try:
            youtube.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": pid,
                        "resourceId": {
                            "kind": "youtube#video",
                            "videoId": video_id,
                        },
                    }
                },
            ).execute()
            name = names.get(pid, pid)
            print(f"  再生リスト追加: {name}")
        except Exception as e:
            print(f"  [警告] 再生リスト追加失敗 ({pid}): {e}")


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
