"""Pexels Video API で Shorts hook 用の縦型動画を事前収集する.

使い方:
    python fetch_pexels_videos.py                # 全カテゴリ収集
    python fetch_pexels_videos.py --category anxiety  # 指定カテゴリのみ
    python fetch_pexels_videos.py --list          # 収集済み一覧表示
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import time

import requests

SCRIPT_DIR = pathlib.Path(__file__).parent
OUTPUT_BASE = SCRIPT_DIR / "assets" / "videos" / "shorts_hook"
METADATA_PATH = OUTPUT_BASE / "metadata.json"

# Pexels API
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
PEXELS_VIDEO_SEARCH_URL = "https://api.pexels.com/videos/search"

# カテゴリ → 検索クエリ（写真カテゴリと対応）
# 各カテゴリ複数クエリで多様性を確保
CATEGORY_QUERIES = {
    "anxiety": [
        "worried person phone night",
        "stressed person sitting alone",
        "person looking at screen dark",
        "anxious waiting alone",
    ],
    "comparison": [
        "person scrolling phone social media",
        "person watching news screen",
        "busy city crowd walking",
        "person comparing thinking",
    ],
    "data": [
        "stock market chart screen",
        "financial newspaper reading",
        "numbers data screen",
        "office desk documents",
    ],
    "recovery": [
        "sunrise morning calm",
        "person walking nature peaceful",
        "light through window morning",
        "calm ocean waves",
    ],
    "steady": [
        "person sitting quietly thinking",
        "quiet road walking alone",
        "rain window calm",
        "night city lights peaceful",
    ],
}

# 1カテゴリあたりの目標本数
TARGET_PER_CATEGORY = 12


def _load_env():
    """PEXELS_API_KEY を .env から読み込む。"""
    global PEXELS_API_KEY
    if PEXELS_API_KEY:
        return
    env_path = SCRIPT_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("PEXELS_API_KEY="):
                PEXELS_API_KEY = line.split("=", 1)[1].strip()
                break
    if not PEXELS_API_KEY:
        raise RuntimeError("PEXELS_API_KEY が未設定です")


def _search_videos(query: str, orientation: str = "portrait",
                   per_page: int = 10) -> list[dict]:
    """Pexels Video API で検索。"""
    headers = {"Authorization": PEXELS_API_KEY}
    params = {
        "query": query,
        "orientation": orientation,
        "size": "medium",
        "per_page": per_page,
    }
    resp = requests.get(PEXELS_VIDEO_SEARCH_URL, headers=headers, params=params)
    resp.raise_for_status()
    return resp.json().get("videos", [])


def _pick_best_file(video: dict, max_height: int = 1920) -> dict | None:
    """動画の video_files から最適な解像度を選択。"""
    candidates = []
    for vf in video.get("video_files", []):
        h = vf.get("height") or 0
        w = vf.get("width") or 0
        # 縦型（h > w）で適切なサイズ
        if h > w and h <= max_height and h >= 720:
            candidates.append(vf)
    if not candidates:
        # 縦型が見つからなければ横型も候補に
        for vf in video.get("video_files", []):
            h = vf.get("height") or 0
            if h <= max_height and h >= 720:
                candidates.append(vf)
    if not candidates:
        return None
    # 解像度が高い順にソート
    candidates.sort(key=lambda x: (x.get("height", 0)), reverse=True)
    return candidates[0]


def _download_video(url: str, output_path: pathlib.Path) -> bool:
    """動画ファイルをダウンロード。"""
    try:
        resp = requests.get(url, stream=True, timeout=60)
        resp.raise_for_status()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"    ダウンロード失敗: {e}")
        return False


def _load_metadata() -> dict:
    """メタデータ読み込み。"""
    if METADATA_PATH.exists():
        return json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    return {"videos": []}


def _save_metadata(data: dict):
    """メタデータ保存。"""
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    METADATA_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def fetch_category(category: str, queries: list[str]):
    """1カテゴリの動画を収集。"""
    meta = _load_metadata()
    existing_ids = {v["pexels_id"] for v in meta["videos"]}
    category_count = sum(1 for v in meta["videos"] if v["category"] == category)

    if category_count >= TARGET_PER_CATEGORY:
        print(f"  {category}: 既に {category_count} 本あり（目標 {TARGET_PER_CATEGORY}）。スキップ")
        return

    needed = TARGET_PER_CATEGORY - category_count
    collected = 0
    cat_dir = OUTPUT_BASE / category
    cat_dir.mkdir(parents=True, exist_ok=True)

    for query in queries:
        if collected >= needed:
            break
        print(f"  検索: '{query}'")
        videos = _search_videos(query, per_page=8)
        time.sleep(0.5)  # レート制限対策

        for video in videos:
            if collected >= needed:
                break
            vid = video["id"]
            if vid in existing_ids:
                continue

            duration = video.get("duration", 0)
            # 3〜15秒の動画を選択（hook用に適切な長さ）
            if duration < 3 or duration > 15:
                continue

            best_file = _pick_best_file(video)
            if not best_file:
                continue

            filename = f"{category}_{vid}.mp4"
            output_path = cat_dir / filename

            print(f"    [{collected+1}/{needed}] ID:{vid} ({duration}秒, "
                  f"{best_file.get('width')}x{best_file.get('height')})")

            if _download_video(best_file["link"], output_path):
                entry = {
                    "pexels_id": vid,
                    "category": category,
                    "filename": filename,
                    "query": query,
                    "duration": duration,
                    "width": best_file.get("width", 0),
                    "height": best_file.get("height", 0),
                    "url": video.get("url", ""),
                    "photographer": video.get("user", {}).get("name", ""),
                    "status": "downloaded",
                }
                meta["videos"].append(entry)
                existing_ids.add(vid)
                _save_metadata(meta)
                collected += 1
                time.sleep(0.3)

    print(f"  {category}: {collected} 本追加（合計 {category_count + collected} 本）")


def list_videos():
    """収集済み動画一覧を表示。"""
    meta = _load_metadata()
    if not meta["videos"]:
        print("収集済み動画なし")
        return

    by_cat: dict[str, list] = {}
    for v in meta["videos"]:
        by_cat.setdefault(v["category"], []).append(v)

    total = 0
    for cat in sorted(by_cat):
        videos = by_cat[cat]
        print(f"\n{cat}: {len(videos)} 本")
        for v in videos:
            status = v.get("status", "downloaded")
            print(f"  {v['filename']} ({v['duration']}秒, "
                  f"{v['width']}x{v['height']}) [{status}]")
            total += 1
    print(f"\n合計: {total} 本")


def main():
    parser = argparse.ArgumentParser(description="Pexels動画素材の事前収集")
    parser.add_argument("--category", help="指定カテゴリのみ収集")
    parser.add_argument("--list", action="store_true", help="収集済み一覧表示")
    args = parser.parse_args()

    if args.list:
        list_videos()
        return

    _load_env()

    if args.category:
        if args.category not in CATEGORY_QUERIES:
            print(f"不明なカテゴリ: {args.category}")
            print(f"有効なカテゴリ: {', '.join(CATEGORY_QUERIES)}")
            return
        print(f"=== {args.category} カテゴリの動画を収集 ===")
        fetch_category(args.category, CATEGORY_QUERIES[args.category])
    else:
        print("=== 全カテゴリの動画を収集 ===")
        for cat, queries in CATEGORY_QUERIES.items():
            print(f"\n--- {cat} ---")
            fetch_category(cat, queries)

    print("\n=== 完了 ===")
    list_videos()


if __name__ == "__main__":
    main()
