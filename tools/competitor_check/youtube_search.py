"""YouTube Data API v3 でチャンネル候補を探索する."""
from __future__ import annotations

import re

from youtube_channel_fetcher import _execute_with_backoff, _get_cached_service, fetch_channel_metadata


def _build_channel_url(channel_id: str, custom_url: str | None = None) -> str:
    if custom_url:
        cleaned = custom_url.lstrip("@")
        return f"https://www.youtube.com/@{cleaned}"
    return f"https://www.youtube.com/channel/{channel_id}"


def _slugify_text(value: str) -> str:
    slug = re.sub(r"\s+", "-", value.strip().lower())
    slug = re.sub(r"[^a-z0-9_\-\u3040-\u30ff\u3400-\u9fff]+", "-", slug).strip("-")
    return slug or "query"


def search_channels(query: str, limit: int) -> list[dict]:
    """キーワード検索でチャンネル候補を返す。"""
    if limit <= 0:
        raise ValueError("--channels は 1 以上で指定してください")

    youtube = _get_cached_service()
    search_response = _execute_with_backoff(
        youtube.search().list(
            part="snippet",
            q=query,
            type="channel",
            maxResults=min(limit, 50),
        )
    )

    channel_ids = []
    seen_ids = set()
    for item in search_response.get("items", []):
        channel_id = item.get("id", {}).get("channelId")
        if not channel_id or channel_id in seen_ids:
            continue
        seen_ids.add(channel_id)
        channel_ids.append(channel_id)

    if not channel_ids:
        return []

    channels_response = _execute_with_backoff(
        youtube.channels().list(
            part="snippet,statistics,contentDetails",
            id=",".join(channel_ids),
            maxResults=min(len(channel_ids), 50),
        )
    )

    candidates = []
    for item in channels_response.get("items", []):
        snippet = item.get("snippet", {})
        statistics = item.get("statistics", {})
        custom_url = snippet.get("customUrl")
        candidates.append(
            {
                "channel_id": item["id"],
                "channel_title": snippet.get("title", ""),
                "description": snippet.get("description", ""),
                "custom_url": custom_url,
                "channel_url": _build_channel_url(item["id"], custom_url),
                "subscriber_count": int(statistics.get("subscriberCount", 0)),
                "video_count": int(statistics.get("videoCount", 0)),
            }
        )

    candidates.sort(
        key=lambda row: (row["subscriber_count"], row["video_count"]),
        reverse=True,
    )
    return candidates[:limit]


def build_query_from_seed_channel(seed_channel_url: str) -> tuple[str, dict]:
    """起点チャンネルから探索クエリを作る。"""
    channel_data = fetch_channel_metadata(seed_channel_url)
    title = channel_data["channel_title"]
    tokens = [token for token in re.split(r"[\s/|｜〜・]+", title) if token]
    if channel_data.get("description"):
        description_tokens = [
            token
            for token in re.split(r"[\s/|｜〜・]+", channel_data["description"])
            if token
        ]
        tokens.extend(description_tokens[:3])
    query = " ".join(tokens[:5]) if tokens else title
    return query, channel_data


def search_related_channels(seed_channel_url: str, limit: int) -> dict:
    """起点チャンネルから探索クエリを作り、候補チャンネルを返す。"""
    derived_query, seed_channel = build_query_from_seed_channel(seed_channel_url)
    candidates = search_channels(derived_query, limit=limit + 1)
    filtered = [candidate for candidate in candidates if candidate["channel_id"] != seed_channel["channel_id"]]
    return {
        "derived_query": derived_query,
        "seed_channel": {
            "channel_id": seed_channel["channel_id"],
            "channel_title": seed_channel["channel_title"],
            "channel_url": seed_channel["channel_url"],
            "channel_handle": seed_channel["channel_handle"],
        },
        "candidates": filtered[:limit],
        "discovery_key": _slugify_text(derived_query),
    }


def query_discovery_source(query: str, limit: int) -> dict:
    """クエリ起点の探索情報を返す。"""
    return {
        "derived_query": query,
        "seed_channel": None,
        "candidates": search_channels(query, limit=limit),
        "discovery_key": _slugify_text(query),
    }
