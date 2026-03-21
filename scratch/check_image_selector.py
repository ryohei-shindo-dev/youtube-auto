"""ヘッダー画像の×ボタンのセレクタを確認するためのスクリプト。"""
import time
from note_publish import _launch_browser, _close_browser

pw, context, page = _launch_browser(headless=False)
page.goto("https://editor.note.com/notes/nab06c9c68ffa/edit/")
page.wait_for_load_state("networkidle")
time.sleep(5)

try:
    pub = page.locator('label[for="target-published"]')
    if pub.count() > 0:
        pub.click()
        time.sleep(1)
        page.locator('button:has-text("編集する")').click()
        time.sleep(3)
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

print("ブラウザが開きました。")
print("ヘッダー画像の×ボタンを右クリック→検証でHTMLを確認してください。")
print("確認できたらブラウザを閉じてください。")

try:
    context.pages[0].wait_for_event("close", timeout=0)
except Exception:
    pass
context.close()
pw.stop()
