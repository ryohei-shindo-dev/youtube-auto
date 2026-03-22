# [廃止予定] note_tool.py + note_ops.py に統合済み。このファイルは互換性のため残しているが、新規利用禁止。
"""
note_manage.py
note記事の管理操作を行う汎用スクリプト。

使い方:
    # 予約日時を変更
    python note_manage.py reschedule --id nXXX --schedule "2026-04-01 12:30"

    # 下書きを破棄（公開した時点の記事に戻す）
    python note_manage.py discard-draft --id nXXX

    # 記事を全文再投入（リンクカード修正等）
    python note_manage.py rewrite --id nXXX --file note_articles/xxx.md

    # 新規記事を予約投稿
    python note_manage.py post --file note_articles/xxx.md --image note_images/xxx.png --schedule "2026-04-01 12:30"

    # 予約記事のIDリストを取得
    python note_manage.py collect-ids
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import time
from datetime import datetime

from playwright.sync_api import Page

from note_publish import _launch_browser, _close_browser
from note_ops import _parse_datepicker_month
from note_publish_additional import (
    _fill_editor, _upload_header_image, _finalize,
    _URL_LINE_RE, _EMBED_SELECTORS, _count_embed_cards,
)

SCRIPT_DIR = pathlib.Path(__file__).parent
ARTICLES_DIR = SCRIPT_DIR / "note_articles"
IMAGES_DIR = SCRIPT_DIR / "note_images"

NOTE_TAGS = ["長期投資", "積立投資", "資産形成", "投資メンタル", "NISA"]
NOTE_MAGAZINE = "こつこつ積み立てを続ける人の読みもの"

MIN_BODY_LENGTH = 200


# ── 共通ユーティリティ ──

def _dismiss_modals(page: Page):
    """noteのポップアップ・モーダルを閉じる。"""
    for sel in [
        'div[role="dialog"] button[aria-label="閉じる"]',
        'div[role="dialog"] button:has-text("閉じる")',
        'button:has-text("あとで")',
    ]:
        try:
            el = page.locator(sel)
            if el.count() > 0:
                el.first.click(force=True)
                time.sleep(0.5)
        except Exception:
            pass


def _handle_draft_dialog(page: Page) -> bool:
    """下書きダイアログ: 「公開した時点の記事」→「編集する」"""
    try:
        pub_label = page.locator('label[for="target-published"]')
        if pub_label.count() > 0:
            pub_label.click()
            time.sleep(1)
            edit_btn = page.locator('button:has-text("編集する")')
            if edit_btn.count() > 0:
                edit_btn.click()
                time.sleep(3)
                print("  下書きダイアログ: 「公開した時点の記事」→「編集する」")
                return True
    except Exception:
        pass
    return False


def _handle_multi_edit_dialog(page: Page) -> bool:
    """「複数画面で編集されています」ダイアログ: 「現在の画面」→「保存する」"""
    try:
        local_label = page.locator('label[for="local-checkbox"]')
        if local_label.count() > 0:
            local_label.click()
            time.sleep(1)
            save_btn = page.locator('button:has-text("保存する")')
            if save_btn.count() > 0:
                save_btn.click()
                time.sleep(3)
                print("  複数画面ダイアログ: 「現在の画面」→「保存する」")
                return True
    except Exception:
        pass
    return False


def _open_editor(page: Page, note_id: str):
    """記事の編集画面を開き、ダイアログを処理する。"""
    edit_url = f"https://editor.note.com/notes/{note_id}/edit/"
    page.goto(edit_url)
    page.wait_for_load_state("networkidle")
    time.sleep(5)
    _dismiss_modals(page)
    _handle_draft_dialog(page)
    time.sleep(1)
    _handle_multi_edit_dialog(page)
    time.sleep(1)


def _go_to_publish(page: Page):
    """エディタから公開設定画面へ遷移する。"""
    page.keyboard.press("Escape")
    time.sleep(1)
    publish_nav = page.wait_for_selector('button:has-text("公開に進む")', timeout=10000)
    publish_nav.click()
    page.wait_for_load_state("networkidle")
    time.sleep(3)


def _go_to_detail_settings(page: Page):
    """公開設定画面で「詳細設定」タブに移動する。"""
    try:
        detail_tab = page.locator('text="詳細設定"')
        if detail_tab.count() > 0:
            detail_tab.click()
            time.sleep(1)
    except Exception:
        pass


def _set_schedule_datetime(page: Page, schedule_str: str):
    """予約日時を設定する。カレンダーが既に表示されている前提。"""
    dt = datetime.strptime(schedule_str, "%Y-%m-%d %H:%M")

    # 日時ボタンをクリック
    date_btn = page.locator('.react-datepicker__input-container button')
    if date_btn.count() > 0:
        date_btn.click()
        time.sleep(1)
    else:
        # 未設定の場合は「日時の設定」ボタン
        schedule_btn = page.wait_for_selector('button:has-text("日時の設定")', timeout=5000)
        schedule_btn.scroll_into_view_if_needed()
        schedule_btn.click()
        time.sleep(1)

    # 月移動（前後どちらにも対応）
    try:
        current_month_el = page.locator('.react-datepicker__current-month')
        if current_month_el.count() > 0:
            current_text = current_month_el.inner_text()
            cur_y, cur_m = _parse_datepicker_month(current_text)
            if cur_y and cur_m:
                tgt_total = dt.year * 12 + dt.month
                cur_total = cur_y * 12 + cur_m
                diff = tgt_total - cur_total
                nav = '.react-datepicker__navigation--next' if diff > 0 else '.react-datepicker__navigation--previous'
                for _ in range(abs(diff)):
                    page.locator(nav).click()
                    time.sleep(0.5)
    except Exception:
        pass

    # 日付選択
    day = dt.day
    date_cell = page.wait_for_selector(
        f'.react-datepicker__day--0{day:02d}:not(.react-datepicker__day--outside-month)',
        timeout=5000,
    )
    date_cell.click()
    time.sleep(0.5)

    # 時刻選択
    time_str = dt.strftime("%H:%M")
    time_item = page.wait_for_selector(
        f'li.react-datepicker__time-list-item:text-is("{time_str}")',
        timeout=5000,
    )
    time_item.scroll_into_view_if_needed()
    time_item.click()
    time.sleep(1)


def _load_article(path: pathlib.Path) -> tuple[str, str]:
    """mdファイルからタイトルと本文を分離する。"""
    text = path.read_text(encoding="utf-8")
    title = ""
    body_lines = []
    for line in text.split("\n"):
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        else:
            body_lines.append(line)
    return title, "\n".join(body_lines).strip()


# ── コマンド実装 ──

def cmd_reschedule(page: Page, note_id: str, schedule_str: str):
    """予約日時を変更する。"""
    print(f"  予約日時変更: {note_id} → {schedule_str}")
    _open_editor(page, note_id)
    _go_to_publish(page)
    _go_to_detail_settings(page)
    _set_schedule_datetime(page, schedule_str)
    print(f"  日時設定完了: {schedule_str}")
    _finalize(page)
    print(f"  予約投稿完了")


def cmd_discard_draft(page: Page, note_id: str):
    """下書きを破棄して公開時点の記事に戻す。"""
    print(f"  下書き破棄: {note_id}")
    _open_editor(page, note_id)
    # _open_editor内で_handle_draft_dialogが処理済み
    # 公開に進む → 更新する/予約投稿で確定（変更なしで再保存）
    _go_to_publish(page)
    # 公開済み記事は「更新する」、予約中は「予約投稿」
    final_btn = page.wait_for_selector(
        'button:has-text("更新する"), button:has-text("予約投稿"), button:has-text("投稿"), button:has-text("公開")',
        timeout=5000,
    )
    final_btn.click()
    time.sleep(5)
    # 成功モーダル閉じる
    close_btn = page.locator('button:has-text("閉じる")')
    if close_btn.count() > 0 and close_btn.first.is_visible():
        close_btn.first.click()
        time.sleep(1)
    print(f"  完了")


def cmd_rewrite(page: Page, note_id: str, md_path: pathlib.Path):
    """記事の本文を全文再投入する。"""
    title, body = _load_article(md_path)
    expected_urls = sum(1 for l in body.splitlines() if _URL_LINE_RE.match(l.strip()))

    print(f"  全文再投入: {note_id}")
    print(f"  タイトル: {title[:40]}")
    _open_editor(page, note_id)

    body_el = page.locator('div.ProseMirror[role="textbox"]')
    original_length = len(body_el.inner_text().strip())

    # 既にカードが十分あるかチェック
    existing_cards = _count_embed_cards(page)
    if existing_cards >= expected_urls and expected_urls > 0:
        print(f"  [スキップ] 既にカード{existing_cards}個（期待{expected_urls}個）")
        return

    # 全選択→削除→再投入
    body_el.click()
    page.keyboard.press("Meta+a")
    time.sleep(0.3)
    page.keyboard.press("Backspace")
    time.sleep(0.5)
    _fill_editor(page, title, body)

    # 検証
    new_text = body_el.inner_text().strip()
    new_cards = _count_embed_cards(page)
    print(f"  検証: {original_length}→{len(new_text)}文字, カード{new_cards}個")

    if len(new_text) < MIN_BODY_LENGTH:
        print(f"  [中断] 本文が短すぎます（{len(new_text)}文字）")
        return

    _go_to_publish(page)
    _finalize(page)
    print(f"  完了")


def cmd_post(page: Page, md_path: pathlib.Path, image_path: pathlib.Path | None,
             schedule_str: str, extra_tags: list[str] | None = None):
    """新規記事を予約投稿する。"""
    title, body = _load_article(md_path)
    tags = NOTE_TAGS + (extra_tags or [])

    print(f"  新規投稿: {title[:40]}")
    print(f"  予約: {schedule_str}")

    page.goto("https://note.com/new")
    page.wait_for_load_state("networkidle")
    time.sleep(3)
    _dismiss_modals(page)

    # ヘッダー画像
    if image_path and image_path.exists():
        try:
            _upload_header_image(page, image_path)
            print(f"  画像アップロード完了")
        except Exception as e:
            print(f"  [警告] 画像アップロード失敗: {e}")

    # 本文入力
    _fill_editor(page, title, body)
    print(f"  本文入力完了")

    # 公開設定へ
    try:
        save_btn = page.wait_for_selector(
            'button:has-text("下書き保存"), button:has-text("一時保存")',
            timeout=10000,
        )
        save_btn.click()
        time.sleep(3)
        publish_nav = page.wait_for_selector('button:has-text("公開に進む")', timeout=10000)
        publish_nav.click()
        page.wait_for_load_state("networkidle")
        time.sleep(2)
    except Exception as e:
        print(f"  [エラー] 公開設定遷移失敗: {e}")
        return

    # タグ
    try:
        tag_input = page.wait_for_selector(
            'input[placeholder="ハッシュタグを追加する"]', timeout=5000)
        for tag in tags:
            tag_input.fill(tag)
            time.sleep(0.5)
            tag_input.press("Enter")
            time.sleep(0.5)
    except Exception as e:
        print(f"  [警告] タグ設定失敗: {e}")

    # マガジン
    try:
        magazine_btn = page.wait_for_selector(
            f'button:has-text("追加"):near(:text("{NOTE_MAGAZINE}"))', timeout=5000)
        magazine_btn.click()
        time.sleep(1)
    except Exception as e:
        print(f"  [警告] マガジン追加失敗: {e}")

    # 予約設定
    _go_to_detail_settings(page)
    _set_schedule_datetime(page, schedule_str)
    print(f"  予約設定完了: {schedule_str}")

    _finalize(page)
    print(f"  予約投稿完了")


def cmd_collect_ids(page: Page):
    """予約記事のIDリストをAPIレスポンスから収集する。"""
    output_file = SCRIPT_DIR / "scheduled_notes.json"
    collected = []

    def on_response(response):
        if "/api/v2/note_list/contents" in response.url and response.status == 200:
            try:
                data = response.json()
                notes = data.get("data", {}).get("contents", [])
                for n in notes:
                    if n.get("status") == "reserved":
                        collected.append({
                            "id": n.get("key", ""),
                            "title": n.get("name", ""),
                            "status": n.get("status", ""),
                            "publish_at": n.get("publish_at", ""),
                        })
            except Exception:
                pass

    page.on("response", on_response)
    page.goto("https://note.com/notes")
    page.wait_for_load_state("networkidle")
    time.sleep(5)

    # スクロールで追加読み込み
    for _ in range(5):
        page.keyboard.press("End")
        time.sleep(2)

    # 重複排除
    seen = set()
    unique = []
    for n in collected:
        if n["id"] not in seen:
            seen.add(n["id"])
            unique.append(n)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({"notes": unique}, f, ensure_ascii=False, indent=2)

    print(f"予約記事: {len(unique)}本 → {output_file}")
    for n in sorted(unique, key=lambda x: x.get("publish_at", "")):
        print(f"  {n['publish_at'][:16]} | {n['id']} | {n['title'][:35]}")


# ── メイン ──

def main():
    parser = argparse.ArgumentParser(description="note記事管理")
    sub = parser.add_subparsers(dest="command")

    # reschedule
    p_rs = sub.add_parser("reschedule", help="予約日時を変更")
    p_rs.add_argument("--id", required=True, help="note ID")
    p_rs.add_argument("--schedule", required=True, help='予約日時 (例: "2026-04-01 12:30")')

    # discard-draft
    p_dd = sub.add_parser("discard-draft", help="下書きを破棄")
    p_dd.add_argument("--id", required=True, help="note ID")

    # rewrite
    p_rw = sub.add_parser("rewrite", help="記事を全文再投入")
    p_rw.add_argument("--id", required=True, help="note ID")
    p_rw.add_argument("--file", required=True, help="mdファイルパス")

    # post
    p_po = sub.add_parser("post", help="新規記事を予約投稿")
    p_po.add_argument("--file", required=True, help="mdファイルパス")
    p_po.add_argument("--image", help="ヘッダー画像パス")
    p_po.add_argument("--schedule", required=True, help='予約日時')
    p_po.add_argument("--tags", nargs="*", default=[], help="追加タグ")

    # collect-ids
    sub.add_parser("collect-ids", help="予約記事のIDリストを取得")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    pw, context, page = _launch_browser(headless=False)
    try:
        if args.command == "reschedule":
            cmd_reschedule(page, args.id, args.schedule)
        elif args.command == "discard-draft":
            cmd_discard_draft(page, args.id)
        elif args.command == "rewrite":
            cmd_rewrite(page, args.id, pathlib.Path(args.file))
        elif args.command == "post":
            image = pathlib.Path(args.image) if args.image else None
            cmd_post(page, pathlib.Path(args.file), image, args.schedule, args.tags)
        elif args.command == "collect-ids":
            cmd_collect_ids(page)
    finally:
        _close_browser(pw, context, wait_for_user=False)


if __name__ == "__main__":
    main()
