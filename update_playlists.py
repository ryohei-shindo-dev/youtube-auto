"""再生リストの名前変更 + サムネイル設定スクリプト。

Usage:
    python update_playlists.py
"""
from __future__ import annotations

import pathlib

from googleapiclient.http import MediaFileUpload

import sheets

THUMBNAIL_DIR = pathlib.Path("assets/playlist_thumbnails")

# 再生リストID → 新しい名前・サムネファイル
UPDATES = [
    {
        "playlist_id": "PLxsqPMwO1hN_u_VFXPsaqqiiKKmnEh2eF",
        "new_title": "売りたくなった日に見る Shorts",
        "thumbnail": THUMBNAIL_DIR / "playlist_sell.png",
    },
    {
        "playlist_id": "PLxsqPMwO1hN8EBVliTFOka7RxIGxQTsMh",
        "new_title": "増えていない気がするときの Shorts",
        "thumbnail": THUMBNAIL_DIR / "playlist_slow.png",
    },
    {
        "playlist_id": "PLxsqPMwO1hN-HxyHL5mrQkvtLOXQLRijM",
        "new_title": "人と比べてしまうときの Shorts",
        "thumbnail": THUMBNAIL_DIR / "playlist_compare.png",
    },
    {
        "playlist_id": "PLxsqPMwO1hN8rzg7n47kNFRWxmvN0RurL",
        "new_title": "何も起きない日に見る Shorts",
        "thumbnail": THUMBNAIL_DIR / "playlist_quiet.png",
    },
]


def main():
    youtube = sheets.get_youtube_service()

    for item in UPDATES:
        pid = item["playlist_id"]
        new_title = item["new_title"]
        thumb_path = item["thumbnail"]

        # 1. 再生リスト名を変更
        print(f"\n[{pid[:20]}...] 名前変更: {new_title}")
        try:
            # 現在のプレイリスト情報を取得
            pl = youtube.playlists().list(
                part="snippet,status", id=pid,
            ).execute()
            if not pl.get("items"):
                print(f"  [エラー] 再生リストが見つかりません")
                continue

            snippet = pl["items"][0]["snippet"]
            status = pl["items"][0]["status"]
            snippet["title"] = new_title

            youtube.playlists().update(
                part="snippet,status",
                body={
                    "id": pid,
                    "snippet": snippet,
                    "status": status,
                },
            ).execute()
            print(f"  名前変更完了")
        except Exception as e:
            print(f"  [エラー] 名前変更失敗: {e}")

        # 2. サムネイル設定
        if thumb_path.exists():
            print(f"  サムネイル設定: {thumb_path.name}")
            try:
                media = MediaFileUpload(str(thumb_path), mimetype="image/png")
                youtube.thumbnails().set(
                    videoId=pid,  # playlistId もこのパラメータで指定
                    media_body=media,
                ).execute()
                print(f"  サムネイル設定完了")
            except Exception as e:
                print(f"  [警告] サムネイル設定失敗: {e}")
                print(f"  → YouTube Studioで手動設定してください: {thumb_path}")
        else:
            print(f"  [スキップ] サムネイルファイルなし: {thumb_path}")

    print("\n完了")


if __name__ == "__main__":
    main()
