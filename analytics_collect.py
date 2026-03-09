"""
analytics_collect.py
YouTube Data API で投稿済み動画の再生数・いいね・コメント数を収集するスクリプト。

使い方:
    python analytics_collect.py           # 全投稿済み動画の統計を収集
    python analytics_collect.py --json    # JSON形式で出力

cron設定例（毎晩22:00に収集）:
    0 22 * * * cd /Users/shindoryohei/youtube-auto && venv/bin/python analytics_collect.py >> logs/analytics.log 2>&1
"""

import json
import os
import pathlib
from datetime import datetime

import sheets

SCRIPT_DIR = pathlib.Path(__file__).parent
ANALYTICS_FILE = SCRIPT_DIR / "analytics_log.json"
STRATEGY_FILE = SCRIPT_DIR / "CHANNEL_STRATEGY.md"


def collect_analytics():
    """投稿済み動画の統計を収集する。"""
    youtube = sheets.get_youtube_service()

    # チャンネルの全動画を取得
    video_ids = _get_channel_video_ids(youtube)
    if not video_ids:
        print("チャンネルに動画がありません。")
        return []

    # 統計を取得
    stats = _get_video_stats(youtube, video_ids)
    return stats


def _get_channel_video_ids(youtube) -> list:
    """チャンネルの全Shorts動画IDを取得する。"""
    # 自分のチャンネルのアップロードプレイリストを取得
    ch_res = youtube.channels().list(part="contentDetails", mine=True).execute()
    if not ch_res.get("items"):
        return []

    uploads_id = ch_res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    # プレイリストから全動画IDを取得
    video_ids = []
    page_token = None
    while True:
        pl_res = youtube.playlistItems().list(
            part="contentDetails",
            playlistId=uploads_id,
            maxResults=50,
            pageToken=page_token,
        ).execute()

        for item in pl_res.get("items", []):
            video_ids.append(item["contentDetails"]["videoId"])

        page_token = pl_res.get("nextPageToken")
        if not page_token:
            break

    return video_ids


def _get_video_stats(youtube, video_ids: list) -> list:
    """動画IDリストの統計情報を取得する。"""
    stats = []

    # 50件ずつバッチ取得
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        res = youtube.videos().list(
            part="snippet,statistics",
            id=",".join(batch),
        ).execute()

        for item in res.get("items", []):
            s = item["statistics"]
            snippet = item["snippet"]
            stats.append({
                "video_id": item["id"],
                "title": snippet.get("title", ""),
                "published_at": snippet.get("publishedAt", ""),
                "views": int(s.get("viewCount", 0)),
                "likes": int(s.get("likeCount", 0)),
                "comments": int(s.get("commentCount", 0)),
            })

    # 公開日順にソート
    stats.sort(key=lambda x: x["published_at"])
    return stats


def save_analytics(stats: list):
    """統計データをJSONファイルに保存する。"""
    # 既存データを読み込み
    history = {}
    if ANALYTICS_FILE.exists():
        with open(ANALYTICS_FILE, encoding="utf-8") as f:
            history = json.load(f)

    # 今日の日付をキーにして保存
    today = datetime.now().strftime("%Y-%m-%d")
    history[today] = stats

    with open(ANALYTICS_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

    print(f"  analytics_log.json 更新完了（{today}: {len(stats)}本）")


def update_strategy_log(stats: list):
    """CHANNEL_STRATEGY.mdの分析ログテーブルを更新する。"""
    if not STRATEGY_FILE.exists():
        return

    content = STRATEGY_FILE.read_text(encoding="utf-8")

    # テーブルヘッダーを探す
    marker = "| Day | 動画 | 再生 | 維持率 | いいね率 | コメント | hook |"
    if marker not in content:
        print("  [警告] CHANNEL_STRATEGY.mdに分析ログテーブルが見つかりません")
        return

    # シートからNo.とフォルダ名のマッピングを取得
    sheet_id = os.getenv("YOUTUBE_SHEET_ID", "")
    folder_to_no = {}
    if sheet_id:
        try:
            svc = sheets.get_service()
            result = svc.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range="投稿管理!A:B",
            ).execute()
            for row in result.get("values", [])[1:]:
                no = sheets.get_cell(row, 0)
                folder = sheets.get_cell(row, 1)
                if no and folder:
                    folder_to_no[folder] = no
        except Exception:
            pass

    # transcript.jsonからhookを取得
    done_dir = SCRIPT_DIR / "done"
    hook_map = {}  # title → hook
    if done_dir.exists():
        for folder_dir in done_dir.iterdir():
            if not folder_dir.is_dir():
                continue
            tp = folder_dir / "transcript.json"
            if not tp.exists():
                continue
            with open(tp, encoding="utf-8") as f:
                data = json.load(f)
            raw_title = data.get("title", "")
            hook = ""
            for s in data.get("scenes", []):
                if s.get("role") == "hook":
                    hook = s.get("slide_text", "").replace("。", "")
                    break
            no = folder_to_no.get(folder_dir.name, "?")
            hook_map[raw_title] = {"hook": hook, "no": no}

    # テーブル行を生成
    lines = [
        marker,
        "|---|---|---|---|---|---|---|",
    ]
    for s in stats:
        title_short = s["title"][:20]
        like_rate = f"{s['likes'] / s['views'] * 100:.1f}%（{s['likes']}件）" if s["views"] > 0 else "-"

        # hookとDay番号を特定
        hook_info = None
        for raw_title, info in hook_map.items():
            if raw_title in s["title"] or s["title"].split("｜")[0] in raw_title:
                hook_info = info
                break

        day = hook_info["no"] if hook_info else "?"
        hook = hook_info["hook"] if hook_info else "-"

        lines.append(
            f"| {day} | {title_short} | {s['views']} | - | {like_rate} | {s['comments']} | {hook} |"
        )

    # テーブル部分を置換
    # 既存テーブルの開始と終了を特定
    idx_start = content.index(marker)
    # テーブルの終わり（空行または次のセクション）
    after_marker = content[idx_start:]
    table_lines = after_marker.split("\n")
    table_end = 0
    for i, line in enumerate(table_lines):
        if i == 0:
            continue
        if line.startswith("|"):
            table_end = i
        else:
            break

    # 既存テーブルを新しいテーブルで置換
    old_table = "\n".join(table_lines[:table_end + 1])
    new_table = "\n".join(lines)
    content = content.replace(old_table, new_table)

    STRATEGY_FILE.write_text(content, encoding="utf-8")
    print("  CHANNEL_STRATEGY.md 分析ログ更新完了")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="YouTube Shorts 分析データ収集")
    parser.add_argument("--json", action="store_true", help="JSON形式で標準出力")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  分析データ収集: {datetime.now().strftime('%Y/%m/%d %H:%M')}")
    print(f"{'='*60}")

    stats = collect_analytics()
    if not stats:
        return

    # 結果表示
    total_views = sum(s["views"] for s in stats)
    total_likes = sum(s["likes"] for s in stats)
    print(f"\n  動画数: {len(stats)}本")
    print(f"  合計再生: {total_views}")
    print(f"  合計いいね: {total_likes}")

    for s in stats:
        like_pct = f"{s['likes'] / s['views'] * 100:.1f}%" if s["views"] > 0 else "-"
        print(f"  {s['title'][:30]:30s}  再生:{s['views']:>6}  いいね:{like_pct:>6}  コメント:{s['comments']}")

    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))

    # 保存
    save_analytics(stats)
    update_strategy_log(stats)


if __name__ == "__main__":
    main()
