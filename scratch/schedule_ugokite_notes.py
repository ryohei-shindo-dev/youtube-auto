"""
schedule_ugokite_notes.py
「動いて崩した系」5本の新規予約投稿 + 既存5本の日時変更を行う。

操作一覧（計10回）:
  新規5本: 記事投稿 → 予約設定
  既存5本: 編集画面 → 日時変更 → 予約投稿
"""
from __future__ import annotations

import pathlib
import re
import time
from datetime import datetime

from playwright.sync_api import Page

from note_publish import _launch_browser, _close_browser
from note_publish_additional import (
    _fill_editor, _upload_header_image, _set_schedule, _finalize,
)

SCRIPT_DIR = pathlib.Path(__file__).parent
ARTICLES_DIR = SCRIPT_DIR / "note_articles"
IMAGES_DIR = SCRIPT_DIR / "note_images"

NOTE_TAGS = ["長期投資", "積立投資", "資産形成", "投資メンタル", "NISA"]
NOTE_MAGAZINE = "こつこつ積み立てを続ける人の読みもの"

# --- 新規投稿5本 ---
NEW_ARTICLES = [
    {
        "article_path": ARTICLES_DIR / "note_ugokite_03_積立をやめたあとに相場が戻った.md",
        "image_path": IMAGES_DIR / "note_ugokite_03.png",
        "schedule": "2026-03-22 12:30",
        "extra_tags": ["積立中断"],
    },
    {
        "article_path": ARTICLES_DIR / "note_ugokite_02_下がるのを待っていたら買えなか.md",
        "image_path": IMAGES_DIR / "note_ugokite_02.png",
        "schedule": "2026-03-23 21:00",
        "extra_tags": ["タイミング投資"],
    },
    {
        "article_path": ARTICLES_DIR / "note_ugokite_04_口座を見すぎて余計な売買をして.md",
        "image_path": IMAGES_DIR / "note_ugokite_04.png",
        "schedule": "2026-03-25 12:30",
        "extra_tags": ["投資メンタル"],
    },
    {
        "article_path": ARTICLES_DIR / "note_ugokite_06_怖くなって全部売ったあと、戻れ.md",
        "image_path": IMAGES_DIR / "note_ugokite_06.png",
        "schedule": "2026-03-26 21:00",
        "extra_tags": ["狼狽売り"],
    },
    {
        "article_path": ARTICLES_DIR / "note_ugokite_05_乗り換えたら前のほうが伸びた。.md",
        "image_path": IMAGES_DIR / "note_ugokite_05.png",
        "schedule": "2026-03-28 12:30",
        "extra_tags": ["銘柄変更"],
    },
]

# --- 日時変更5本 ---
RESCHEDULE = [
    {"id": "n62f895db3407", "title": "オルカン置いていかれる", "new_schedule": "2026-03-31 12:30"},
    {"id": "nd93ee5e8ee67", "title": "40代新NISA", "new_schedule": "2026-03-31 21:00"},
    {"id": "nc44e14e1ca3d", "title": "他の投資が伸びて", "new_schedule": "2026-04-01 12:30"},
    {"id": "nf9f32a55d872", "title": "自分だけ遅い", "new_schedule": "2026-04-01 21:00"},
    {"id": "n9a18ad93cdc1", "title": "増えてる実感がない", "new_schedule": "2026-04-02 12:30"},
]


def _load_article(path: pathlib.Path) -> tuple[str, str]:
    """mdファイルからタイトルと本文を分離。"""
    text = path.read_text(encoding="utf-8")
    title = ""
    body_lines = []
    for line in text.split("\n"):
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        else:
            body_lines.append(line)
    return title, "\n".join(body_lines).strip()


def _dismiss_modals(page: Page):
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


def _post_new_article(page: Page, spec: dict) -> bool:
    """新規記事を予約投稿する。"""
    title, body = _load_article(spec["article_path"])
    tags = NOTE_TAGS + spec.get("extra_tags", [])

    print(f"    タイトル: {title[:40]}")
    print(f"    予約: {spec['schedule']}")

    # エディタを開く
    page.goto("https://note.com/new")
    page.wait_for_load_state("networkidle")
    time.sleep(3)
    _dismiss_modals(page)

    # ヘッダー画像
    if spec["image_path"].exists():
        try:
            _upload_header_image(page, spec["image_path"])
            print(f"    画像アップロード完了")
        except Exception as e:
            print(f"    [警告] 画像アップロード失敗: {e}")

    # 本文入力（カード化対応）
    _fill_editor(page, title, body)
    print(f"    本文入力完了")

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
        print(f"    公開設定画面へ遷移")
    except Exception as e:
        print(f"    [エラー] 公開設定遷移失敗: {e}")
        return False

    # タグ設定
    try:
        tag_input = page.wait_for_selector(
            'input[placeholder="ハッシュタグを追加する"]', timeout=5000
        )
        for tag in tags:
            tag_input.fill(tag)
            time.sleep(0.5)
            tag_input.press("Enter")
            time.sleep(0.5)
        print(f"    タグ設定完了（{len(tags)}個）")
    except Exception as e:
        print(f"    [警告] タグ設定失敗: {e}")

    # マガジン追加
    try:
        magazine_btn = page.wait_for_selector(
            f'button:has-text("追加"):near(:text("{NOTE_MAGAZINE}"))',
            timeout=5000,
        )
        magazine_btn.click()
        time.sleep(1)
        print(f"    マガジン追加完了")
    except Exception as e:
        print(f"    [警告] マガジン追加失敗: {e}")

    # 予約設定
    _set_schedule(page, spec["schedule"])
    print(f"    予約設定完了: {spec['schedule']}")

    # 予約投稿
    _finalize(page)
    print(f"    予約投稿完了")
    return True


def _change_schedule(page: Page, note_id: str, title: str, new_schedule: str) -> bool:
    """既存記事の予約日時を変更する。"""
    edit_url = f"https://editor.note.com/notes/{note_id}/edit/"
    page.goto(edit_url)
    page.wait_for_load_state("networkidle")
    time.sleep(3)
    _dismiss_modals(page)

    # 公開設定へ
    try:
        page.keyboard.press("Escape")
        time.sleep(1)
        publish_nav = page.wait_for_selector('button:has-text("公開に進む")', timeout=10000)
        publish_nav.click()
        page.wait_for_load_state("networkidle")
        time.sleep(2)
    except Exception as e:
        print(f"    [エラー] 公開設定遷移失敗: {e}")
        return False

    # 日時変更（既に予約設定済みなのでカレンダーが表示されている）
    _set_schedule(page, new_schedule)
    print(f"    日時変更: {new_schedule}")

    # 予約投稿で確定
    _finalize(page)
    print(f"    予約投稿完了")
    return True


def main():
    pw, context, page = _launch_browser(headless=False)
    success = 0
    fail = 0

    try:
        # --- フェーズ1: 新規5本投稿 ---
        print(f"\n{'#' * 50}")
        print(f"  フェーズ1: 新規5本の予約投稿")
        print(f"{'#' * 50}")

        for i, spec in enumerate(NEW_ARTICLES, 1):
            print(f"\n{'=' * 50}")
            print(f"  [{i}/5] 新規投稿")
            print(f"{'=' * 50}")
            if _post_new_article(page, spec):
                success += 1
            else:
                fail += 1
            time.sleep(3)

        # --- フェーズ2: 既存5本の日時変更 ---
        print(f"\n{'#' * 50}")
        print(f"  フェーズ2: 既存5本の日時変更")
        print(f"{'#' * 50}")

        for i, item in enumerate(RESCHEDULE, 1):
            print(f"\n{'=' * 50}")
            print(f"  [{i}/5] 日時変更: {item['title']}")
            print(f"  {item['id']} → {item['new_schedule']}")
            print(f"{'=' * 50}")
            if _change_schedule(page, item["id"], item["title"], item["new_schedule"]):
                success += 1
            else:
                fail += 1
            time.sleep(3)

        print(f"\n{'#' * 50}")
        print(f"  完了: 成功{success}/10, 失敗{fail}/10")
        print(f"{'#' * 50}")

    finally:
        _close_browser(pw, context, wait_for_user=False)


if __name__ == "__main__":
    main()
