"""既存5本の下書き破棄 + 予約日時変更。
スクリーンショットから確認したセレクタを使用。
"""
from __future__ import annotations
import time
from datetime import datetime
from note_publish import _launch_browser, _close_browser

RESCHEDULE = [
    {"id": "n62f895db3407", "title": "オルカン置いていかれる", "new_schedule": "2026-03-31 12:30"},
    {"id": "nd93ee5e8ee67", "title": "40代新NISA", "new_schedule": "2026-03-31 21:00"},
    {"id": "nc44e14e1ca3d", "title": "他の投資が伸びて", "new_schedule": "2026-04-01 12:30"},
    {"id": "nf9f32a55d872", "title": "自分だけ遅い", "new_schedule": "2026-04-01 21:00"},
    {"id": "n9a18ad93cdc1", "title": "増えてる実感がない", "new_schedule": "2026-04-02 12:30"},
]


def _handle_draft_dialog(page):
    """下書きダイアログを処理: 「公開した時点の記事」→「編集する」"""
    try:
        # 「公開した時点の記事」ラベルをクリック
        pub_label = page.locator('label[for="target-published"]')
        if pub_label.count() > 0:
            pub_label.click()
            time.sleep(1)
            # 「編集する」ボタン
            edit_btn = page.locator('button:has-text("編集する")')
            if edit_btn.count() > 0:
                edit_btn.click()
                time.sleep(3)
                print("    下書きダイアログ: 「公開した時点の記事」→「編集する」")
                return True
    except Exception:
        pass
    return False


def _handle_multi_edit_dialog(page):
    """「複数画面で編集されています」ダイアログ: 「現在の画面」→「保存する」"""
    try:
        local_label = page.locator('label[for="local-checkbox"]')
        if local_label.count() > 0:
            local_label.click()
            time.sleep(1)
            save_btn = page.locator('button:has-text("保存する")')
            if save_btn.count() > 0:
                save_btn.click()
                time.sleep(3)
                print("    複数画面ダイアログ: 「現在の画面」→「保存する」")
                return True
    except Exception:
        pass
    return False


def _change_schedule(page, note_id, new_schedule):
    dt = datetime.strptime(new_schedule, "%Y-%m-%d %H:%M")

    # 編集画面を開く
    edit_url = f"https://editor.note.com/notes/{note_id}/edit/"
    page.goto(edit_url)
    page.wait_for_load_state("networkidle")
    time.sleep(5)

    # 下書きダイアログ
    _handle_draft_dialog(page)
    time.sleep(2)

    # 複数画面ダイアログ
    _handle_multi_edit_dialog(page)
    time.sleep(2)

    # 「公開に進む」
    try:
        page.keyboard.press("Escape")
        time.sleep(1)
        publish_nav = page.wait_for_selector('button:has-text("公開に進む")', timeout=10000)
        publish_nav.click()
        page.wait_for_load_state("networkidle")
        time.sleep(3)
        print("    公開設定画面へ遷移")
    except Exception as e:
        print(f"    [エラー] 公開設定遷移失敗: {e}")
        return False

    # 「詳細設定」タブ
    try:
        detail_tab = page.locator('text="詳細設定"')
        if detail_tab.count() > 0:
            detail_tab.click()
            time.sleep(1)
            print("    詳細設定タブ")
    except Exception:
        pass

    # 予約日時ボタン（react-datepicker__input-container内のbutton）
    try:
        date_btn = page.locator('.react-datepicker__input-container button')
        if date_btn.count() > 0:
            date_btn.click()
            time.sleep(1)
            print("    日時ピッカーを開きました")
        else:
            print("    [エラー] 日時ボタンが見つかりません")
            return False
    except Exception as e:
        print(f"    [エラー] 日時ボタン失敗: {e}")
        return False

    # 月移動（3月→4月の場合）
    if dt.month == 4:
        try:
            next_btn = page.locator('.react-datepicker__navigation--next')
            next_btn.click()
            time.sleep(0.5)
            print("    次月へ移動")
        except Exception:
            pass

    # 日付選択
    try:
        day = dt.day
        date_cell = page.wait_for_selector(
            f'.react-datepicker__day--0{day:02d}:not(.react-datepicker__day--outside-month)',
            timeout=5000,
        )
        date_cell.click()
        time.sleep(0.5)
    except Exception as e:
        print(f"    [エラー] 日付選択失敗: {e}")
        return False

    # 時刻選択
    try:
        time_str = dt.strftime("%H:%M")
        time_item = page.wait_for_selector(
            f'li.react-datepicker__time-list-item:text-is("{time_str}")',
            timeout=5000,
        )
        time_item.scroll_into_view_if_needed()
        time_item.click()
        time.sleep(1)
    except Exception as e:
        print(f"    [エラー] 時刻選択失敗: {e}")
        return False

    print(f"    日時変更: {new_schedule}")

    # 予約投稿
    try:
        final_btn = page.wait_for_selector('button:has-text("予約投稿")', timeout=5000)
        final_btn.click()
        time.sleep(5)
        print("    予約投稿完了")
        return True
    except Exception as e:
        print(f"    [エラー] 予約投稿失敗: {e}")
        return False


def main():
    pw, context, page = _launch_browser(headless=False)
    success = 0
    try:
        for i, item in enumerate(RESCHEDULE, 1):
            print(f"\n[{i}/5] {item['title']} → {item['new_schedule']}")
            if _change_schedule(page, item["id"], item["new_schedule"]):
                success += 1
            time.sleep(2)
        print(f"\n完了: {success}/5 成功")
    finally:
        _close_browser(pw, context, wait_for_user=False)

if __name__ == "__main__":
    main()
