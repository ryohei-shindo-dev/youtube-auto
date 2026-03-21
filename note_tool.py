"""
note_tool.py — note記事管理の唯一のCLI入口。

使い方:
    python note_tool.py collect-ids
    python note_tool.py sync-manifest
    python note_tool.py publish --file xxx.md --image xxx.png --schedule "2026-04-01 12:30"
    python note_tool.py replace-images [--limit 5] [--resume] [--dry-run]
    python note_tool.py rewrite-body --note-id nXXX --file xxx.md
    python note_tool.py fix-link-cards [--limit 5] [--resume]
    python note_tool.py reschedule --note-id nXXX --schedule "2026-04-01 12:30"
    python note_tool.py discard-draft --note-id nXXX
    python note_tool.py inspect --note-id nXXX
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
from datetime import datetime

import note_ops as ops

SCRIPT_DIR = pathlib.Path(__file__).parent


# ── 共通ヘルパー ──

def _manifest_targets(manifest: list[dict], resume: bool = False) -> list[dict]:
    """manifestから処理対象を抽出する。--resume時は成功済みをスキップ。"""
    if resume:
        return [m for m in manifest if m.get("last_result") != "success"]
    return manifest


def _run_batch(page, targets: list[dict], command: str, manifest: list[dict],
               process_fn, dry_run: bool = False, fail_fast: bool = False):
    """バッチ処理の共通ループ。"""
    print(f"対象: {len(targets)}本" + (" (dry-run)" if dry_run else ""))

    if dry_run:
        for i, t in enumerate(targets, 1):
            print(f"  [{i}] {t.get('title', '')[:40]} (ID: {t.get('note_id', '')})")
        return

    success = fail = 0
    for i, t in enumerate(targets, 1):
        title = t.get("title", "")[:35]
        note_id = t.get("note_id", "")
        print(f"\n{'=' * 50}")
        print(f"  [{i}/{len(targets)}] {title}")
        print(f"  ID: {note_id}")
        print(f"{'=' * 50}")

        try:
            ok = process_fn(page, t)
            result = ops.RESULT_SUCCESS if ok else ops.RESULT_FAILED
            if ok:
                success += 1
            else:
                fail += 1
                ops.take_debug_snapshot(page, f"{command}_{note_id}")
        except Exception as e:
            result = ops.RESULT_ERROR
            fail += 1
            print(f"  [エラー] {e}")
            ops.take_debug_snapshot(page, f"{command}_{note_id}")

        ops.log_result(note_id, command, result)
        ops.update_manifest_row(manifest, note_id, command, result)

        # 失敗時は即座にmanifest保存（リカバリ用）
        if result != ops.RESULT_SUCCESS:
            ops.save_manifest(manifest)

        if fail_fast and fail > 0:
            print(f"\n--fail-fast: 失敗が発生したため停止")
            break

        time.sleep(2)

    # バッチ終了時にmanifest保存
    ops.save_manifest(manifest)
    print(f"\n{'=' * 50}")
    print(f"  完了: 成功{success}, 失敗{fail}")
    print(f"{'=' * 50}")


# ── サブコマンド ──

def cmd_collect_ids(args):
    """APIから全記事のIDを収集する。"""
    pw, context, page = ops.launch()
    try:
        notes = ops.collect_note_ids(page)
        output = SCRIPT_DIR / "scheduled_notes.json"
        with open(output, "w", encoding="utf-8") as f:
            json.dump({"notes": notes}, f, ensure_ascii=False, indent=2)
        print(f"\n全記事: {len(notes)}本 → {output}")
        for n in sorted(notes, key=lambda x: x.get("publish_at", "")):
            print(f"  {n['status']:10} | {n['publish_at'][:16] if n['publish_at'] else '':16} | {n['title'][:35]}")
    finally:
        ops.close(pw, context)


def cmd_sync_manifest(args):
    """note管理シートからmanifestを構築/同期する。"""
    manifest = ops.build_manifest_from_sheet()
    ops.save_manifest(manifest)
    print(f"manifest同期完了: {len(manifest)}本 → {ops.MANIFEST_PATH}")

    # 統計
    with_id = sum(1 for m in manifest if m.get("note_id"))
    with_img = sum(1 for m in manifest if m.get("image_path") and pathlib.Path(m["image_path"]).exists())
    print(f"  note_idあり: {with_id}本")
    print(f"  画像あり: {with_img}本")
    missing_img = [m for m in manifest if m.get("note_id") and m.get("image_path") and not pathlib.Path(m["image_path"]).exists()]
    if missing_img:
        print(f"  画像欠損: {len(missing_img)}本")
        for m in missing_img:
            print(f"    {m['sheet_no']} | {m['title'][:30]} | {m['image_path']}")


def cmd_publish(args):
    """新規記事を予約投稿する。"""
    md_path = pathlib.Path(args.file)
    image_path = pathlib.Path(args.image) if args.image else None
    title, body = ops.load_article(md_path)
    tags = ops.NOTE_TAGS + (args.tags or [])

    print(f"タイトル: {title[:40]}")
    print(f"予約: {args.schedule}")

    pw, context, page = ops.launch()
    try:
        page.goto("https://note.com/new")
        page.wait_for_load_state("networkidle")
        time.sleep(3)
        ops.dismiss_modals(page)

        if image_path and image_path.exists():
            ops.upload_header_image(page, image_path)
            print("  画像アップロード完了")

        ops.fill_editor(page, title, body)
        print("  本文入力完了")

        # 下書き保存でエディタ状態を確定してから公開設定へ
        save_btn = page.wait_for_selector(
            'button:has-text("下書き保存"), button:has-text("一時保存")', timeout=10000)
        save_btn.click()
        time.sleep(3)
        ops.go_to_publish(page)

        ops.set_tags(page, tags)
        ops.add_to_magazine(page)
        ops.go_to_detail_settings(page)
        ops.set_schedule(page, args.schedule)
        print(f"  予約設定完了: {args.schedule}")
        ops.finalize(page)
        print("  予約投稿完了")
        ops.log_result("new", "publish", ops.RESULT_SUCCESS, extra={"title": title})
    except Exception as e:
        print(f"  [エラー] {e}")
        ops.take_debug_snapshot(page, "publish")
        ops.log_result("new", "publish", ops.RESULT_ERROR, error_message=str(e))
    finally:
        ops.close(pw, context)


def cmd_replace_images(args):
    """ヘッダー画像を一括差し替えする。"""
    manifest = ops.load_manifest()
    if not manifest:
        print("manifestがありません。先に sync-manifest を実行してください。")
        return

    targets = _manifest_targets(manifest, args.resume)
    # 画像パスがある記事のみ対象
    targets = [t for t in targets if t.get("image_path") and t.get("note_id")]
    if args.limit:
        targets = targets[:args.limit]

    def process(page, item):
        ops.open_editor(page, item["note_id"])
        img = pathlib.Path(item["image_path"])
        if not img.exists():
            print(f"    [スキップ] 画像なし: {img}")
            return False
        if not ops.replace_header_image(page, img):
            return False
        # 検証
        state = ops.verify_article_state(page)
        if not state["ok"]:
            print(f"    [検証失敗] {state['errors']}")
            return False
        return ops.save_article(page)

    pw, context, page = ops.launch()
    try:
        _run_batch(page, targets, "replace-images", manifest, process,
                   dry_run=args.dry_run, fail_fast=args.fail_fast)
    finally:
        ops.close(pw, context)


def cmd_rewrite_body(args):
    """記事の本文を全文再投入する。"""
    md_path = pathlib.Path(args.file)
    pw, context, page = ops.launch()
    try:
        ops.open_editor(page, args.note_id)
        if ops.rewrite_body(page, md_path):
            state = ops.verify_article_state(page)
            if state["ok"]:
                if ops.save_article(page):
                    print("保存完了")
                    ops.log_result(args.note_id, "rewrite-body", ops.RESULT_SUCCESS)
                else:
                    print("[エラー] 保存失敗")
                    ops.log_result(args.note_id, "rewrite-body", ops.RESULT_FAILED)
            else:
                print(f"[検証失敗] {state['errors']}")
                ops.take_debug_snapshot(page, f"rewrite_{args.note_id}")
        else:
            print("[エラー] 本文再投入失敗")
            ops.log_result(args.note_id, "rewrite-body", ops.RESULT_FAILED)
    finally:
        ops.close(pw, context)


def cmd_fix_link_cards(args):
    """リンクカードを修正する（本文全再投入方式）。"""
    manifest = ops.load_manifest()
    targets = _manifest_targets(manifest, args.resume)
    targets = [t for t in targets if t.get("note_id") and t.get("md_path")]
    if args.limit:
        targets = targets[:args.limit]

    def process(page, item):
        ops.open_editor(page, item["note_id"])
        md_path = pathlib.Path(item["md_path"])
        if not md_path.exists():
            print(f"    [スキップ] mdなし: {md_path}")
            return False
        if not ops.rewrite_body(page, md_path):
            return False
        return ops.save_article(page)

    pw, context, page = ops.launch()
    try:
        _run_batch(page, targets, "fix-link-cards", manifest, process,
                   dry_run=args.dry_run, fail_fast=args.fail_fast)
    finally:
        ops.close(pw, context)


def cmd_reschedule(args):
    """予約日時を変更する。"""
    pw, context, page = ops.launch()
    try:
        ops.open_editor(page, args.note_id)
        ops.go_to_publish(page)
        ops.go_to_detail_settings(page)
        ops.set_schedule(page, args.schedule)
        print(f"  日時変更: {args.schedule}")
        ops.finalize(page)
        print("  予約投稿完了")
        ops.log_result(args.note_id, "reschedule", ops.RESULT_SUCCESS,
                       extra={"schedule": args.schedule})
    except Exception as e:
        print(f"  [エラー] {e}")
        ops.take_debug_snapshot(page, f"reschedule_{args.note_id}")
        ops.log_result(args.note_id, "reschedule", ops.RESULT_ERROR, error_message=str(e))
    finally:
        ops.close(pw, context)


def cmd_discard_draft(args):
    """下書きを破棄する。"""
    pw, context, page = ops.launch()
    try:
        ops.open_editor(page, args.note_id)
        if ops.save_article(page):
            print("下書き破棄+保存完了")
            ops.log_result(args.note_id, "discard-draft", ops.RESULT_SUCCESS)
        else:
            print("[エラー] 保存失敗")
    finally:
        ops.close(pw, context)


def cmd_publish_queue(args):
    """note_publish_queue.json の記事を一括予約投稿する。"""
    queue_path = SCRIPT_DIR / "note_publish_queue.json"
    if not queue_path.exists():
        print("note_publish_queue.json がありません")
        print("先に note_schedule_mixer.py plan --write を実行してください")
        return

    queue = json.loads(queue_path.read_text(encoding="utf-8"))

    # フィルタ
    if args.failed_only:
        targets = [q for q in queue if q.get("status") == "failed"]
        print(f"失敗分リトライ: {len(targets)}本")
    else:
        targets = [q for q in queue if q.get("status") == "planned"]
        print(f"計画済み: {len(targets)}本")

    if args.limit:
        targets = targets[:args.limit]
        print(f"  --limit {args.limit} → {len(targets)}本に制限")

    if not targets:
        print("対象記事がありません")
        return

    if args.dry_run:
        print(f"\n[プレビュー] 以下の {len(targets)} 本を投稿します:")
        for i, t in enumerate(targets, 1):
            print(f"  {i}. [{t['category']:8s}] {t['schedule_at']} {t['title'][:40]}")
        return

    # manifest を読み込み（成功時に反映するため）
    manifest_path = SCRIPT_DIR / "note_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_by_no = {m["sheet_no"]: m for m in manifest}

    pw, context, page = ops.launch()
    success = fail = 0
    try:
        for i, entry in enumerate(targets, 1):
            title_short = entry["title"][:35]
            print(f"\n{'=' * 50}")
            print(f"  [{i}/{len(targets)}] {title_short}")
            print(f"  カテゴリ: {entry['category']} / 予約: {entry['schedule_at']}")
            print(f"{'=' * 50}")

            md_path = pathlib.Path(entry["md_path"])
            image_path = pathlib.Path(entry["image_path"]) if entry.get("image_path") else None

            if not md_path.exists():
                print(f"  [スキップ] MDファイルなし: {md_path}")
                entry["status"] = "failed"
                entry["last_step"] = "file_check"
                entry["last_error"] = f"MDファイルなし: {md_path}"
                entry["attempts"] = entry.get("attempts", 0) + 1
                fail += 1
                _save_queue(queue_path, queue)
                continue

            entry["status"] = "processing"
            entry["attempts"] = entry.get("attempts", 0) + 1
            _save_queue(queue_path, queue)

            try:
                title, body = ops.load_article(md_path)

                entry["last_step"] = "open_editor"
                page.goto("https://note.com/new")
                page.wait_for_load_state("networkidle")
                time.sleep(3)
                ops.dismiss_modals(page)

                # 画像アップロード
                entry["last_step"] = "upload_image"
                if image_path and image_path.exists():
                    ops.upload_header_image(page, image_path)
                    print("  画像アップロード完了")

                # 本文入力
                entry["last_step"] = "fill_editor"
                ops.fill_editor(page, title, body)
                print("  本文入力完了")

                # 下書き保存
                entry["last_step"] = "draft_save"
                save_btn = page.wait_for_selector(
                    'button:has-text("下書き保存"), button:has-text("一時保存")',
                    timeout=10000,
                )
                save_btn.click()
                time.sleep(3)

                # 公開設定
                entry["last_step"] = "go_to_publish"
                ops.go_to_publish(page)

                # タグ設定
                entry["last_step"] = "set_tags"
                tags = entry.get("tags") or ops.NOTE_TAGS
                ops.set_tags(page, tags)

                # マガジン追加
                entry["last_step"] = "add_to_magazine"
                magazine = entry.get("magazine")
                ops.add_to_magazine(page, magazine)

                # 予約日時設定
                entry["last_step"] = "set_schedule"
                ops.go_to_detail_settings(page)
                ops.set_schedule(page, entry["schedule_at"])
                print(f"  予約設定完了: {entry['schedule_at']}")

                # 確定
                entry["last_step"] = "finalize"
                ops.finalize(page)
                print("  予約投稿完了 ✅")

                entry["status"] = "scheduled"
                entry["last_error"] = None
                success += 1
                ops.log_result(
                    f"queue_{entry['sheet_no']}", "publish-queue",
                    ops.RESULT_SUCCESS, extra={"title": title},
                )

                # manifest に反映（note_key は投稿後に collect-ids で取得）
                m = manifest_by_no.get(entry["sheet_no"])
                if m:
                    m["scheduled_at"] = entry["schedule_at"]

            except Exception as e:
                print(f"  [エラー] {e}")
                ops.take_debug_snapshot(page, f"publish_queue_{entry['sheet_no']}")
                entry["status"] = "failed"
                entry["last_error"] = str(e)[:200]
                fail += 1
                ops.log_result(
                    f"queue_{entry['sheet_no']}", "publish-queue",
                    ops.RESULT_ERROR, error_message=str(e),
                )

            # 都度保存（途中停止に備える）
            _save_queue(queue_path, queue)
            time.sleep(2)

    finally:
        ops.close(pw, context)

    # manifest を保存
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"\n{'=' * 50}")
    print(f"  完了: 成功 {success}, 失敗 {fail}")
    print(f"{'=' * 50}")


def _save_queue(path: pathlib.Path, queue: list[dict]):
    """キューファイルを保存する。"""
    path.write_text(
        json.dumps(queue, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def cmd_inspect(args):
    """記事を開いて状態を確認する。"""
    pw, context, page = ops.launch()
    try:
        ops.open_editor(page, args.note_id)
        state = ops.verify_article_state(page)
        print(f"  タイトル: {state['title_len']}文字")
        print(f"  本文: {state['body_len']}文字")
        print(f"  カード: {state['cards']}個")
        print(f"  画像: {'あり' if state['has_image'] else 'なし'}")
        if state["errors"]:
            print(f"  エラー: {state['errors']}")
        else:
            print(f"  状態: OK")

        print("\nブラウザで確認してください。閉じると終了します。")
        try:
            context.pages[0].wait_for_event("close", timeout=0)
        except Exception:
            pass
    finally:
        ops.close(pw, context)


# ── CLI ──

def main():
    parser = argparse.ArgumentParser(description="note記事管理ツール")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("collect-ids", help="全記事のIDを収集")
    sub.add_parser("sync-manifest", help="note管理シートからmanifestを同期")

    p = sub.add_parser("publish", help="新規記事を予約投稿")
    p.add_argument("--file", required=True)
    p.add_argument("--image")
    p.add_argument("--schedule", required=True)
    p.add_argument("--tags", nargs="*", default=[])

    p = sub.add_parser("replace-images", help="ヘッダー画像を一括差し替え")
    p.add_argument("--limit", type=int)
    p.add_argument("--resume", action="store_true", help="成功済みをスキップ")
    p.add_argument("--dry-run", action="store_true", help="対象確認のみ")
    p.add_argument("--fail-fast", action="store_true", help="1件失敗で停止")

    p = sub.add_parser("rewrite-body", help="記事の本文を全文再投入")
    p.add_argument("--note-id", required=True)
    p.add_argument("--file", required=True)

    p = sub.add_parser("fix-link-cards", help="リンクカードを修正")
    p.add_argument("--limit", type=int)
    p.add_argument("--resume", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--fail-fast", action="store_true")

    p = sub.add_parser("reschedule", help="予約日時を変更")
    p.add_argument("--note-id", required=True)
    p.add_argument("--schedule", required=True)

    p = sub.add_parser("discard-draft", help="下書きを破棄")
    p.add_argument("--note-id", required=True)

    p = sub.add_parser("publish-queue", help="note_publish_queue.json の記事を一括予約投稿")
    p.add_argument("--limit", type=int, help="最大処理本数")
    p.add_argument("--failed-only", action="store_true", help="失敗したものだけリトライ")
    p.add_argument("--dry-run", action="store_true", help="対象確認のみ")

    p = sub.add_parser("inspect", help="記事を開いて手動確認")
    p.add_argument("--note-id", required=True)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    cmd_map = {
        "collect-ids": cmd_collect_ids,
        "sync-manifest": cmd_sync_manifest,
        "publish": cmd_publish,
        "publish-queue": cmd_publish_queue,
        "replace-images": cmd_replace_images,
        "rewrite-body": cmd_rewrite_body,
        "fix-link-cards": cmd_fix_link_cards,
        "reschedule": cmd_reschedule,
        "discard-draft": cmd_discard_draft,
        "inspect": cmd_inspect,
    }
    cmd_map[args.command](args)


if __name__ == "__main__":
    main()
