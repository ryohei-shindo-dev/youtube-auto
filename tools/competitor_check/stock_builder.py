"""判定結果からネタ候補ストックを構築する."""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path


def _normalize_text(value: str) -> str:
    normalized = value.strip()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = normalized.replace("｜", "|")
    return normalized


def _extract_theme_text(result: dict) -> str:
    action_detail = _normalize_text(result.get("action_detail", ""))
    reason_short = _normalize_text(result.get("reason_short", ""))
    if action_detail:
        return action_detail
    return reason_short


def _resolve_stock_type(result: dict) -> str:
    recommended_action = result.get("recommended_action", "")
    if recommended_action == "use_as_material":
        return "material"
    return "normal"


def _build_duplicate_group_key(theme_text: str, topics: list[str]) -> str:
    source = theme_text or " ".join(topics)
    source = source.lower()
    source = re.sub(r"[^\w\u3040-\u30ff\u3400-\u9fff]+", "_", source)
    source = re.sub(r"_+", "_", source).strip("_")
    return source[:48] or "candidate"


def _next_candidate_id(existing: list[dict]) -> str:
    return f"theme_{len(existing) + 1:04d}"


def build_stock_candidates(discovery_summary: dict) -> list[dict]:
    """discovery summary から usable / conditional 候補だけ抽出する。"""
    candidates = []
    for channel in discovery_summary.get("channels", []):
        for result in channel.get("results", []):
            judgment = result.get("judgment")
            if judgment not in {"usable", "conditional"}:
                continue

            candidate_existing_topics = result.get("candidate_existing_topics", [])
            normalized_theme = _extract_theme_text(result)
            candidates.append(
                {
                    "normalized_theme": normalized_theme,
                    "duplicate_group_key": _build_duplicate_group_key(
                        normalized_theme,
                        candidate_existing_topics,
                    ),
                    "stock_type": _resolve_stock_type(result),
                    "judgment": judgment,
                    "risk_level": result.get("risk_level", ""),
                    "connection_candidates": candidate_existing_topics,
                    "recommended_action": result.get("recommended_action", ""),
                    "source_videos": [
                        {
                            "video_id": result["video_id"],
                            "title": result["title"],
                            "channel_id": channel["channel_id"],
                            "channel_title": channel["channel_title"],
                            "channel_url": channel["channel_url"],
                            "view_count": result["view_count"],
                            "source_url": result["source_url"],
                            "check_json_path": result.get("check_json_path", ""),
                        }
                    ],
                    "review_status": "pending",
                    "reason_short": result.get("reason_short", ""),
                }
            )
    return candidates


def _merge_candidate(target: dict, incoming: dict) -> None:
    seen_video_ids = {video["video_id"] for video in target.get("source_videos", [])}
    for video in incoming.get("source_videos", []):
        if video["video_id"] in seen_video_ids:
            continue
        target.setdefault("source_videos", []).append(video)
        seen_video_ids.add(video["video_id"])

    existing_topics = set(target.get("connection_candidates", []))
    for topic in incoming.get("connection_candidates", []):
        if topic not in existing_topics:
            target.setdefault("connection_candidates", []).append(topic)
            existing_topics.add(topic)

    if len(target.get("normalized_theme", "")) < len(incoming.get("normalized_theme", "")):
        target["normalized_theme"] = incoming["normalized_theme"]

    current_stock_type = target.get("stock_type", "normal")
    incoming_stock_type = incoming.get("stock_type", "normal")
    if current_stock_type != "material" and incoming_stock_type == "material":
        target["stock_type"] = "material"


def update_stock_file(stock_path: Path, discovery_summary: dict) -> dict:
    """stock_candidates.json を更新する。"""
    stock_path.parent.mkdir(parents=True, exist_ok=True)
    existing = {
        "generated_at": datetime.now().isoformat(),
        "source": {},
        "candidates": [],
    }
    if stock_path.exists():
        existing = json.loads(stock_path.read_text(encoding="utf-8"))

    by_key = {
        candidate["duplicate_group_key"]: candidate
        for candidate in existing.get("candidates", [])
    }

    for incoming in build_stock_candidates(discovery_summary):
        key = incoming["duplicate_group_key"]
        if key in by_key:
            _merge_candidate(by_key[key], incoming)
            continue

        incoming["candidate_id"] = _next_candidate_id(existing.get("candidates", []))
        existing.setdefault("candidates", []).append(incoming)
        by_key[key] = incoming

    existing["generated_at"] = datetime.now().isoformat()
    existing["source"] = discovery_summary.get("source", {})
    stock_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    return existing
