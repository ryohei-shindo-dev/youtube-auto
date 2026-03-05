"""
auto_publish.py
投稿スケジュールに従って YouTube Shorts / TikTok / Instagram Reels を自動投稿するスクリプト。

使い方:
    python auto_publish.py                                    # 今日の分を全プラットフォームに投稿
    python auto_publish.py --dry-run                          # 投稿せずに確認だけ
    python auto_publish.py --force 2                          # day 2 を強制投稿
    python auto_publish.py --private                          # 非公開で投稿（テスト用）
    python auto_publish.py --platforms youtube tiktok         # 指定プラットフォームのみ
    python auto_publish.py --retry-failed                     # 失敗したプラットフォームだけ再投稿

cron設定例（毎朝7:00 / 毎晩19:00に自動投稿）:
    0 7 * * * cd /Users/shindoryohei/youtube-auto && venv/bin/python auto_publish.py >> logs/auto_publish.log 2>&1
    0 19 * * * cd /Users/shindoryohei/youtube-auto && venv/bin/python auto_publish.py >> logs/auto_publish.log 2>&1
"""

import argparse
import json
import os
import pathlib
import random
import sys
from datetime import datetime

from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).parent / ".env")

SCRIPT_DIR = pathlib.Path(__file__).parent
DONE_DIR = SCRIPT_DIR / "done"
SCHEDULE_FILE = SCRIPT_DIR / "posting_schedule.json"
LOG_DIR = SCRIPT_DIR / "logs"

ALL_PLATFORMS = ["youtube", "tiktok", "instagram"]

# Shorts タイトル用サフィックス（ランダムで選択）
_TITLE_SUFFIXES = [
    "長期投資の真実",
    "長期投資",
    "ガチホの真実",
    "積立投資",
]

# プラットフォーム別ハッシュタグ
_YT_HASHTAGS = "#長期投資 #積立投資 #NISA #資産形成 #ガチホ"
_TT_HASHTAGS = "#長期投資 #積立投資 #NISA #資産形成 #ガチホ #投資初心者 #お金の勉強 #fyp"
_IG_HASHTAGS = "#長期投資 #積立投資 #NISA #資産形成 #ガチホ #投資 #お金 #reels #リール"


def _get_hook_text(meta: dict) -> str:
    """metaからhookのslide_textを取得する。"""
    for s in meta.get("scenes", []):
        if s.get("role") == "hook":
            return s.get("slide_text", "")
    return ""


def _build_front_text(raw_title: str, meta: dict) -> str:
    """hookテキストからタイトル冒頭の痛みワードフレーズを組み立てる。"""
    hook_text = _get_hook_text(meta)

    if hook_text:
        pain = hook_text.replace("。", "").replace("、", "").strip()
        if len(pain) <= 2:
            return f"{pain}で悩む人へ"
        elif pain.endswith(("たい", "ない", "した")):
            return f"{pain}人へ"
        elif pain.endswith(("目", "中", "後")):
            return f"{pain}の人へ"
        elif pain.endswith("い"):
            return f"{pain}人へ"
        else:
            return f"{pain}がつらい人へ"

    for sep in ["、", "。", "，"]:
        if sep in raw_title:
            return raw_title.split(sep)[0]
    return raw_title[:15]


def _optimize_title(raw_title: str, meta: dict) -> str:
    """Shorts最適タイトルに変換する。

    形式: 痛みワード｜投資キーワード #Shorts
    例: 含み損がつらい人へ｜長期投資の真実 #Shorts
    """
    front = _build_front_text(raw_title, meta)
    suffix = random.choice(_TITLE_SUFFIXES)
    title = f"{front}｜{suffix} #Shorts"

    if len(title) > 100:
        title = f"{front[:30]}｜{suffix} #Shorts"

    return title


def _optimize_description(raw_description: str, raw_title: str) -> str:
    """YouTube用の説明文を生成する。"""
    lines = [raw_title, ""]
    if raw_description:
        lines.append(raw_description)
        lines.append("")
    lines.append(_YT_HASHTAGS)
    return "\n".join(lines)


def _optimize_tiktok_title(raw_title: str, meta: dict) -> str:
    """TikTok用のタイトル（投稿テキスト）を生成する。"""
    front = _build_front_text(raw_title, meta)
    suffix = random.choice(_TITLE_SUFFIXES)
    return f"{front}｜{suffix}"


def _optimize_instagram_caption(raw_title: str, meta: dict) -> str:
    """Instagram用のキャプションを生成する。"""
    front = _build_front_text(raw_title, meta)
    suffix = random.choice(_TITLE_SUFFIXES)
    return f"{front}｜{suffix}\n\n{_IG_HASHTAGS}"


def load_schedule() -> list:
    """投稿スケジュールを読み込む。"""
    with open(SCHEDULE_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_schedule(schedule: list):
    """投稿スケジュールを保存する。"""
    with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
        json.dump(schedule, f, ensure_ascii=False, indent=2)


def find_today_entry(schedule: list) -> dict:
    """今日投稿すべきエントリを返す。"""
    today = datetime.now().strftime("%Y/%m/%d")
    for entry in schedule:
        if entry["date"] == today and not entry.get("published"):
            return entry
    return None


def find_entry_by_day(schedule: list, day: int) -> dict:
    """指定したday番号のエントリを返す。"""
    for entry in schedule:
        if entry["day"] == day:
            return entry
    return None


def _ensure_platforms(entry: dict):
    """エントリにplatformsフィールドがなければ追加する（後方互換）。"""
    if "platforms" not in entry:
        entry["platforms"] = {
            "youtube": {
                "published": entry.get("published", False),
                "published_at": entry.get("published_at"),
                "url": None,
                "error": None,
            },
            "tiktok": {"published": False, "url": None, "error": None},
            "instagram": {"published": False, "url": None, "error": None},
        }


def _get_retry_platforms(entry: dict) -> list:
    """失敗したプラットフォームのリストを返す。"""
    _ensure_platforms(entry)
    failed = []
    for p in ALL_PLATFORMS:
        pdata = entry["platforms"].get(p, {})
        if not pdata.get("published", False):
            failed.append(p)
    return failed


def publish_entry(
    entry: dict,
    privacy: str = "public",
    dry_run: bool = False,
    platforms: list = None,
) -> dict:
    """
    1本の動画を各プラットフォームに投稿する。

    Returns:
        {"youtube": True/False, "tiktok": True/False, "instagram": True/False}
    """
    if platforms is None:
        platforms = list(ALL_PLATFORMS)

    folder = DONE_DIR / entry["folder"]
    video_path = folder / "output.mp4"
    thumbnail_path = folder / "thumbnail.png"
    transcript_path = folder / "transcript.json"

    if not video_path.exists():
        print(f"  [エラー] 動画ファイルが見つかりません: {video_path}")
        return {p: False for p in platforms}

    if not transcript_path.exists():
        print(f"  [エラー] transcript.jsonが見つかりません: {transcript_path}")
        return {p: False for p in platforms}

    # メタデータ読み込み
    with open(transcript_path, encoding="utf-8") as f:
        meta = json.load(f)

    raw_title = meta.get("title", "")
    raw_description = meta.get("description", "")
    tags = meta.get("tags", [])

    # プラットフォーム別に最適化されたテキスト
    yt_title = _optimize_title(raw_title, meta)
    yt_description = _optimize_description(raw_description, raw_title)
    tt_title = _optimize_tiktok_title(raw_title, meta)
    ig_caption = _optimize_instagram_caption(raw_title, meta)

    print(f"\n{'='*60}")
    print(f"  Day {entry['day']}: {raw_title[:40]}")
    print(f"  動画: {video_path}")
    print(f"  公開設定: {privacy}")
    print(f"  プラットフォーム: {', '.join(platforms)}")
    print(f"{'='*60}")

    if dry_run:
        print("  [dry-run] 投稿をスキップしました")
        if "youtube" in platforms:
            print(f"    YouTube: {yt_title}")
        if "tiktok" in platforms:
            print(f"    TikTok:  {tt_title}")
        if "instagram" in platforms:
            print(f"    Instagram: {ig_caption[:50]}...")
        return {p: True for p in platforms}

    results = {}
    urls = {}

    # --- YouTube ---
    if "youtube" in platforms:
        try:
            print("\n  [YouTube] 投稿中...")
            import youtube_upload
            video_id = youtube_upload.upload_video(
                video_path=str(video_path),
                title=yt_title,
                description=yt_description,
                tags=tags,
                privacy=privacy,
                thumbnail_path=str(thumbnail_path) if thumbnail_path.exists() else None,
            )
            if video_id:
                youtube_url = f"https://youtube.com/shorts/{video_id}"
                urls["youtube"] = youtube_url
                results["youtube"] = True
                print(f"  [YouTube] 投稿完了: {youtube_url}")

                # スプレッドシート更新
                _update_sheet(yt_title, youtube_url)

                # 固定コメント + いいね
                try:
                    import sheets
                    youtube = sheets.get_youtube_service()
                    _post_pinned_comment(youtube, video_id)
                    _like_video(youtube, video_id)
                except Exception as e:
                    print(f"  [警告] 初期ブースト処理に失敗: {e}")
            else:
                results["youtube"] = False
                print("  [YouTube] アップロード失敗")
        except Exception as e:
            results["youtube"] = False
            print(f"  [YouTube] エラー: {e}")

    # --- TikTok ---
    if "tiktok" in platforms:
        try:
            print("\n  [TikTok] 投稿中...")
            import tiktok_upload
            tt_tags = ["長期投資", "積立投資", "NISA", "資産形成", "ガチホ", "投資初心者", "お金の勉強"]
            publish_id = tiktok_upload.upload_video(
                video_path=str(video_path),
                title=tt_title,
                tags=tt_tags,
                privacy=privacy,
            )
            if publish_id:
                results["tiktok"] = True
                urls["tiktok"] = f"tiktok:publish_id={publish_id}"
                print(f"  [TikTok] 投稿完了")
            else:
                results["tiktok"] = False
                print("  [TikTok] 投稿失敗")
        except Exception as e:
            results["tiktok"] = False
            print(f"  [TikTok] エラー: {e}")

    # --- Instagram ---
    if "instagram" in platforms:
        try:
            print("\n  [Instagram] 投稿中...")
            import instagram_upload
            ig_url = instagram_upload.upload_video(
                video_path=str(video_path),
                caption=ig_caption,
            )
            if ig_url:
                results["instagram"] = True
                urls["instagram"] = ig_url
                print(f"  [Instagram] 投稿完了: {ig_url}")
            else:
                results["instagram"] = False
                print("  [Instagram] 投稿失敗")
        except Exception as e:
            results["instagram"] = False
            print(f"  [Instagram] エラー: {e}")

    # --- 結果サマリー ---
    print(f"\n  {'='*40}")
    for p in platforms:
        status = "✓ 成功" if results.get(p) else "✗ 失敗"
        print(f"  {p:12s}: {status}")
    print(f"  {'='*40}")

    # platforms フィールドを更新
    _ensure_platforms(entry)
    now = datetime.now().strftime("%Y/%m/%d %H:%M")
    for p in platforms:
        if results.get(p):
            entry["platforms"][p] = {
                "published": True,
                "published_at": now,
                "url": urls.get(p),
                "error": None,
            }
        else:
            entry["platforms"][p] = {
                "published": False,
                "published_at": None,
                "url": None,
                "error": "投稿に失敗しました",
            }

    return results


def _update_sheet(title: str, youtube_url: str):
    """スプレッドシートを更新する。"""
    sheet_id = os.getenv("YOUTUBE_SHEET_ID", "")
    if not sheet_id:
        return
    try:
        import sheets
        svc = sheets.get_service()
        result = svc.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range="投稿管理!A:G",
        ).execute()
        rows = result.get("values", [])
        sheet_row = None
        for i, row in enumerate(rows[1:], start=2):
            if len(row) > 6 and row[6] == title:
                sheet_row = i
                break
        if sheet_row:
            sheets.update_published(sheet_id, sheet_row, youtube_url)
        else:
            print(f"  [警告] シートでタイトル「{title}」が見つかりませんでした")
    except Exception as e:
        print(f"  [警告] シート更新に失敗: {e}")


# 固定コメントテンプレ
_PINNED_COMMENT = (
    "長期投資で一番つらい時期。\n"
    "それは今かもしれません。\n"
    "\n"
    "でも、退場しない人だけが勝つ。\n"
    "\n"
    "このチャンネルでは\n"
    "「静かな長期投資モチベーション」を毎日配信しています。"
)


def _post_pinned_comment(youtube, video_id: str):
    """動画に固定コメントを投稿する。"""
    result = youtube.commentThreads().insert(
        part="snippet",
        body={
            "snippet": {
                "videoId": video_id,
                "topLevelComment": {
                    "snippet": {
                        "textOriginal": _PINNED_COMMENT,
                    }
                },
            }
        },
    ).execute()
    comment_id = result["snippet"]["topLevelComment"]["id"]
    print(f"  固定コメント投稿完了: {comment_id}")


def _like_video(youtube, video_id: str):
    """動画にいいねする。"""
    youtube.videos().rate(id=video_id, rating="like").execute()
    print("  自動いいね完了")


def main():
    parser = argparse.ArgumentParser(description="マルチプラットフォーム自動投稿")
    parser.add_argument("--dry-run", action="store_true", help="投稿せずに確認だけ")
    parser.add_argument("--force", type=int, default=None, help="指定したday番号を強制投稿")
    parser.add_argument("--private", action="store_true", help="非公開で投稿（テスト用）")
    parser.add_argument("--platforms", nargs="+", default=None,
                        choices=ALL_PLATFORMS,
                        help="投稿先プラットフォーム（デフォルト: 全て）")
    parser.add_argument("--retry-failed", action="store_true",
                        help="失敗したプラットフォームだけ再投稿")
    args = parser.parse_args()

    privacy = "private" if args.private else "public"

    LOG_DIR.mkdir(exist_ok=True)

    schedule = load_schedule()

    # 投稿対象を決定
    if args.force is not None:
        entry = find_entry_by_day(schedule, args.force)
        if not entry:
            print(f"[エラー] day {args.force} がスケジュールにありません")
            sys.exit(1)
        if entry.get("published") and not args.dry_run and not args.retry_failed:
            print(f"[警告] day {args.force} は既に投稿済みです。再投稿します。")
    else:
        entry = find_today_entry(schedule)
        if not entry:
            print(f"[情報] 今日（{datetime.now().strftime('%Y/%m/%d')}）の投稿予定はありません。")
            for e in schedule:
                if not e.get("published"):
                    print(f"  次の投稿: day {e['day']} ({e['date']}) — {e['note']}")
                    break
            sys.exit(0)

    # プラットフォームを決定
    if args.retry_failed:
        platforms = _get_retry_platforms(entry)
        if not platforms:
            print(f"  [情報] day {entry['day']} は全プラットフォーム投稿済みです。")
            sys.exit(0)
        print(f"  再投稿対象: {', '.join(platforms)}")
    elif args.platforms:
        platforms = args.platforms
    else:
        platforms = list(ALL_PLATFORMS)

    # 投稿実行
    results = publish_entry(entry, privacy=privacy, dry_run=args.dry_run, platforms=platforms)

    if not args.dry_run:
        # published フラグ更新（YouTube成功で true — 後方互換）
        _ensure_platforms(entry)
        yt_done = entry["platforms"].get("youtube", {}).get("published", False)
        entry["published"] = yt_done
        entry["published_at"] = datetime.now().strftime("%Y/%m/%d %H:%M")

        save_schedule(schedule)

        success_count = sum(1 for r in results.values() if r)
        print(f"\n  スケジュール更新完了（day {entry['day']}: {success_count}/{len(results)} 成功）")

    # 次回予告
    next_entry = None
    for e in schedule:
        if not e.get("published"):
            next_entry = e
            break
    if next_entry:
        print(f"\n  次回: day {next_entry['day']} ({next_entry['date']}) — {next_entry['note']}")
    else:
        print("\n  全投稿が完了しました！")


if __name__ == "__main__":
    main()
