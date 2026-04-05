"""競合チャンネル探索とネタ候補ストック化を行う."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from batch_runner import _format_view_count, _judgment_symbol, analyze_channel_videos
from competitor_check import DISCOVERIES_DIR, STOCK_DIR
from stock_builder import update_stock_file
from youtube_channel_fetcher import fetch_channel_videos_by_views
from youtube_search import query_discovery_source, search_related_channels


def _build_discovery_path(discovery_key: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return DISCOVERIES_DIR / f"discovery_{discovery_key}_{timestamp}.json"


def _render_candidate_table(candidates: list[dict]) -> list[str]:
    lines = [
        "### 候補チャンネル",
        "",
        "| # | チャンネル | 登録者数 | 動画数 | URL |",
        "|---|---|---:|---:|---|",
    ]
    for index, candidate in enumerate(candidates, 1):
        lines.append(
            f"| {index} | {candidate['channel_title']} | "
            f"{candidate['subscriber_count']:,} | {candidate['video_count']:,} | "
            f"{candidate['channel_url']} |"
        )
    return lines


def _render_stock_table(discovery_summary: dict) -> list[str]:
    lines = [
        "### ネタ候補",
        "",
        "| # | チャンネル | タイトル | 再生数 | 判定 | 接続候補 | 理由 |",
        "|---|---|---|---:|---|---|---|",
    ]
    rows = []
    for channel in discovery_summary.get("channels", []):
        for result in channel.get("results", []):
            if result.get("judgment") not in {"usable", "conditional"}:
                continue
            rows.append((channel, result))

    for index, (channel, result) in enumerate(rows, 1):
        topics = " / ".join(result.get("candidate_existing_topics", [])[:2])
        lines.append(
            f"| {index} | {channel['channel_title'].replace('|', '｜')} | "
            f"{result['title'].replace('|', '｜')} | {_format_view_count(result['view_count'])} | "
            f"{_judgment_symbol(result['judgment'])} | {topics.replace('|', '｜')} | "
            f"{result['reason_short'].replace('|', '｜')} |"
        )

    if not rows:
        lines.append("| - | - | - | - | - | - | usable / conditional は見つかりませんでした |")
    return lines


def render_discovery_markdown(discovery_summary: dict) -> str:
    """discovery の結果を Markdown 表示用に整形する。"""
    source = discovery_summary["source"]
    title = source.get("query") or source.get("seed_channel_url") or "discover"
    lines = [f"## Discovery: {title}", ""]
    if source.get("derived_query") and source.get("derived_query") != source.get("query"):
        lines.append(f"- 派生クエリ: {source['derived_query']}")
    lines.append(f"- 候補チャンネル数: {len(discovery_summary.get('channel_candidates', []))}")
    lines.append(f"- 各チャンネル上位本数: {source.get('top_per_channel', 0)}")
    lines.append("")
    lines.extend(_render_candidate_table(discovery_summary.get("channel_candidates", [])))
    lines.append("")
    lines.extend(_render_stock_table(discovery_summary))
    return "\n".join(lines)


def run_discovery(
    query: str | None,
    seed_channel_url: str | None,
    channels_limit: int,
    top_n: int,
    dry_run: bool,
) -> dict:
    """discover サブコマンドのメイン処理。"""
    if channels_limit <= 0:
        raise ValueError("--channels は 1 以上で指定してください")
    if top_n <= 0:
        raise ValueError("--top は 1 以上で指定してください")

    DISCOVERIES_DIR.mkdir(parents=True, exist_ok=True)
    STOCK_DIR.mkdir(parents=True, exist_ok=True)

    if query:
        discovery_source = query_discovery_source(query, limit=channels_limit)
        source = {
            "mode": "query",
            "query": query,
            "derived_query": discovery_source["derived_query"],
            "channels_requested": channels_limit,
            "top_per_channel": top_n,
        }
    else:
        discovery_source = search_related_channels(seed_channel_url, limit=channels_limit)
        source = {
            "mode": "seed_channel",
            "seed_channel_url": seed_channel_url,
            "derived_query": discovery_source["derived_query"],
            "channels_requested": channels_limit,
            "top_per_channel": top_n,
        }

    channel_candidates = discovery_source["candidates"]
    channels = []
    for candidate in channel_candidates:
        if dry_run:
            channels.append(
                {
                    "channel_id": candidate["channel_id"],
                    "channel_title": candidate["channel_title"],
                    "channel_url": candidate["channel_url"],
                    "results": [],
                }
            )
            continue

        fetched = fetch_channel_videos_by_views(candidate["channel_url"])
        analyzed = analyze_channel_videos(fetched, top_n=top_n, skip_existing=True)
        channels.append(
            {
                "channel_id": analyzed["channel_id"],
                "channel_title": analyzed["channel_title"],
                "channel_url": analyzed["channel_url"],
                "channel_handle": analyzed["channel_handle"],
                "fetched_count": analyzed["fetched_count"],
                "skipped_existing_count": analyzed["skipped_existing_count"],
                "analyzed_count": analyzed["analyzed_count"],
                "failed_count": analyzed["failed_count"],
                "results": analyzed["results"],
            }
        )

    discovery_summary = {
        "generated_at": datetime.now().isoformat(),
        "source": source,
        "seed_channel": discovery_source.get("seed_channel"),
        "channel_candidates": channel_candidates,
        "channels": channels,
    }

    discovery_path = _build_discovery_path(discovery_source["discovery_key"])
    discovery_path.write_text(
        json.dumps(discovery_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    stock_path = None
    if not dry_run:
        stock_path = STOCK_DIR / "stock_candidates.json"
        update_stock_file(stock_path, discovery_summary)

    return {
        "summary": discovery_summary,
        "discovery_path": discovery_path,
        "stock_path": stock_path,
        "markdown": render_discovery_markdown(discovery_summary),
    }
