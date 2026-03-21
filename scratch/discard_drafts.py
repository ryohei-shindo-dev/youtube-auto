"""下書きを破棄して元の予約投稿に戻すスクリプト。
記事管理ページの「…」メニューから下書き破棄を試みる。
"""
from __future__ import annotations
import time
from note_publish import _launch_browser, _close_browser

DRAFT_IDS = ["n58f2bca424ca"]


def main():
    pw, context, page = _launch_browser(headless=False)
    try:
        # 記事管理ページを開く
        page.goto("https://note.com/notes")
        page.wait_for_load_state("networkidle")
        time.sleep(5)

        # モーダルを閉じる
        for sel in ['button[aria-label="閉じる"]', 'button:has-text("閉じる")', 'button:has-text("あとで")']:
            try:
                el = page.locator(sel)
                if el.count() > 0:
                    el.first.click(force=True)
                    time.sleep(1)
            except Exception:
                pass

        for note_id in DRAFT_IDS:
            print(f"\n=== {note_id} ===")

            # 「追加編集された未公開の下書き」テキストを持つ記事を探す
            # 記事の「…」メニューをクリック
            articles = page.locator(f'a[href*="{note_id}"]')
            if articles.count() == 0:
                print(f"  記事が見つかりません")
                continue

            # 記事行の「…」ボタンを探す
            article_row = articles.first.locator("xpath=ancestor::div[contains(@class, 'note')]/..")
            menu_btn = page.locator(f'a[href*="{note_id}"]').first.locator("xpath=../../..").locator('button:has-text("…"), button[aria-label="メニュー"]')

            if menu_btn.count() == 0:
                # 別のアプローチ: ページ上の全「…」ボタンを確認
                all_menus = page.locator('button:has-text("…")')
                print(f"  「…」ボタン: {all_menus.count()}個")

                # 直接編集画面を開いて復元を試みる
                print(f"  編集画面から復元を試みます...")
                page.goto(f"https://editor.note.com/notes/{note_id}/edit/")
                page.wait_for_load_state("networkidle")
                time.sleep(5)

                # ページ全体のHTMLをダンプして構造を確認
                body_text = page.locator("body").inner_text()
                if "下書き" in body_text:
                    print(f"  ページ内に「下書き」テキスト検出")
                    # 全ボタンのテキストを表示
                    buttons = page.locator("button")
                    for i in range(min(buttons.count(), 30)):
                        btn_text = buttons.nth(i).inner_text().strip()
                        if btn_text:
                            print(f"    ボタン: {btn_text}")

                # 右上の「…」メニューを確認
                try:
                    top_menu = page.locator('header button, nav button').filter(has_text="…")
                    if top_menu.count() == 0:
                        top_menu = page.locator('[class*="menu"] button, [class*="dots"] button, button[aria-label*="メニュー"]')
                    if top_menu.count() > 0:
                        top_menu.first.click()
                        time.sleep(1)
                        menu_items = page.locator('[role="menu"] button, [role="menuitem"], [class*="menu"] a, [class*="menu"] button')
                        for i in range(menu_items.count()):
                            print(f"    メニュー項目: {menu_items.nth(i).inner_text().strip()}")
                except Exception as e:
                    print(f"    メニュー探索失敗: {e}")

        print("\nブラウザを開いたままにします。手動で確認してください。")
        print("確認が終わったらブラウザを閉じてください。")
        try:
            context.pages[0].wait_for_event("close", timeout=0)
        except Exception:
            pass
    finally:
        context.close()
        pw.stop()


if __name__ == "__main__":
    main()
