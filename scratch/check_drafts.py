"""下書きの状態を確認し、破棄する。"""
from __future__ import annotations
import time
from note_publish import _launch_browser, _close_browser

DRAFT_IDS = ["n89e9fc715f94", "n58f2bca424ca"]

def main():
    pw, context, page = _launch_browser(headless=False)
    try:
        for note_id in DRAFT_IDS:
            edit_url = f"https://editor.note.com/notes/{note_id}/edit/"
            print(f"\n=== {note_id} ===")
            page.goto(edit_url)
            page.wait_for_load_state("networkidle")
            time.sleep(5)

            # ページ全体のテキストからダイアログを探す
            page_text = page.locator("body").inner_text()

            if "下書きがあります" in page_text or "どちらを編集" in page_text:
                print("  下書きダイアログ検出!")

                # ダイアログ内の全ボタンを確認
                dialog = page.locator('div[role="dialog"], .modal-content-wrapper, [class*="modal"]')
                if dialog.count() > 0:
                    buttons = dialog.locator("button")
                    for i in range(buttons.count()):
                        print(f"  ボタン{i}: {buttons.nth(i).inner_text()}")

                # 「公開した時点の記事」を含む要素をクリック
                try:
                    pub = page.locator(':text("公開した時点の記事")')
                    if pub.count() > 0:
                        pub.first.click()
                        time.sleep(1)
                        print("  「公開した時点の記事」を選択")

                    # 「編集する」ボタンをクリック
                    edit_btn = page.locator('button:has-text("編集する")')
                    if edit_btn.count() > 0:
                        edit_btn.click()
                        time.sleep(3)
                        print("  「編集する」をクリック")

                    # 下書き保存で確定
                    save_btn = page.wait_for_selector('button:has-text("下書き保存")', timeout=5000)
                    save_btn.click()
                    time.sleep(3)
                    print("  保存完了（元の状態に復元）")
                except Exception as e:
                    print(f"  [エラー] {e}")
            else:
                print("  下書きダイアログなし")

                # エディタの本文文字数を確認
                body = page.locator('div.ProseMirror[role="textbox"]')
                if body.count() > 0:
                    text = body.inner_text().strip()
                    print(f"  本文: {len(text)}文字, 先頭: {text[:40]}...")

        print("\n完了。")
    finally:
        _close_browser(pw, context, wait_for_user=False)

if __name__ == "__main__":
    main()
