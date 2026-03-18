"""
sync_youtube.py — YouTube APIとシートの同期・監査

公開済み動画のvideo ID・公開日・タイトルをYouTube APIから取得し、
シートと突合・補完する。

使い方:
    # 初回同期（既存の全動画のvideo IDをW列に記録）
    python sync_youtube.py

    # 定期監査（毎日22:00にanalytics_collect.pyと一緒に実行推奨）
    python sync_youtube.py --audit
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re

from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).parent / ".env")

SCRIPT_DIR = pathlib.Path(__file__).parent


def _get_youtube_videos() -> list[dict]:
    """YouTube APIからチャンネルの全動画を取得する。"""
    import sheets

    yt = sheets.get_youtube_service()
    channel_resp = yt.channels().list(part="contentDetails", mine=True).execute()
    uploads_id = channel_resp["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    videos = []
    next_token = None
    while True:
        pl_resp = yt.playlistItems().list(
            part="snippet", playlistId=uploads_id, maxResults=50,
            pageToken=next_token,
        ).execute()
        for item in pl_resp.get("items", []):
            snip = item["snippet"]
            videos.append({
                "video_id": snip["resourceId"]["videoId"],
                "title": snip["title"],
                "published_at": snip["publishedAt"][:10],
            })
        next_token = pl_resp.get("nextPageToken")
        if not next_token:
            break

    return videos


def _get_sheet_data() -> tuple[list[list], str]:
    """シートの全行を取得する。"""
    import sheets

    sheet_id = os.getenv("YOUTUBE_SHEET_ID", "")
    svc = sheets.get_service()
    result = svc.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"{sheets.SHEET_NAME}!A:W",
    ).execute()
    return result.get("values", []), sheet_id


def sync():
    """YouTube APIの全動画とシートを突合し、video ID・公開日を補完する。"""
    import sheets

    yt_videos = _get_youtube_videos()
    rows, sheet_id = _get_sheet_data()
    svc = sheets.get_service()

    print(f"YouTube上の動画: {len(yt_videos)}本")
    print(f"シート行数: {len(rows)}行\n")

    # シートのK列（YouTube URL）からvideo IDを抽出してマッピング
    updates = []
    synced = 0

    for i, row in enumerate(rows):
        if i == 0:
            continue
        row_num = i + 1
        yt_url = row[10] if len(row) >= 11 else ""  # K列
        existing_vid_id = row[22] if len(row) >= 23 else ""  # W列
        pub_date = row[9] if len(row) >= 10 else ""  # J列

        if not yt_url:
            continue

        # URL から video ID を抽出
        vid_id = sheets._extract_video_id(yt_url)
        if not vid_id:
            # URL全体がvideo IDかもしれない
            for yt_vid in yt_videos:
                if yt_vid["video_id"] in yt_url:
                    vid_id = yt_vid["video_id"]
                    break

        if not vid_id:
            continue

        # YouTube APIのデータと照合
        yt_data = next((v for v in yt_videos if v["video_id"] == vid_id), None)

        changed = False

        # W列: video ID が空なら記録
        if not existing_vid_id and vid_id:
            updates.append({"range": f"{sheets.SHEET_NAME}!W{row_num}", "values": [[vid_id]]})
            changed = True

        # J列: 公開日が空ならAPIから補完
        if not pub_date and yt_data:
            api_date = yt_data["published_at"].replace("-", "/")
            updates.append({"range": f"{sheets.SHEET_NAME}!J{row_num}", "values": [[api_date]]})
            changed = True

        # K列: YouTube URLを正規形式に統一
        expected_url = f"https://youtube.com/shorts/{vid_id}"
        if yt_url != expected_url:
            updates.append({"range": f"{sheets.SHEET_NAME}!K{row_num}", "values": [[expected_url]]})
            changed = True

        if changed:
            folder = row[1] if len(row) >= 2 else ""
            print(f"  行{row_num}: {folder} → video_id={vid_id}")
            synced += 1

    if updates:
        svc.spreadsheets().values().batchUpdate(
            spreadsheetId=sheet_id,
            body={"valueInputOption": "RAW", "data": updates},
        ).execute()

    print(f"\n同期完了: {synced}行を更新")


def audit():
    """シートとYouTube APIの整合性を監査する。"""
    import sheets

    yt_videos = _get_youtube_videos()
    rows, sheet_id = _get_sheet_data()

    yt_ids = {v["video_id"] for v in yt_videos}
    issues = []

    for i, row in enumerate(rows):
        if i == 0:
            continue
        row_num = i + 1
        folder = row[1] if len(row) >= 2 else ""
        status = row[6] if len(row) >= 7 else ""
        pub_date = row[9] if len(row) >= 10 else ""
        yt_url = row[10] if len(row) >= 11 else ""
        vid_id = row[22] if len(row) >= 23 else ""

        # 公開済みなのにvideo_id空
        if status == sheets.STATUS_PUBLISHED and not vid_id:
            issues.append(f"  ❌ 行{row_num} {folder}: 公開済みだがvideo_idが空")

        # video_idあるのにpublished_at空
        if vid_id and not pub_date:
            issues.append(f"  ❌ 行{row_num} {folder}: video_idあるが公開日が空")

        # video_idがYouTube上に存在しない
        if vid_id and vid_id not in yt_ids:
            issues.append(f"  ⚠ 行{row_num} {folder}: video_id={vid_id}がYouTube上にない")

        # YouTube URLが正規形式でない
        if vid_id and yt_url and yt_url != f"https://youtube.com/shorts/{vid_id}":
            issues.append(f"  ⚠ 行{row_num} {folder}: URL非正規 {yt_url}")

    # YouTube上に存在するがシートに未記録
    sheet_vid_ids = set()
    for row in rows[1:]:
        vid = row[22] if len(row) >= 23 else ""
        if vid:
            sheet_vid_ids.add(vid)
    untracked = yt_ids - sheet_vid_ids
    for vid_id in untracked:
        yt_data = next(v for v in yt_videos if v["video_id"] == vid_id)
        issues.append(f"  ⚠ YouTube上にあるがシート未記録: {vid_id} ({yt_data['title'][:30]})")

    if issues:
        print(f"監査結果: {len(issues)}件の問題\n")
        for issue in issues:
            print(issue)
    else:
        print("監査結果: 問題なし ✅")

    print(f"\nYouTube: {len(yt_videos)}本, シート(video_id付き): {len(sheet_vid_ids)}本")


def main():
    parser = argparse.ArgumentParser(description="YouTube API同期・監査")
    parser.add_argument("--audit", action="store_true", help="監査のみ（同期しない）")
    args = parser.parse_args()

    if args.audit:
        audit()
    else:
        sync()
        print("\n--- 監査 ---")
        audit()


if __name__ == "__main__":
    main()
