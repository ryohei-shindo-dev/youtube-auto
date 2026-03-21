"""リンクカード変換のテスト — 下書き保存のみ。"""
from __future__ import annotations

import pathlib
import time

from note_publish import _launch_browser, _close_browser, _markdown_to_note_html
from note_publish_additional import _fill_editor, _upload_header_image

SCRIPT_DIR = pathlib.Path(__file__).parent
ARTICLES_DIR = SCRIPT_DIR / "note_articles"

SPEC = {
    "article_path": ARTICLES_DIR / "note_add_12_投資信託を増やしすぎると、安心.md",
}


def main():
    # 記事読み込み
    text = SPEC["article_path"].read_text(encoding="utf-8")
    title = ""
    body_lines = []
    for line in text.split("\n"):
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        else:
            body_lines.append(line)
    body = "\n".join(body_lines).strip()

    print(f"タイトル: {title}")
    print(f"本文: {len(body)}字")
    print(f"URL行数: {sum(1 for l in body.splitlines() if l.strip().startswith('https://'))}")
    print()
    print("下書きテスト開始。ブラウザが開きます。")
    print("カード変換を確認したら、ブラウザを閉じてください。")

    pw, context, page = _launch_browser(headless=False)
    try:
        page.goto("https://note.com/new")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        _fill_editor(page, "[テスト] " + title, body)
        print("\n本文入力完了。カード変換を確認してください。")

        # ユーザーが閉じるまで待つ
        try:
            context.pages[0].wait_for_event("close", timeout=0)
        except Exception:
            pass
    finally:
        context.close()
        pw.stop()


if __name__ == "__main__":
    main()
