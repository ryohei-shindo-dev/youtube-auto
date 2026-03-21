"""
note_publish_ugokite.py
「動いて崩した系」1本目のnote記事を予約投稿する。
note_publish_additional.py の実績あるコードパス（post_spec）を使用。
"""
from __future__ import annotations

import pathlib

from note_publish import _launch_browser, _close_browser
from note_publish_additional import post_spec

SCRIPT_DIR = pathlib.Path(__file__).parent
ARTICLES_DIR = SCRIPT_DIR / "note_articles"
IMAGES_DIR = SCRIPT_DIR / "note_images"

SPEC = {
    "id": "ugokite_01",
    "title": "売ったら上がった。長期投資でタイミングを計りたくなるときの整理法",
    "article_path": ARTICLES_DIR / "note_ugokite_01_売ったら上がった.md",
    "image_path": IMAGES_DIR / "note_ugokite_01.png",
    "schedule": "2026-03-20 21:00",
}


def main():
    print(f"記事: {SPEC['title']}")
    print(f"予約: {SPEC['schedule']}")
    print(f"ファイル: {SPEC['article_path']}")
    print(f"画像: {SPEC['image_path']}")
    print()

    pw, context, page = _launch_browser(headless=False)
    try:
        post_spec(page, SPEC)
    finally:
        _close_browser(pw, context, wait_for_user=False)


if __name__ == "__main__":
    main()
