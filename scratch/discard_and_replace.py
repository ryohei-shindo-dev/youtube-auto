"""下書き破棄 → 画像差し替え（×削除→再追加→状態再同期）。"""
import time
import pathlib
from note_publish import _launch_browser, _close_browser

NOTE_ID = "nab06c9c68ffa"
IMAGE_PATH = "note_images/note_01.png"


def main():
    pw, context, page = _launch_browser(headless=False)
    try:
        # Step 1: 編集画面を開く
        print("Step 1: 編集画面を開く")
        page.goto(f"https://editor.note.com/notes/{NOTE_ID}/edit/")
        page.wait_for_load_state("networkidle")
        time.sleep(5)

        # 下書きダイアログ
        try:
            pub = page.locator('label[for="target-published"]')
            if pub.count() > 0:
                pub.click()
                time.sleep(1)
                page.locator('button:has-text("編集する")').click()
                time.sleep(3)
                print("  下書き破棄完了")
        except Exception:
            pass
        try:
            local = page.locator('label[for="local-checkbox"]')
            if local.count() > 0:
                local.click()
                time.sleep(1)
                page.locator('button:has-text("保存する")').click()
                time.sleep(3)
        except Exception:
            pass
        time.sleep(2)

        # Step 2: 既存画像を×で削除
        print("Step 2: 既存画像を削除")
        delete_btn = page.locator('span[role="img"][aria-label="削除"]').locator("..")
        if delete_btn.count() > 0:
            delete_btn.first.click()
            time.sleep(2)
            print("  削除完了")
        else:
            print("  画像なし（スキップ）")

        # Step 3: 新画像をアップロード
        print("Step 3: 新画像をアップロード")
        img_file = pathlib.Path(IMAGE_PATH)
        add_btn = page.wait_for_selector('button[aria-label="画像を追加"]', timeout=5000)
        add_btn.click()
        time.sleep(1)

        with page.expect_file_chooser() as fc_info:
            page.click('button:has-text("画像をアップロード")')
        fc_info.value.set_files(str(img_file))
        time.sleep(3)

        save_btn = page.wait_for_selector('.ReactModal__Content button:has-text("保存")', timeout=5000)
        save_btn.click()
        time.sleep(5)
        print("  アップロード完了")

        # Step 4: タイトル・本文に実入力→削除で状態を再同期
        print("Step 4: 状態再同期")
        title_el = page.locator('textarea[placeholder="記事タイトル"]')
        if title_el.count() > 0:
            title_el.click()
            time.sleep(0.3)
            page.keyboard.press("End")
            page.keyboard.type(" ")
            time.sleep(0.3)
            page.keyboard.press("Backspace")
            time.sleep(0.5)
            print("  タイトル再同期OK")

        body_el = page.locator('div.ProseMirror[role="textbox"]')
        if body_el.count() > 0:
            body_el.click()
            time.sleep(0.3)
            page.keyboard.press("End")
            page.keyboard.type(".")
            time.sleep(0.3)
            page.keyboard.press("Backspace")
            time.sleep(0.5)
            print("  本文再同期OK")

        page.keyboard.press("Escape")
        time.sleep(2)

        # Step 5: 「公開に進む」→ 保存
        print("Step 5: 保存")
        publish_nav = page.wait_for_selector('button:has-text("公開に進む")', timeout=10000)
        publish_nav.click()
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        final_btn = page.locator(
            'button:has-text("予約投稿"), button:has-text("更新する"), button:has-text("更新")'
        )
        if final_btn.count() > 0:
            final_btn.first.click()
            time.sleep(5)
            print("  保存完了!")
        else:
            print("  [エラー] 保存ボタンなし")
            try:
                context.pages[0].wait_for_event("close", timeout=0)
            except Exception:
                pass
            return

    finally:
        context.close()
        pw.stop()


if __name__ == "__main__":
    main()
