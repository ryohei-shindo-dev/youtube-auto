"""
note_publish_one.py
指定したマークダウンファイルをnoteに予約投稿するワンショットスクリプト。

使い方:
    python note_publish_one.py note_articles/note_article.md --schedule "2026-03-20 21:00"
    python note_publish_one.py note_articles/note_article.md --draft
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys
import time
from datetime import datetime
from html import escape as _html_escape

from playwright.sync_api import sync_playwright

SCRIPT_DIR = pathlib.Path(__file__).parent
USER_DATA_DIR = SCRIPT_DIR / ".note_browser"
IMAGES_DIR = SCRIPT_DIR / "note_images"

NOTE_TAGS = ["長期投資", "積立投資", "資産形成", "投資メンタル", "NISA"]
EXTRA_TAGS = ["売却", "タイミング投資", "後悔"]
NOTE_MAGAZINE = "こつこつ積み立てを続ける人の読みもの"


def _markdown_to_note_html(body: str) -> str:
    """note_publish.py と同じ変換ロジック。"""
    parts: list[str] = []
    for raw_line in body.split("\n"):
        line = raw_line.rstrip()
        if re.match(r"^-{3,}$", line.strip()):
            parts.append("<hr>")
            continue
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            heading = re.sub(r"\*\*(.+?)\*\*", r"\1", m.group(1))
            parts.append(f"<h3>{_html_escape(heading)}</h3>")
            continue
        if not line.strip():
            parts.append("<p><br></p>")
            continue
        escaped = _html_escape(line)
        text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
        parts.append(f"<p>{text}</p>")

    html = "\n".join(parts)
    empty = "<p><br></p>"
    while f"{empty}\n{empty}\n{empty}" in html:
        html = html.replace(f"{empty}\n{empty}\n{empty}", f"{empty}\n{empty}")
    return html.strip()


def main():
    parser = argparse.ArgumentParser(description="note記事を1本投稿")
    parser.add_argument("file", help="マークダウンファイルのパス")
    parser.add_argument("--schedule", help='予約日時 (例: "2026-03-20 21:00")')
    parser.add_argument("--draft", action="store_true", help="下書き保存のみ")
    parser.add_argument("--image", help="ヘッダー画像のパス（省略時は自動検索）")
    args = parser.parse_args()

    # ファイル読み込み
    article_path = pathlib.Path(args.file)
    if not article_path.exists():
        print(f"[エラー] ファイルが見つかりません: {article_path}")
        sys.exit(1)

    text = article_path.read_text(encoding="utf-8")
    title = ""
    body_lines = []
    for line in text.split("\n"):
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        else:
            body_lines.append(line)
    body = "\n".join(body_lines).strip()
    body_html = _markdown_to_note_html(body)
    tags = NOTE_TAGS + EXTRA_TAGS

    # 画像
    image_path = pathlib.Path(args.image) if args.image else None

    print(f"\n{'=' * 50}")
    print(f"  タイトル: {title}")
    print(f"  タグ: {', '.join(tags)}")
    if args.schedule:
        print(f"  予約: {args.schedule}")
    print(f"{'=' * 50}")

    # ブラウザ起動
    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        user_data_dir=str(USER_DATA_DIR),
        headless=False,
        viewport={"width": 1280, "height": 900},
        locale="ja-JP",
    )
    page = context.pages[0] if context.pages else context.new_page()

    try:
        # エディタを開く
        page.goto("https://note.com/new")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # ヘッダー画像
        if image_path and image_path.exists():
            try:
                img_btn = page.wait_for_selector(
                    'button[aria-label="画像を追加"]', timeout=5000
                )
                img_btn.click()
                time.sleep(1)
                with page.expect_file_chooser() as fc_info:
                    page.click('button:has-text("画像をアップロード")')
                file_chooser = fc_info.value
                file_chooser.set_files(str(image_path))
                time.sleep(3)
                save_btn = page.wait_for_selector(
                    '.ReactModal__Content button:has-text("保存")', timeout=5000
                )
                save_btn.click()
                time.sleep(2)
                print(f"  画像アップロード完了: {image_path.name}")
            except Exception as e:
                print(f"  [警告] 画像アップロード失敗: {e}")

        # タイトル入力
        title_el = page.wait_for_selector(
            'textarea[placeholder="記事タイトル"]', timeout=10000
        )
        title_el.click()
        page.keyboard.type(title, delay=10)
        time.sleep(0.5)
        print("  タイトル入力完了")

        # 本文入力
        body_el = page.wait_for_selector(
            'div.ProseMirror[role="textbox"]', timeout=10000
        )
        body_el.click()
        page.evaluate(
            """html => { document.execCommand('insertHTML', false, html); }""",
            body_html,
        )
        time.sleep(1)
        print("  本文入力完了")

        # 公開設定画面へ
        page.keyboard.press("Escape")
        time.sleep(1)
        publish_nav = page.wait_for_selector(
            'button:has-text("公開に進む")', timeout=10000
        )
        publish_nav.click()
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        print("  公開設定画面へ遷移")

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
            print(f"  タグ設定完了（{len(tags)}個）")
        except Exception as e:
            print(f"  [警告] タグ設定失敗: {e}")

        # マガジン追加
        try:
            magazine_btn = page.wait_for_selector(
                f'button:has-text("追加"):near(:text("{NOTE_MAGAZINE}"))',
                timeout=5000,
            )
            magazine_btn.click()
            time.sleep(1)
            print("  マガジン追加完了")
        except Exception as e:
            print(f"  [警告] マガジン追加失敗: {e}")

        # 予約投稿設定
        if args.schedule and not args.draft:
            dt = datetime.strptime(args.schedule, "%Y-%m-%d %H:%M")
            try:
                schedule_btn = page.wait_for_selector(
                    'button:has-text("日時の設定")', timeout=5000
                )
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
                print(f"  予約設定完了: {args.schedule}")
            except Exception as e:
                print(f"  [警告] 予約設定失敗: {e}")
                print(f"  手動で予約日時を設定してください: {args.schedule}")

        # 下書き / 投稿
        if args.draft:
            print("\n  下書きモード: 確認してからブラウザを閉じてください。")
            page.pause()
        else:
            # 投稿前にnote IDを取得
            editor_url = page.url
            note_id = None
            m = re.search(r"/notes/([a-zA-Z0-9]+)/", editor_url)
            if m:
                note_id = m.group(1)

            final_btn = page.wait_for_selector(
                'button:has-text("予約投稿"), button:has-text("投稿"), '
                'button:has-text("公開")',
                timeout=5000,
            )
            final_btn.click()
            time.sleep(5)
            print("  投稿実行完了")

            current_url = page.url
            if "note.com" in current_url and "/n/" in current_url:
                print(f"  URL: {current_url}")
            elif note_id:
                print(f"  URL: https://note.com/gachiho_motive/n/{note_id}")

    except Exception as e:
        print(f"\n[エラー] {e}")
        print("ブラウザを閉じてください。")
        try:
            context.pages[0].wait_for_event("close", timeout=0)
        except Exception:
            pass
    finally:
        context.close()
        pw.stop()


if __name__ == "__main__":
    main()
