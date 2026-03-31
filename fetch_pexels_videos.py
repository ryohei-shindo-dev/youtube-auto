"""Pexels Video API で動画素材を事前収集する.

使い方:
    python fetch_pexels_videos.py                    # 縦型（Shorts用）全カテゴリ
    python fetch_pexels_videos.py --landscape         # 横型（長尺用）全カテゴリ
    python fetch_pexels_videos.py --landscape --category anxiety
    python fetch_pexels_videos.py --list              # 縦型一覧
    python fetch_pexels_videos.py --list --landscape  # 横型一覧
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import time

import requests

SCRIPT_DIR = pathlib.Path(__file__).parent
OUTPUT_BASE_PORTRAIT = SCRIPT_DIR / "assets" / "videos" / "shorts_hook"
OUTPUT_BASE_LANDSCAPE = SCRIPT_DIR / "assets" / "videos" / "long_emotion"

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

# 横型（長尺用）の検索クエリ — 空気感重視、人物少なめ
CATEGORY_QUERIES_LANDSCAPE = {
    "anxiety": [
        "dark room alone night",
        "rain on window night",
        "empty street night city",
        "shadows dark moody",
    ],
    "comparison": [
        "crowd walking city busy",
        "traffic lights night urban",
        "people passing by street",
        "office building windows",
    ],
    "data": [
        "newspaper coffee morning",
        "bookshelf library quiet",
        "desk workspace minimal",
        "clock time passing",
    ],
    "recovery": [
        "sunrise over mountains",
        "light through trees morning",
        "calm lake morning mist",
        "open road horizon",
    ],
    "steady": [
        "candle flame dark room",
        "rain drops slow motion",
        "quiet forest path",
        "waves shore calm evening",
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


def _pick_best_file(video: dict, landscape: bool = False) -> dict | None:
    """動画の video_files から最適な解像度を選択。"""
    candidates = []
    for vf in video.get("video_files", []):
        h = vf.get("height") or 0
        w = vf.get("width") or 0
        if h < 720:
            continue
        if landscape:
            # 横型: w > h
            if w > h:
                candidates.append(vf)
        else:
            # 縦型: h > w
            if h > w:
                candidates.append(vf)
    if not candidates:
        # フォールバック: 向き問わず720p以上
        for vf in video.get("video_files", []):
            if (vf.get("height") or 0) >= 720:
                candidates.append(vf)
    if not candidates:
        return None
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


def _load_metadata(path: pathlib.Path = None) -> dict:
    """メタデータ読み込み。"""
    p = path or (OUTPUT_BASE_PORTRAIT / "metadata.json")
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"videos": []}


def _save_metadata(data: dict, path: pathlib.Path = None):
    """メタデータ保存。"""
    p = path or (OUTPUT_BASE_PORTRAIT / "metadata.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def fetch_category(category: str, queries: list[str], landscape: bool = False):
    """1カテゴリの動画を収集。"""
    output_base = OUTPUT_BASE_LANDSCAPE if landscape else OUTPUT_BASE_PORTRAIT
    metadata_path = output_base / "metadata.json"
    orientation = "landscape" if landscape else "portrait"

    meta = _load_metadata(metadata_path)
    existing_ids = {v["pexels_id"] for v in meta["videos"]}
    category_count = sum(1 for v in meta["videos"] if v["category"] == category)

    if category_count >= TARGET_PER_CATEGORY:
        print(f"  {category}: 既に {category_count} 本あり（目標 {TARGET_PER_CATEGORY}）。スキップ")
        return

    needed = TARGET_PER_CATEGORY - category_count
    collected = 0
    cat_dir = output_base / category
    cat_dir.mkdir(parents=True, exist_ok=True)

    for query in queries:
        if collected >= needed:
            break
        print(f"  検索: '{query}'")
        videos = _search_videos(query, orientation=orientation, per_page=8)
        time.sleep(0.5)  # レート制限対策

        for video in videos:
            if collected >= needed:
                break
            vid = video["id"]
            if vid in existing_ids:
                continue

            duration = video.get("duration", 0)
            # 3〜15秒の動画を選択
            if duration < 3 or duration > 15:
                continue

            best_file = _pick_best_file(video, landscape=landscape)
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
                _save_metadata(meta, metadata_path)
                collected += 1
                time.sleep(0.3)

    print(f"  {category}: {collected} 本追加（合計 {category_count + collected} 本）")


def list_videos(landscape: bool = False):
    """収集済み動画一覧を表示。"""
    output_base = OUTPUT_BASE_LANDSCAPE if landscape else OUTPUT_BASE_PORTRAIT
    meta = _load_metadata(output_base / "metadata.json")
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
    parser.add_argument("--landscape", action="store_true", help="横型（長尺用）を収集")
    parser.add_argument("--list", action="store_true", help="収集済み一覧表示")
    args = parser.parse_args()

    landscape = args.landscape
    queries_map = CATEGORY_QUERIES_LANDSCAPE if landscape else CATEGORY_QUERIES
    label = "横型（長尺用）" if landscape else "縦型（Shorts用）"

    if args.list:
        list_videos(landscape=landscape)
        return

    _load_env()

    if args.category:
        if args.category not in queries_map:
            print(f"不明なカテゴリ: {args.category}")
            print(f"有効なカテゴリ: {', '.join(queries_map)}")
            return
        print(f"=== {args.category} {label}の動画を収集 ===")
        fetch_category(args.category, queries_map[args.category], landscape=landscape)
    else:
        print(f"=== 全カテゴリ {label}の動画を収集 ===")
        for cat, queries in queries_map.items():
            print(f"\n--- {cat} ---")
            fetch_category(cat, queries, landscape=landscape)

    print("\n=== 完了 ===")
    list_videos(landscape=landscape)


if __name__ == "__main__":
    main()
