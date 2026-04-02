"""YouTube Studio 自動化 CLI.

使い方:
    python -m yt_studio.cli login                    # 初回ログイン
    python -m yt_studio.cli inspect --video-id XXX   # セレクタ調査用HTML取得
    python -m yt_studio.cli set --video-id XXX       # 1本だけ関連動画設定
    python -m yt_studio.cli batch --limit 5          # 関連動画一括設定
    python -m yt_studio.cli pin --limit 5            # コメント一括ピン留め
    python -m yt_studio.cli pin --limit 5 --dry-run
    python -m yt_studio.cli status                   # 処理状況確認
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sys
import time

from dotenv import load_dotenv
load_dotenv(pathlib.Path(__file__).resolve().parent.parent / ".env")

import yt_studio.browser as browser
import yt_studio.ops as ops
from yt_studio.selector import (
    LONG_VIDEO_MAP,
    select_related_video,
    get_long_video_title,
)


def cmd_login(args):
    """ブラウザを起動して手動でGoogleログインする。"""
    print(f"ブラウザを起動します（プロファイル: {browser._BROWSER_PROFILE}）")
    print("YouTube Studio にログインしてからブラウザを閉じてください。")
    pw, context, page = browser.launch()
    page.goto("https://studio.youtube.com")
    try:
        page.wait_for_event("close", timeout=0)
    except Exception:
        pass
    browser.close(pw, context)
    print("ログイン完了（cookieが保存されました）")


def cmd_inspect(args):
    """動画詳細ページのHTMLを取得する（セレクタ調査用）。"""
    pw, context, page = browser.launch()
    try:
        ops.open_video_details(page, args.video_id)
        # ページ下部までスクロール
        page.keyboard.press("End")
        time.sleep(2)
        html_path = ops.inspect_related_video_html(page)
        ops.take_debug_snapshot(page, f"inspect_{args.video_id}")
        print(f"\nHTMLとスクリーンショットを確認してセレクタを設定してください")
    finally:
        browser.close(pw, context)


def cmd_set(args):
    """1本のShortsに関連動画を設定する。"""
    if args.related:
        related_id = args.related
    else:
        related_id = select_related_video(title=args.title or "", topic=args.topic or "")

    related_title = get_long_video_title(related_id)
    print(f"動画: {args.video_id}")
    print(f"関連動画: {related_id} ({related_title})")

    if args.dry_run:
        print("[dry-run] 設定をスキップ")
        return

    pw, context, page = browser.launch()
    try:
        ops.open_video_details(page, args.video_id)
        ok = ops.set_related_video(page, related_title)
        result = "success" if ok else "failed"
        ops.log_result(args.video_id, result, "related_video", related_id)
        print(f"結果: {result}")
    except Exception as e:
        print(f"[エラー] {e}")
        ops.take_debug_snapshot(page, f"set_{args.video_id}")
        ops.log_result(args.video_id, "error", "related_video", related_id, error=str(e))
    finally:
        browser.close(pw, context)


def cmd_batch(args):
    """未設定のShortsに関連動画を一括設定する。"""
    # シートからShorts一覧を取得
    sys.path.insert(0, str(ops.SCRIPT_DIR))
    import sheets

    sheet_id = os.getenv("YOUTUBE_SHEET_ID", "")
    if not sheet_id:
        print("YOUTUBE_SHEET_ID が設定されていません")
        return

    svc = sheets.get_service()
    result = svc.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range="投稿管理!A:AC",
    ).execute()
    rows = result.get("values", [])

    # 処理済みを除外
    processed = ops.load_processed_ids()

    targets = []
    for row in rows[1:]:
        # W列=YouTube video ID, H列=タイトル, D列=トピック, C列=種別
        video_id = row[22] if len(row) > 22 else ""  # W列 (0-indexed: 22)
        title = row[7] if len(row) > 7 else ""        # H列
        topic = row[3] if len(row) > 3 else ""         # D列
        vid_type = row[2] if len(row) > 2 else ""      # C列
        youtube_url = row[10] if len(row) > 10 else ""  # K列

        if not video_id or not youtube_url:
            continue
        if video_id in processed:
            continue
        # Shortsのみ（長尺は別処理）
        if vid_type and "長尺" in vid_type:
            continue

        related_id = select_related_video(title=title, topic=topic)
        targets.append({
            "video_id": video_id,
            "title": title[:40],
            "topic": topic,
            "related_id": related_id,
            "related_title": get_long_video_title(related_id),
        })

    if not targets:
        print("設定対象のShortsがありません（全て処理済み）")
        return

    limit = args.limit or len(targets)
    targets = targets[:limit]

    print(f"対象: {len(targets)}本\n")
    for i, t in enumerate(targets, 1):
        print(f"  {i}. {t['video_id']}  {t['title']}")
        print(f"     → {t['related_id']} ({t['related_title']})")

    if args.dry_run:
        print("\n[dry-run] 設定をスキップ")
        return

    # Playwright実行
    pw, context, page = browser.launch()
    success = fail = 0
    try:
        for i, t in enumerate(targets, 1):
            print(f"\n[{i}/{len(targets)}] {t['video_id']} → {t['related_title'][:30]}")
            try:
                ops.open_video_details(page, t["video_id"])
                ok = ops.set_related_video(page, t["related_title"])
                if ok:
                    success += 1
                    ops.log_result(t["video_id"], "success", "related_video", t["related_id"])
                    print(f"  ✅ 設定完了")
                else:
                    fail += 1
                    ops.log_result(t["video_id"], "failed", "related_video", t["related_id"])
                    print(f"  ❌ 設定失敗")
            except Exception as e:
                fail += 1
                print(f"  [エラー] {e}")
                ops.take_debug_snapshot(page, f"batch_{t['video_id']}")
                ops.log_result(t["video_id"], "error", "related_video", t["related_id"], error=str(e))
                if args.fail_fast:
                    print("--fail-fast: 停止")
                    break
            time.sleep(2)
    finally:
        browser.close(pw, context)

    print(f"\n完了: 成功 {success}, 失敗 {fail}")


def cmd_pin(args):
    """未固定のコメントを一括ピン留めする。"""
    sys.path.insert(0, str(ops.SCRIPT_DIR))
    import sheets

    sheet_id = os.getenv("YOUTUBE_SHEET_ID", "")
    if not sheet_id:
        print("YOUTUBE_SHEET_ID が設定されていません")
        return

    svc = sheets.get_service()
    result = svc.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range="投稿管理!A:AC",
    ).execute()
    rows = result.get("values", [])

    # ピン留め済みを除外
    processed = ops.load_processed_ids(ops.PIN_STATE_FILE)

    targets = []
    for row in rows[1:]:
        video_id = row[22] if len(row) > 22 else ""  # W列
        title = row[7] if len(row) > 7 else ""        # H列
        status = row[6] if len(row) > 6 else ""        # G列
        youtube_url = row[10] if len(row) > 10 else ""  # K列

        if not video_id or not youtube_url or status != "公開済み":
            continue
        if video_id in processed:
            continue
        targets.append({"video_id": video_id, "title": title[:40]})

    if not targets:
        print("ピン留め対象の動画がありません（全て処理済み）")
        return

    limit = args.limit or len(targets)
    targets = targets[:limit]

    print(f"コメント固定: {len(targets)}本（処理済み: {len(processed)}本）\n")
    for i, t in enumerate(targets, 1):
        print(f"  {i}. {t['video_id']}  {t['title']}")

    if args.dry_run:
        print("\n[dry-run] 固定をスキップ")
        return

    pw, context, page = browser.launch()
    success = fail = 0
    try:
        for i, t in enumerate(targets, 1):
            print(f"\n[{i}/{len(targets)}] {t['video_id']}  {t['title']}")
            try:
                ok = ops.pin_comment(page, t["video_id"])
                if ok:
                    success += 1
                    ops.log_result(t["video_id"], "success", "pin_comment")
                else:
                    fail += 1
                    ops.log_result(t["video_id"], "failed", "pin_comment")
            except Exception as e:
                fail += 1
                print(f"  [エラー] {e}")
                ops.take_debug_snapshot(page, f"pin_{t['video_id']}")
                ops.log_result(t["video_id"], "error", "pin_comment", error=str(e))
                if args.fail_fast:
                    print("--fail-fast: 停止")
                    break
            time.sleep(2)
    finally:
        browser.close(pw, context)

    print(f"\n完了: 成功 {success}, 失敗 {fail}")


def cmd_status(args):
    """処理状況を表示する。"""
    related_done = ops.load_processed_ids(ops.RELATED_STATE_FILE)
    pin_done = ops.load_processed_ids(ops.PIN_STATE_FILE)

    print(f"\n=== 処理状況 ===")
    print(f"関連動画設定: {len(related_done)}本 完了")
    print(f"コメント固定: {len(pin_done)}本 完了")


def main():
    parser = argparse.ArgumentParser(description="YouTube Studio 自動化")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("login", help="初回ログイン")

    p = sub.add_parser("inspect", help="セレクタ調査用HTML取得")
    p.add_argument("--video-id", required=True)

    p = sub.add_parser("set", help="1本の関連動画を設定")
    p.add_argument("--video-id", required=True)
    p.add_argument("--related", help="関連動画のvideo ID（省略時は自動選定）")
    p.add_argument("--title", help="Shortsのタイトル（自動選定用）")
    p.add_argument("--topic", help="Shortsのトピック（自動選定用）")
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("batch", help="未設定Shortsに一括設定")
    p.add_argument("--limit", type=int, help="最大処理本数")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--fail-fast", action="store_true")

    p = sub.add_parser("pin", help="コメントを一括ピン留め")
    p.add_argument("--limit", type=int, help="最大処理本数")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--fail-fast", action="store_true")

    sub.add_parser("status", help="処理状況確認")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    cmds = {
        "login": cmd_login,
        "inspect": cmd_inspect,
        "set": cmd_set,
        "batch": cmd_batch,
        "pin": cmd_pin,
        "status": cmd_status,
    }
    cmds[args.command](args)


if __name__ == "__main__":
    main()
