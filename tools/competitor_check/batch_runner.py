"""チャンネル単位の一括判定を実行する."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from competitor_check import BATCHES_DIR, OUTPUTS_DIR, load_existing_result, run_video_check
from youtube_channel_fetcher import fetch_channel_videos_by_views


def _judgment_symbol(value: str) -> str:
    return {
        "usable": "○",
        "conditional": "△",
        "unusable": "×",
    }.get(value, "?")


def _format_view_count(value: int) -> str:
    if value >= 10000:
        man = value / 10000
        if man >= 100 and float(man).is_integer():
            return f"{int(man)}万"
        return f"{man:.1f}".rstrip("0").rstrip(".") + "万"
    return f"{value:,}"


def render_batch_markdown(channel_title: str, rows: list[dict]) -> str:
    """バッチ判定結果を Markdown 表で返す。"""
    lines = [
        f"## {channel_title} 人気動画判定",
        "",
        "| # | タイトル | 再生数 | 判定 | 理由 |",
        "|---|---|---:|---|---|",
    ]
    for index, row in enumerate(rows, 1):
        safe_title = row["title"].replace("|", "｜")
        safe_reason = row["reason_short"].replace("|", "｜")
        lines.append(
            f"| {index} | {safe_title} | {_format_view_count(row['view_count'])} | "
            f"{_judgment_symbol(row['judgment'])} | {safe_reason} |"
        )
    return "\n".join(lines)


def _build_summary_path(channel_handle: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return BATCHES_DIR / f"{channel_handle}_{timestamp}.json"


def analyze_channel_videos(channel_data: dict, top_n: int, skip_existing: bool = True) -> dict:
    """取得済みチャンネル動画を上位 N 本だけ判定する。"""
    if top_n <= 0:
        raise ValueError("--top は 1 以上で指定してください")

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    selected = channel_data["videos"][:top_n]

    skipped_existing_count = 0
    analyzed_count = 0
    failed_count = 0
    summary_rows = []

    for video in selected:
        existing = load_existing_result(video["video_id"]) if skip_existing else None
        if existing is not None:
            skipped_existing_count += 1
            result = existing
            check_json_path = OUTPUTS_DIR / f"{video['video_id']}.json"
        else:
            try:
                run_result = run_video_check(video["url"])
                analyzed_count += 1
                result = run_result["result"]
                check_json_path = run_result["path"]
            except Exception as err:
                failed_count += 1
                summary_rows.append(
                    {
                        "video_id": video["video_id"],
                        "title": video["title"],
                        "view_count": video["view_count"],
                        "judgment": "failed",
                        "reason_short": str(err),
                        "source_url": video["url"],
                    }
                )
                continue

        judgment = result.get("judgment", {})
        connections = result.get("connections", {})
        summary_rows.append(
            {
                "video_id": video["video_id"],
                "title": result.get("title") or video["title"],
                "view_count": video["view_count"],
                "judgment": judgment.get("primary", "unknown"),
                "reason_short": judgment.get("reason_short", ""),
                "risk_level": judgment.get("risk_level", ""),
                "translation_cost": judgment.get("translation_cost", ""),
                "source_url": video["url"],
                "check_json_path": str(check_json_path),
                "candidate_existing_topics": connections.get("candidate_existing_topics", []),
                "recommended_action": connections.get("recommended_action", ""),
                "action_detail": connections.get("action_detail", ""),
            }
        )

    return {
        "channel_url": channel_data["channel_url"],
        "channel_id": channel_data["channel_id"],
        "channel_title": channel_data["channel_title"],
        "channel_handle": channel_data["channel_handle"],
        "top_n_requested": top_n,
        "fetched_count": len(channel_data["videos"]),
        "skipped_existing_count": skipped_existing_count,
        "analyzed_count": analyzed_count,
        "failed_count": failed_count,
        "results": summary_rows,
    }


def run_channel_batch(channel_url: str, top_n: int) -> dict:
    """チャンネル URL から人気動画を上位 N 本だけ判定する。"""
    BATCHES_DIR.mkdir(parents=True, exist_ok=True)

    fetched = fetch_channel_videos_by_views(channel_url)
    summary = analyze_channel_videos(fetched, top_n=top_n, skip_existing=True)

    summary_path = _build_summary_path(summary["channel_handle"])
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "summary": summary,
        "summary_path": summary_path,
        "markdown": render_batch_markdown(summary["channel_title"], summary["results"]),
    }
