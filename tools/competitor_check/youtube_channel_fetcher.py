"""YouTube Data API v3 でチャンネル動画一覧を取得する."""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from googleapiclient.errors import HttpError

TOOL_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TOOL_DIR.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import sheets


def _get_cached_service():
    """既存の YouTube API クライアントを再利用する。"""
    return sheets.get_youtube_service()


def _should_retry_http_error(err: HttpError) -> bool:
    """429 のみ再試行対象にする。"""
    return getattr(err, "status_code", None) == 429 or getattr(err.resp, "status", None) == 429


def _execute_with_backoff(request, max_retries: int = 5):
    """429 のときだけ指数バックオフで再試行する。"""
    for attempt in range(max_retries + 1):
        try:
            return request.execute()
        except HttpError as err:
            if not _should_retry_http_error(err) or attempt >= max_retries:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("YouTube API request failed after retries")


def parse_channel_url(channel_url: str) -> dict[str, str]:
    """チャンネル URL から handle または channel_id を抽出する。"""
    parsed = urlparse(channel_url)
    host = parsed.netloc.lower()
    if "youtube.com" not in host:
        raise ValueError(f"YouTubeチャンネルURLではありません: {channel_url}")

    path = parsed.path.rstrip("/")
    if path.startswith("/@"):
        handle = path.split("/", 2)[1][1:]
        return {"channel_url": channel_url, "handle": handle}
    if path.startswith("/channel/"):
        channel_id = path.split("/", 3)[2]
        return {"channel_url": channel_url, "channel_id": channel_id}

    query = parse_qs(parsed.query)
    if "channel_id" in query and query["channel_id"]:
        return {"channel_url": channel_url, "channel_id": query["channel_id"][0]}

    raise ValueError("対応しているチャンネルURLは /@handle または /channel/UC... 形式です")


def _fetch_uploads_playlist_id(youtube, parsed: dict[str, str]) -> dict[str, str]:
    """チャンネル情報と uploads playlist ID を取得する。"""
    params = {
        "part": "contentDetails,snippet",
        "maxResults": 1,
    }
    if parsed.get("handle"):
        params["forHandle"] = parsed["handle"]
    else:
        params["id"] = parsed["channel_id"]

    response = _execute_with_backoff(youtube.channels().list(**params))
    items = response.get("items", [])
    if not items:
        raise RuntimeError(f"チャンネル情報を取得できませんでした: {parsed['channel_url']}")

    item = items[0]
    return {
        "channel_id": item["id"],
        "channel_title": item["snippet"]["title"],
        "description": item["snippet"].get("description", ""),
        "channel_handle": parsed.get("handle") or item["id"],
        "uploads_playlist_id": item["contentDetails"]["relatedPlaylists"]["uploads"],
    }


def _fetch_playlist_video_items(youtube, playlist_id: str) -> list[dict]:
    """uploads playlist をページネーションしながら走査する。"""
    items = []
    page_token = None
    while True:
        response = _execute_with_backoff(
            youtube.playlistItems().list(
                part="snippet",
                playlistId=playlist_id,
                maxResults=50,
                pageToken=page_token,
            )
        )
        for item in response.get("items", []):
            resource = item["snippet"].get("resourceId", {})
            video_id = resource.get("videoId")
            if not video_id:
                continue
            items.append(
                {
                    "video_id": video_id,
                    "title": item["snippet"].get("title", ""),
                    "published_at": item["snippet"].get("publishedAt"),
                }
            )
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return items


def _chunked(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _fetch_video_statistics(youtube, video_ids: list[str]) -> dict[str, dict]:
    """videos.list を 50 件ずつ叩いて統計情報を返す。"""
    stats = {}
    for chunk in _chunked(video_ids, 50):
        response = _execute_with_backoff(
            youtube.videos().list(
                part="statistics,snippet",
                id=",".join(chunk),
                maxResults=50,
            )
        )
        for item in response.get("items", []):
            statistics = item.get("statistics", {})
            stats[item["id"]] = {
                "view_count": int(statistics.get("viewCount", 0)),
                "title": item.get("snippet", {}).get("title", ""),
            }
    return stats


def _slugify_channel_handle(value: str) -> str:
    lowered = value.lower()
    slug = re.sub(r"[^a-z0-9_-]+", "-", lowered).strip("-")
    return slug or "channel"


def fetch_channel_videos_by_views(channel_url: str) -> dict:
    """チャンネルの全動画を取得し、再生数降順に並べて返す。"""
    youtube = _get_cached_service()
    parsed = parse_channel_url(channel_url)
    channel_info = _fetch_uploads_playlist_id(youtube, parsed)
    playlist_items = _fetch_playlist_video_items(youtube, channel_info["uploads_playlist_id"])
    statistics = _fetch_video_statistics(
        youtube,
        [item["video_id"] for item in playlist_items],
    )

    videos = []
    for item in playlist_items:
        video_id = item["video_id"]
        stat = statistics.get(video_id)
        if not stat:
            continue
        videos.append(
            {
                "video_id": video_id,
                "title": stat["title"] or item["title"],
                "view_count": stat["view_count"],
                "published_at": item.get("published_at"),
                "url": f"https://www.youtube.com/watch?v={video_id}",
            }
        )

    videos.sort(key=lambda row: row["view_count"], reverse=True)
    return {
        "channel_url": channel_url,
        "channel_id": channel_info["channel_id"],
        "channel_title": channel_info["channel_title"],
        "description": channel_info.get("description", ""),
        "channel_handle": _slugify_channel_handle(channel_info["channel_handle"]),
        "videos": videos,
    }


def fetch_channel_metadata(channel_url: str) -> dict:
    """チャンネルの基本情報だけを返す。"""
    youtube = _get_cached_service()
    parsed = parse_channel_url(channel_url)
    channel_info = _fetch_uploads_playlist_id(youtube, parsed)
    return {
        "channel_url": channel_url,
        "channel_id": channel_info["channel_id"],
        "channel_title": channel_info["channel_title"],
        "description": channel_info.get("description", ""),
        "channel_handle": _slugify_channel_handle(channel_info["channel_handle"]),
    }
