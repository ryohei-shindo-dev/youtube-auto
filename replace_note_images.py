# [廃止予定] note_tool.py + note_ops.py に統合済み。このファイルは互換性のため残しているが、新規利用禁止。
"""
replace_note_images.py
全note記事のヘッダー画像を一括差し替えする。

image_manifest.json を読み、各記事の編集画面で画像を差し替える。

使い方:
    python replace_note_images.py --explore    # 1本でUI探索（操作せず）
    python replace_note_images.py --test       # 1本だけ差し替えテスト
    python replace_note_images.py --batch 10   # 10本ずつバッチ
    python replace_note_images.py --all        # 全件実行
"""
from __future__ import annotations

import argparse
import json
import pathlib
import time

from playwright.sync_api import Page

from note_publish import _launch_browser, _close_browser

SCRIPT_DIR = pathlib.Path(__file__).parent
MANIFEST_FILE = SCRIPT_DIR / "image_manifest.json"


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


def _handle_draft_dialog(page: Page):
    try:
        pub_label = page.locator('label[for="target-published"]')
        if pub_label.count() > 0:
            pub_label.click()
            time.sleep(1)
            edit_btn = page.locator('button:has-text("編集する")')
            if edit_btn.count() > 0:
                edit_btn.click()
                time.sleep(3)
                print("    下書きダイアログ処理済み")
    except Exception:
        pass


def _handle_multi_edit_dialog(page: Page):
    try:
        local_label = page.locator('label[for="local-checkbox"]')
        if local_label.count() > 0:
            local_label.click()
            time.sleep(1)
            save_btn = page.locator('button:has-text("保存する")')
            if save_btn.count() > 0:
                save_btn.click()
                time.sleep(3)
    except Exception:
        pass


def _explore_image_ui(page: Page, note_id: str):
    """画像差し替えUIを探索する（操作はしない）。"""
    edit_url = f"https://editor.note.com/notes/{note_id}/edit/"
    page.goto(edit_url)
    page.wait_for_load_state("networkidle")
    time.sleep(5)
    _dismiss_modals(page)
    _handle_draft_dialog(page)
    time.sleep(2)
    _handle_multi_edit_dialog(page)
    time.sleep(1)

    # 画像関連のボタン/要素を列挙
    print("\n  === 画像関連UI探索 ===")
    for sel_desc, sel in [
        ("aria-label含む画像", '[aria-label*="画像"]'),
        ("画像を追加", 'button:has-text("画像を追加")'),
        ("画像を変更", 'button:has-text("画像を変更")'),
        ("画像を編集", 'button:has-text("画像を編集")'),
        ("変更", 'button:has-text("変更")'),
        ("差し替え", 'button:has-text("差し替え")'),
        ("削除", 'button:has-text("削除")'),
        ("ヘッダー画像", '[class*="header"] button, [class*="eyecatch"] button'),
        ("input[type=file]", 'input[type="file"]'),
    ]:
        els = page.locator(sel)
        count = els.count()
        if count > 0:
            texts = []
            for i in range(min(count, 5)):
                t = els.nth(i).inner_text().strip()[:30]
                aria = els.nth(i).get_attribute("aria-label") or ""
                texts.append(f"{t} (aria={aria})" if aria else t)
            print(f"  ✓ {sel_desc}: {count}個 → {texts}")

    # ヘッダー画像エリアにホバーしてUIが出るか
    try:
        # エディタ上部の画像エリアを探す
        header_area = page.locator('[class*="eyecatch"], [class*="header-image"], [class*="cover"]')
        if header_area.count() > 0:
            header_area.first.hover()
            time.sleep(1)
            print(f"  ✓ ヘッダーエリアにホバー → 追加UIを確認中...")
            # ホバー後に出現するボタンを再探索
            for sel in ['button:has-text("変更")', 'button:has-text("画像")', '[aria-label*="画像"]']:
                els = page.locator(sel)
                if els.count() > 0:
                    print(f"    ホバー後: {sel} → {els.count()}個")
    except Exception:
        pass

    print("\n  ブラウザで手動確認してください。閉じると終了します。")


def _replace_image(page: Page, note_id: str, image_path: str) -> bool:
    """1記事のヘッダー画像を差し替える。"""
    edit_url = f"https://editor.note.com/notes/{note_id}/edit/"
    page.goto(edit_url)
    page.wait_for_load_state("networkidle")
    time.sleep(5)
    _dismiss_modals(page)
    _handle_draft_dialog(page)
    time.sleep(2)
    _handle_multi_edit_dialog(page)
    time.sleep(1)

    img_file = pathlib.Path(image_path)
    if not img_file.exists():
        print(f"    [エラー] 画像ファイルなし: {image_path}")
        return False

    try:
        # Step 1: 既存画像があれば×ボタン（aria-label="削除"）で削除
        delete_btn = page.locator('span[role="img"][aria-label="削除"]').locator("..")
        if delete_btn.count() > 0:
            delete_btn.first.click()
            time.sleep(2)
            print(f"    既存画像を削除")

        # Step 2: 「画像を追加」ボタンをクリック
        add_btn = page.wait_for_selector(
            'button[aria-label="画像を追加"]', timeout=5000
        )
        add_btn.click()
        time.sleep(1)

        # Step 3: ファイルアップロード
        with page.expect_file_chooser() as fc_info:
            page.click('button:has-text("画像をアップロード")')
        file_chooser = fc_info.value
        file_chooser.set_files(str(img_file))
        time.sleep(3)

        # Step 4: 保存ボタン（モーダル内）
        save_btn = page.wait_for_selector(
            '.ReactModal__Content button:has-text("保存")', timeout=5000
        )
        save_btn.click()
        time.sleep(5)

        print(f"    画像アップロード完了")

        # Step 5: タイトル・本文に実入力→削除で状態を再同期
        title_el = page.locator('textarea[placeholder="記事タイトル"]')
        if title_el.count() > 0:
            title_el.click()
            time.sleep(0.3)
            page.keyboard.press("End")
            page.keyboard.type(" ")
            time.sleep(0.3)
            page.keyboard.press("Backspace")
            time.sleep(0.5)

        body_el = page.locator('div.ProseMirror[role="textbox"]')
        if body_el.count() > 0:
            body_el.click()
            time.sleep(0.3)
            page.keyboard.press("End")
            page.keyboard.type(".")
            time.sleep(0.3)
            page.keyboard.press("Backspace")
            time.sleep(0.5)

        print(f"    状態再同期完了")

    except Exception as e:
        print(f"    [エラー] 画像差し替え失敗: {e}")
        return False

    return _save_article(page)


def _save_article(page: Page) -> bool:
    """記事を保存する（公開に進む→予約投稿/更新する）。"""
    try:
        page.keyboard.press("Escape")
        time.sleep(2)

        publish_nav = page.wait_for_selector('button:has-text("公開に進む")', timeout=10000)
        publish_nav.click()
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        # 「予約投稿」or「更新する」or「更新」
        final_btn = page.locator(
            'button:has-text("予約投稿"), button:has-text("更新する"), button:has-text("更新")'
        )
        if final_btn.count() > 0:
            final_btn.first.click()
            time.sleep(5)
            print(f"    保存完了")
            return True
        else:
            print(f"    [エラー] 保存ボタンが見つかりません")
            return False
    except Exception as e:
        print(f"    [エラー] 保存失敗: {e}")
        return False


def _load_manifest() -> list[dict]:
    with open(MANIFEST_FILE, encoding="utf-8") as f:
        return json.load(f)


def _save_manifest(manifest: list[dict]):
    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="note記事ヘッダー画像一括差し替え")
    parser.add_argument("--explore", action="store_true", help="1本でUI探索")
    parser.add_argument("--test", action="store_true", help="1本だけテスト")
    parser.add_argument("--batch", type=int, help="N本ずつバッチ実行")
    parser.add_argument("--all", action="store_true", help="全件実行")
    args = parser.parse_args()

    manifest = _load_manifest()
    remaining = [m for m in manifest if not m["done"]]
    print(f"manifest: {len(manifest)}本, 未処理: {len(remaining)}本")

    if args.explore:
        pw, context, page = _launch_browser(headless=False)
        try:
            _explore_image_ui(page, remaining[0]["note_id"])
            try:
                context.pages[0].wait_for_event("close", timeout=0)
            except Exception:
                pass
        finally:
            context.close()
            pw.stop()
        return

    targets = remaining
    if args.test:
        targets = remaining[:1]
    elif args.batch:
        targets = remaining[:args.batch]

    print(f"実行対象: {len(targets)}本")

    pw, context, page = _launch_browser(headless=False)
    success = 0
    fail = 0

    try:
        for i, item in enumerate(targets, 1):
            print(f"\n{'=' * 50}")
            print(f"  [{i}/{len(targets)}] No.{item['no']} {item['title'][:35]}")
            print(f"  ID: {item['note_id']} | 画像: {pathlib.Path(item['image_path']).name}")
            print(f"{'=' * 50}")

            if _replace_image(page, item["note_id"], item["image_path"]):
                item["done"] = True
                _save_manifest(manifest)
                success += 1
            else:
                fail += 1

            time.sleep(2)

        print(f"\n{'=' * 50}")
        print(f"  完了: 成功{success}, 失敗{fail}")
        print(f"{'=' * 50}")

    finally:
        _close_browser(pw, context, wait_for_user=False)


if __name__ == "__main__":
    main()
