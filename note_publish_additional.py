"""
note_publish_additional.py
追加したnote記事5本を投稿・予約投稿するためのワンショット用スクリプト。

使い方:
    python note_publish_additional.py --login
    python note_publish_additional.py --post-all
"""

from __future__ import annotations

import argparse
import pathlib
import time

from playwright.sync_api import Page

from note_publish import _launch_browser, _close_browser, _markdown_to_note_html

SCRIPT_DIR = pathlib.Path(__file__).parent
ARTICLES_DIR = SCRIPT_DIR / "note_articles"
IMAGES_DIR = SCRIPT_DIR / "note_images"

ARTICLE_SPECS = [
    {
        "id": "add_01",
        "title": "オルカンでいいのか揺れる夜に、思い出したいこと",
        "article_path": ARTICLES_DIR / "note_add_01_オルカンでいいのか揺れる夜.md",
        "image_path": IMAGES_DIR / "note_add_01.png",
        "schedule": None,  # 今すぐ投稿
    },
    {
        "id": "add_02",
        "title": "S&P500が遅く見えるとき、気持ちが揺れる理由",
        "article_path": ARTICLES_DIR / "note_add_02_S&P500が遅く見えるとき.md",
        "image_path": IMAGES_DIR / "note_add_02.png",
        "schedule": "2026-03-15 21:00",
    },
    {
        "id": "add_03",
        "title": "他人の爆益を見た夜に、軸が揺れるのは自然です",
        "article_path": ARTICLES_DIR / "note_add_03_他人の爆益を見た夜に軸が揺れる.md",
        "image_path": IMAGES_DIR / "note_add_03.png",
        "schedule": "2026-03-16 21:00",
    },
    {
        "id": "add_04",
        "title": "何もしないことが不安になる日に、確認したいこと",
        "article_path": ARTICLES_DIR / "note_add_04_何もしないことが不安になる日.md",
        "image_path": IMAGES_DIR / "note_add_04.png",
        "schedule": "2026-03-17 21:00",
    },
    {
        "id": "add_05",
        "title": "正しいのに退屈で続かない。その感覚の整理",
        "article_path": ARTICLES_DIR / "note_add_05_正しいのに退屈で続かない.md",
        "image_path": IMAGES_DIR / "note_add_05.png",
        "schedule": "2026-03-18 21:00",
    },
]


def _load_article(spec: dict) -> tuple[str, str, pathlib.Path]:
    text = spec["article_path"].read_text(encoding="utf-8")
    title = ""
    body_lines = []
    for line in text.split("\n"):
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        else:
            body_lines.append(line)
    body = "\n".join(body_lines).strip()
    return title, _markdown_to_note_html(body), spec["image_path"]


def _upload_header_image(page: Page, image_path: pathlib.Path):
    if not image_path.exists():
        return

    img_btn = page.wait_for_selector('button[aria-label="画像を追加"]', timeout=5000)
    img_btn.click()
    time.sleep(1)

    with page.expect_file_chooser() as fc_info:
        page.click('button:has-text("画像をアップロード")')
    fc_info.value.set_files(str(image_path))
    time.sleep(3)

    save_btn = page.wait_for_selector('.ReactModal__Content button:has-text("保存")', timeout=5000)
    save_btn.click()
    time.sleep(2)


def _fill_editor(page: Page, title: str, body_text: str):
    title_el = page.wait_for_selector('textarea[placeholder="記事タイトル"]', timeout=10000)
    title_el.click()
    page.keyboard.type(title, delay=10)
    time.sleep(1)
    current_title = title_el.input_value().strip()
    if current_title != title:
        raise RuntimeError(f"タイトル入力未反映: {current_title!r}")

    body_el = page.wait_for_selector('div.ProseMirror[role="textbox"]', timeout=10000)
    body_el.click()
    page.keyboard.insert_text(body_text)
    time.sleep(1)
    current_body = page.locator('div.ProseMirror[role="textbox"]').inner_text().strip()
    if len(current_body) < 50:
        raise RuntimeError("本文入力がnote側で確定していません")
    page.keyboard.press("Escape")
    time.sleep(0.5)


def _go_publish(page: Page):
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


def _set_schedule(page: Page, schedule_str: str):
    from datetime import datetime

    dt = datetime.strptime(schedule_str, "%Y-%m-%d %H:%M")
    schedule_btn = page.wait_for_selector('button:has-text("日時の設定")', timeout=5000)
    schedule_btn.scroll_into_view_if_needed()
    schedule_btn.click()
    time.sleep(1)

    day = dt.day
    date_cell = page.wait_for_selector(
        f'.react-datepicker__day--0{day:02d}:not(.react-datepicker__day--outside-month)',
        timeout=5000,
    )
    date_cell.click()
    time.sleep(0.5)

    time_str = dt.strftime("%H:%M")
    time_item = page.wait_for_selector(
        f'li.react-datepicker__time-list-item:text-is("{time_str}")',
        timeout=5000,
    )
    time_item.scroll_into_view_if_needed()
    time_item.click()
    time.sleep(1)


def _finalize(page: Page):
    final_btn = page.wait_for_selector(
        'button:has-text("予約投稿"), button:has-text("投稿"), button:has-text("公開")',
        timeout=5000,
    )
    final_btn.click()
    time.sleep(5)


def post_spec(page: Page, spec: dict):
    title, body_text, image_path = _load_article(spec)
    print(f"\n=== {spec['id']} {title} ===")

    page.goto("https://note.com/new")
    page.wait_for_load_state("networkidle")
    time.sleep(2)

    _upload_header_image(page, image_path)
    _fill_editor(page, title, body_text)
    _go_publish(page)

    if spec["schedule"]:
        _set_schedule(page, spec["schedule"])
        print(f"  予約設定: {spec['schedule']}")
    else:
        print("  即時投稿")

    _finalize(page)
    print(f"  完了: {page.url}")


def do_login():
    print("ブラウザを起動します。noteにログインしてください。")
    print("ログイン完了後、ブラウザを閉じてください。")
    pw, context, page = _launch_browser(headless=False)
    try:
        page.goto("https://note.com/login")
        _close_browser(pw, context, wait_for_user=True)
    except Exception:
        _close_browser(pw, context, wait_for_user=False)
        raise


def do_post_all():
    pw, context, page = _launch_browser(headless=False)
    try:
        for spec in ARTICLE_SPECS:
            post_spec(page, spec)
    finally:
        _close_browser(pw, context, wait_for_user=False)


def main():
    parser = argparse.ArgumentParser(description="追加note記事の投稿")
    parser.add_argument("--login", action="store_true", help="noteログイン用にブラウザを開く")
    parser.add_argument("--post-all", action="store_true", help="5本を投稿・予約投稿する")
    args = parser.parse_args()

    if args.login:
        do_login()
    elif args.post_all:
        do_post_all()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
