"""
note_tool.py — note記事管理の唯一のCLI入口。

使い方:
    python note_tool.py collect-ids
    python note_tool.py publish --file note_articles/xxx.md --image note_images/xxx.png --schedule "2026-04-01 12:30"
    python note_tool.py replace-images --manifest image_manifest.json [--limit 5] [--all]
    python note_tool.py rewrite-body --note-id nXXX --file note_articles/xxx.md
    python note_tool.py fix-link-cards --manifest image_manifest.json [--limit 5] [--all]
    python note_tool.py reschedule --note-id nXXX --schedule "2026-04-01 12:30"
    python note_tool.py discard-drafts --note-id nXXX
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


# ── サブコマンド実装 ──

def cmd_collect_ids(args):
    """APIから全記事のIDを収集してJSONに保存する。"""
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

        # 下書き保存 → 公開に進む
        save_btn = page.wait_for_selector(
            'button:has-text("下書き保存"), button:has-text("一時保存")', timeout=10000
        )
        save_btn.click()
        time.sleep(3)
        page.wait_for_selector(ops.SEL["publish_nav"], timeout=10000).click()
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        print("  公開設定画面へ遷移")

        ops.set_tags(page, tags)
        print(f"  タグ設定完了（{len(tags)}個）")

        ops.add_to_magazine(page)
        print("  マガジン追加完了")

        ops.go_to_detail_settings(page)
        ops.set_schedule(page, args.schedule)
        print(f"  予約設定完了: {args.schedule}")

        ops.finalize(page)
        print("  予約投稿完了")
    finally:
        ops.close(pw, context)


def cmd_replace_images(args):
    """ヘッダー画像を一括差し替えする。"""
    manifest = _load_manifest(args.manifest)
    targets = [m for m in manifest if not m.get("done")]

    if args.limit:
        targets = targets[:args.limit]

    print(f"manifest: {len(manifest)}本, 未処理: {len(targets)}本")
    if not targets:
        print("全件処理済みです。")
        return

    pw, context, page = ops.launch()
    success = fail = 0
    try:
        for i, item in enumerate(targets, 1):
            title = item.get("title", "")[:35]
            print(f"\n[{i}/{len(targets)}] {title}")
            print(f"  ID: {item['note_id']} | 画像: {pathlib.Path(item['image_path']).name}")

            ops.open_editor(page, item["note_id"])

            img = pathlib.Path(item["image_path"])
            if ops.replace_header_image(page, img):
                if ops.save_article(page):
                    item["done"] = True
                    _save_manifest(args.manifest, manifest)
                    success += 1
                    print(f"  保存完了")
                else:
                    fail += 1
                    print(f"  [エラー] 保存失敗")
            else:
                fail += 1

            time.sleep(2)

        print(f"\n完了: 成功{success}, 失敗{fail}")
    finally:
        ops.close(pw, context)


def cmd_rewrite_body(args):
    """記事の本文を全文再投入する。"""
    md_path = pathlib.Path(args.file)

    pw, context, page = ops.launch()
    try:
        print(f"記事を開いています: {args.note_id}")
        ops.open_editor(page, args.note_id)

        if ops.rewrite_body(page, md_path):
            if ops.save_article(page):
                print("保存完了")
            else:
                print("[エラー] 保存失敗")
        else:
            print("[エラー] 本文再投入失敗")
    finally:
        ops.close(pw, context)


def cmd_fix_link_cards(args):
    """リンクカードを修正する（本文全再投入方式）。"""
    manifest = _load_manifest(args.manifest)
    targets = [m for m in manifest if not m.get("done")]

    if args.limit:
        targets = targets[:args.limit]

    print(f"manifest: {len(manifest)}本, 未処理: {len(targets)}本")

    pw, context, page = ops.launch()
    success = fail = 0
    try:
        for i, item in enumerate(targets, 1):
            title = item.get("title", "")[:35]
            print(f"\n[{i}/{len(targets)}] {title}")

            md_path = pathlib.Path(item.get("md_path", ""))
            if not md_path.exists():
                print(f"  [スキップ] mdファイルなし: {md_path}")
                continue

            ops.open_editor(page, item["note_id"])
            if ops.rewrite_body(page, md_path):
                if ops.save_article(page):
                    item["done"] = True
                    _save_manifest(args.manifest, manifest)
                    success += 1
                    print(f"  保存完了")
                else:
                    fail += 1
            else:
                fail += 1
            time.sleep(2)

        print(f"\n完了: 成功{success}, 失敗{fail}")
    finally:
        ops.close(pw, context)


def cmd_reschedule(args):
    """予約日時を変更する。"""
    pw, context, page = ops.launch()
    try:
        print(f"記事を開いています: {args.note_id}")
        ops.open_editor(page, args.note_id)

        page.keyboard.press("Escape")
        time.sleep(1)
        page.wait_for_selector(ops.SEL["publish_nav"], timeout=10000).click()
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        ops.go_to_detail_settings(page)
        ops.set_schedule(page, args.schedule)
        print(f"  日時変更: {args.schedule}")

        ops.finalize(page)
        print("  予約投稿完了")
    finally:
        ops.close(pw, context)


def cmd_discard_drafts(args):
    """下書きを破棄して公開時点の記事に戻す。"""
    pw, context, page = ops.launch()
    try:
        print(f"記事を開いています: {args.note_id}")
        ops.open_editor(page, args.note_id)
        # open_editor内でhandle_draft_dialogが処理済み
        # 保存して確定
        if ops.save_article(page):
            print("下書き破棄+保存完了")
        else:
            print("[エラー] 保存失敗")
    finally:
        ops.close(pw, context)


def cmd_inspect(args):
    """記事の編集画面を開いて手動確認する。"""
    pw, context, page = ops.launch()
    try:
        print(f"記事を開いています: {args.note_id}")
        ops.open_editor(page, args.note_id)

        body = page.locator(ops.SEL["body"])
        text = body.inner_text().strip() if body.count() > 0 else ""
        cards = ops.count_embed_cards(page)
        print(f"  本文: {len(text)}文字")
        print(f"  カード: {cards}個")
        print(f"  先頭: {text[:50]}...")

        print("\nブラウザで確認してください。閉じると終了します。")
        try:
            context.pages[0].wait_for_event("close", timeout=0)
        except Exception:
            pass
    finally:
        context.close()
        pw.stop()


# ── manifest操作 ──

def _load_manifest(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_manifest(path: str, data: list[dict]):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── CLI ──

def main():
    parser = argparse.ArgumentParser(description="note記事管理ツール")
    sub = parser.add_subparsers(dest="command")

    # collect-ids
    sub.add_parser("collect-ids", help="全記事のIDを収集")

    # publish
    p = sub.add_parser("publish", help="新規記事を予約投稿")
    p.add_argument("--file", required=True)
    p.add_argument("--image")
    p.add_argument("--schedule", required=True)
    p.add_argument("--tags", nargs="*", default=[])

    # replace-images
    p = sub.add_parser("replace-images", help="ヘッダー画像を一括差し替え")
    p.add_argument("--manifest", default="image_manifest.json")
    p.add_argument("--limit", type=int)
    p.add_argument("--all", action="store_true")

    # rewrite-body
    p = sub.add_parser("rewrite-body", help="記事の本文を全文再投入")
    p.add_argument("--note-id", required=True)
    p.add_argument("--file", required=True)

    # fix-link-cards
    p = sub.add_parser("fix-link-cards", help="リンクカードを修正")
    p.add_argument("--manifest", default="image_manifest.json")
    p.add_argument("--limit", type=int)
    p.add_argument("--all", action="store_true")

    # reschedule
    p = sub.add_parser("reschedule", help="予約日時を変更")
    p.add_argument("--note-id", required=True)
    p.add_argument("--schedule", required=True)

    # discard-drafts
    p = sub.add_parser("discard-drafts", help="下書きを破棄")
    p.add_argument("--note-id", required=True)

    # inspect
    p = sub.add_parser("inspect", help="記事を開いて手動確認")
    p.add_argument("--note-id", required=True)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    cmd_map = {
        "collect-ids": cmd_collect_ids,
        "publish": cmd_publish,
        "replace-images": cmd_replace_images,
        "rewrite-body": cmd_rewrite_body,
        "fix-link-cards": cmd_fix_link_cards,
        "reschedule": cmd_reschedule,
        "discard-drafts": cmd_discard_drafts,
        "inspect": cmd_inspect,
    }
    cmd_map[args.command](args)


if __name__ == "__main__":
    main()
