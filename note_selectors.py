"""
note_selectors.py
noteのエディタ・公開設定画面のセレクタを一括取得するツール。

使い方:
    # エディタ画面（note.com/new）のセレクタを取得
    python note_selectors.py --editor

    # 公開設定画面（publish）のセレクタを取得
    python note_selectors.py --publish

    # 現在開いているページのセレクタをそのまま取得
    python note_selectors.py --current
"""

from __future__ import annotations

import argparse
import json
import pathlib
import time

from playwright.sync_api import Page

from note_publish import _launch_browser, _close_browser

JS_DUMP_SELECTORS = """
() => {
    const results = {};

    // すべてのボタン
    const buttons = document.querySelectorAll('button');
    results['buttons'] = Array.from(buttons).map(b => ({
        text: b.textContent.trim().substring(0, 80),
        ariaLabel: b.getAttribute('aria-label'),
        id: b.id,
        classes: b.className.substring(0, 100),
        dataName: b.getAttribute('data-name'),
    })).filter(b => b.text || b.ariaLabel);

    // すべてのinput
    const inputs = document.querySelectorAll('input, textarea');
    results['inputs'] = Array.from(inputs).map(i => ({
        tag: i.tagName.toLowerCase(),
        type: i.type,
        placeholder: i.placeholder,
        name: i.name,
        id: i.id,
        role: i.getAttribute('role'),
        classes: i.className.substring(0, 100),
    }));

    // すべてのリンク（aタグ）
    const links = document.querySelectorAll('a');
    results['links'] = Array.from(links).map(a => ({
        text: a.textContent.trim().substring(0, 80),
        href: a.href,
        classes: a.className.substring(0, 100),
    })).filter(a => a.text);

    // role付き要素
    const roleElements = document.querySelectorAll('[role]');
    results['roleElements'] = Array.from(roleElements).map(el => ({
        tag: el.tagName.toLowerCase(),
        role: el.getAttribute('role'),
        ariaLabel: el.getAttribute('aria-label'),
        text: el.textContent.trim().substring(0, 60),
        classes: el.className.substring(0, 100),
    })).slice(0, 50);

    // react-datepicker 関連
    const datepicker = document.querySelectorAll('[class*="datepicker"]');
    results['datepicker'] = Array.from(datepicker).map(el => ({
        tag: el.tagName.toLowerCase(),
        classes: el.className.substring(0, 150),
        text: el.textContent.trim().substring(0, 60),
    })).slice(0, 20);

    // ReactModal 関連
    const modals = document.querySelectorAll('[class*="Modal"]');
    results['modals'] = Array.from(modals).map(el => ({
        tag: el.tagName.toLowerCase(),
        classes: el.className.substring(0, 150),
        childButtons: Array.from(el.querySelectorAll('button')).map(
            b => b.textContent.trim().substring(0, 40)
        ),
    })).slice(0, 10);

    return results;
}
"""


def dump_selectors(page: Page) -> dict:
    """ページ上のセレクタ情報を取得して表示する。"""
    data = page.evaluate(JS_DUMP_SELECTORS)

    print(f"\nURL: {page.url}")
    print(f"Title: {page.title()}")

    for section, items in data.items():
        if not items:
            continue
        print(f"\n{'=' * 60}")
        print(f"  {section} ({len(items)}件)")
        print(f"{'=' * 60}")
        for item in items:
            print(f"  {json.dumps(item, ensure_ascii=False)}")

    return data


def main():
    parser = argparse.ArgumentParser(description="noteセレクタ取得ツール")
    parser.add_argument("--editor", action="store_true", help="エディタ画面")
    parser.add_argument("--publish", action="store_true", help="公開設定画面")
    parser.add_argument("--current", action="store_true", help="現在のページ")
    args = parser.parse_args()

    pw, context, page = _launch_browser(headless=False)

    try:
        if args.editor:
            page.goto("https://note.com/new")
            page.wait_for_load_state("networkidle")
            time.sleep(2)
            dump_selectors(page)

        elif args.publish:
            print("公開設定画面を取得するには、先にエディタで記事を作成してください。")
            print("手動で「公開に進む」を押した後、Enterキーを押してください。")
            page.goto("https://note.com/new")
            page.wait_for_load_state("networkidle")
            input("  → 公開設定画面に遷移したらEnter: ")
            dump_selectors(page)

        elif args.current:
            print("現在のページのセレクタを取得します。")
            print("目的のページに移動してからEnterを押してください。")
            input("  → Enter: ")
            dump_selectors(page)

        _close_browser(pw, context)
    except Exception:
        _close_browser(pw, context, wait_for_user=False)
        raise


if __name__ == "__main__":
    main()
