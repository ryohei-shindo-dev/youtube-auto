"""
note_ops.py — note記事のPlaywright操作を集約した共通ライブラリ。

全セレクタ・操作手順をここに一元管理する。
note_tool.py から呼ばれる。直接実行はしない。
"""
from __future__ import annotations

import json
import pathlib
import re
import time
from datetime import datetime
from typing import Optional

from playwright.sync_api import Page, BrowserContext

from note_publish import _launch_browser, _close_browser, _markdown_to_note_html

SCRIPT_DIR = pathlib.Path(__file__).parent
IMAGES_DIR = SCRIPT_DIR / "note_images"
ARTICLES_DIR = SCRIPT_DIR / "note_articles"

# ── 定数 ──
NOTE_TAGS = ["長期投資", "積立投資", "資産形成", "投資メンタル", "NISA"]
NOTE_MAGAZINE = "こつこつ積み立てを続ける人の読みもの"
MIN_BODY_LENGTH = 200

# ── セレクタ一覧（変更時はここだけ修正） ──
SEL = {
    # エディタ
    "title": 'textarea[placeholder="記事タイトル"]',
    "body": 'div.ProseMirror[role="textbox"]',
    # 画像
    "img_add": 'button[aria-label="画像を追加"]',
    "img_delete": 'span[role="img"][aria-label="削除"]',
    "img_upload": 'button:has-text("画像をアップロード")',
    "img_save": '.ReactModal__Content button:has-text("保存")',
    # ナビゲーション
    "publish_nav": 'button:has-text("公開に進む")',
    "detail_tab": 'text="詳細設定"',
    # 保存
    "btn_reserve": 'button:has-text("予約投稿")',
    "btn_update": 'button:has-text("更新する"), button:has-text("更新")',
    "btn_finalize": 'button:has-text("予約投稿"), button:has-text("更新する"), button:has-text("更新")',
    # 日時
    "datepicker_btn": ".react-datepicker__input-container button",
    "datepicker_next": ".react-datepicker__navigation--next",
    "datepicker_month": ".react-datepicker__current-month",
    # ダイアログ
    "draft_published": 'label[for="target-published"]',
    "draft_edit": 'button:has-text("編集する")',
    "multi_local": 'label[for="local-checkbox"]',
    "multi_save": 'button:has-text("保存する")',
    # タグ
    "tag_input": 'input[placeholder="ハッシュタグを追加する"]',
    # モーダル
    "modal_close": [
        'div[role="dialog"] button[aria-label="閉じる"]',
        'div[role="dialog"] button:has-text("閉じる")',
        'button:has-text("あとで")',
    ],
    # URL検出
    "url_line": re.compile(r"^https?://\S+$"),
    # カード検出
    "embed_selectors": [
        "div.ProseMirror iframe",
        'div.ProseMirror [data-embed-card]',
        'div.ProseMirror .embed-card',
        'div.ProseMirror [class*="embed"]',
    ],
}


# ════════════════════════════════════════
# ブラウザ管理
# ════════════════════════════════════════

def launch() -> tuple:
    """永続ブラウザを起動する。Returns (pw, context, page)."""
    pw, context, page = _launch_browser(headless=False)
    return pw, context, page


def close(pw, context):
    _close_browser(pw, context, wait_for_user=False)


# ════════════════════════════════════════
# 共通UI操作
# ════════════════════════════════════════

def dismiss_modals(page: Page):
    """バッジ獲得等のモーダルを閉じる。"""
    for sel in SEL["modal_close"]:
        try:
            el = page.locator(sel)
            if el.count() > 0:
                el.first.click(force=True)
                time.sleep(0.5)
        except Exception:
            pass


def handle_draft_dialog(page: Page) -> bool:
    """下書きダイアログ: 「公開した時点の記事」→「編集する」"""
    try:
        pub = page.locator(SEL["draft_published"])
        if pub.count() > 0:
            pub.click()
            time.sleep(1)
            page.locator(SEL["draft_edit"]).click()
            time.sleep(3)
            return True
    except Exception:
        pass
    return False


def handle_multi_edit_dialog(page: Page) -> bool:
    """「複数画面で編集」ダイアログ: 「現在の画面」→「保存する」"""
    try:
        local = page.locator(SEL["multi_local"])
        if local.count() > 0:
            local.click()
            time.sleep(1)
            page.locator(SEL["multi_save"]).click()
            time.sleep(3)
            return True
    except Exception:
        pass
    return False


def open_editor(page: Page, note_id: str):
    """記事の編集画面を開き、ダイアログを処理する。"""
    page.goto(f"https://editor.note.com/notes/{note_id}/edit/")
    page.wait_for_load_state("networkidle")
    time.sleep(5)
    dismiss_modals(page)
    handle_draft_dialog(page)
    time.sleep(1)
    handle_multi_edit_dialog(page)
    time.sleep(1)


def resync_editor_state(page: Page):
    """タイトル・本文に1文字入力→削除でエディタの内部状態を再同期する。"""
    title_el = page.locator(SEL["title"])
    if title_el.count() > 0:
        title_el.click()
        time.sleep(0.3)
        page.keyboard.press("End")
        page.keyboard.type(" ")
        time.sleep(0.3)
        page.keyboard.press("Backspace")
        time.sleep(0.5)

    body_el = page.locator(SEL["body"])
    if body_el.count() > 0:
        body_el.click()
        time.sleep(0.3)
        page.keyboard.press("End")
        page.keyboard.type(".")
        time.sleep(0.3)
        page.keyboard.press("Backspace")
        time.sleep(0.5)


def save_article(page: Page) -> bool:
    """「公開に進む」→「予約投稿/更新する」で保存。下書き保存は使わない。"""
    try:
        page.keyboard.press("Escape")
        time.sleep(2)
        page.wait_for_selector(SEL["publish_nav"], timeout=10000).click()
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        final = page.locator(SEL["btn_finalize"])
        if final.count() > 0:
            final.first.click()
            time.sleep(5)
            return True
        return False
    except Exception:
        return False


# ════════════════════════════════════════
# 画像操作
# ════════════════════════════════════════

def replace_header_image(page: Page, image_path: pathlib.Path) -> bool:
    """ヘッダー画像を差し替える（×削除→追加→再同期）。"""
    try:
        # 既存画像の×ボタンで削除
        delete_btn = page.locator(SEL["img_delete"]).locator("..")
        if delete_btn.count() > 0:
            delete_btn.first.click()
            time.sleep(2)

        # 「画像を追加」→ アップロード
        page.wait_for_selector(SEL["img_add"], timeout=5000).click()
        time.sleep(1)

        with page.expect_file_chooser() as fc:
            page.click(SEL["img_upload"])
        fc.value.set_files(str(image_path))
        time.sleep(3)

        page.wait_for_selector(SEL["img_save"], timeout=5000).click()
        time.sleep(5)

        # 状態再同期
        resync_editor_state(page)
        return True
    except Exception as e:
        print(f"    [エラー] 画像差し替え失敗: {e}")
        return False


def upload_header_image(page: Page, image_path: pathlib.Path) -> bool:
    """新規記事にヘッダー画像をアップロードする。"""
    try:
        btn = page.wait_for_selector(SEL["img_add"], timeout=5000)
        btn.click()
        time.sleep(1)
        with page.expect_file_chooser() as fc:
            page.click(SEL["img_upload"])
        fc.value.set_files(str(image_path))
        time.sleep(3)
        page.wait_for_selector(SEL["img_save"], timeout=5000).click()
        time.sleep(2)
        return True
    except Exception as e:
        print(f"    [警告] 画像アップロード失敗: {e}")
        return False


# ════════════════════════════════════════
# 本文操作
# ════════════════════════════════════════

def count_embed_cards(page: Page) -> int:
    """埋め込みカード数を返す。"""
    for sel in SEL["embed_selectors"]:
        c = page.locator(sel).count()
        if c > 0:
            return c
    return 0


def fill_editor(page: Page, title: str, body_text: str) -> int:
    """タイトルと本文をエディタに入力する。URL行はカード変換。

    Returns: カード変換成功数
    """
    # タイトル
    title_el = page.wait_for_selector(SEL["title"], timeout=10000)
    title_el.click()
    page.keyboard.type(title, delay=10)
    time.sleep(1)

    # タイトル確認
    current = title_el.input_value().strip()
    if current != title:
        raise RuntimeError(f"タイトル入力未反映: {current!r}")

    # 本文
    body = page.locator(SEL["body"])
    body.click()

    card_count = 0
    for line in body_text.splitlines():
        stripped = line.strip()
        if SEL["url_line"].match(stripped):
            before = count_embed_cards(page)
            body.press_sequentially(stripped, delay=15)
            body.press("Enter")
            # カード変換待ち
            deadline = time.time() + 5
            while time.time() < deadline:
                if count_embed_cards(page) > before:
                    card_count += 1
                    break
                time.sleep(0.3)
            else:
                body.press("Enter")
                time.sleep(1)
        else:
            if line:
                body.press_sequentially(line, delay=3)
            body.press("Enter")

    time.sleep(1)
    body.press("Escape")
    time.sleep(0.5)
    return card_count


def rewrite_body(page: Page, md_path: pathlib.Path) -> bool:
    """記事の本文を全文再投入する。"""
    title, body = load_article(md_path)
    expected_urls = sum(1 for l in body.splitlines() if SEL["url_line"].match(l.strip()))

    body_el = page.locator(SEL["body"])
    original_len = len(body_el.inner_text().strip())

    # 既にカードが十分あるかチェック
    if count_embed_cards(page) >= expected_urls > 0:
        print(f"    [スキップ] カード既存")
        return True

    # 全選択→削除→再投入
    body_el.click()
    page.keyboard.press("Meta+a")
    time.sleep(0.3)
    page.keyboard.press("Backspace")
    time.sleep(0.5)

    card_count = fill_editor(page, title, body)

    # 検証
    new_len = len(body_el.inner_text().strip())
    if new_len < MIN_BODY_LENGTH:
        print(f"    [中断] 本文短すぎ: {new_len}文字")
        return False

    print(f"    本文再投入完了（{original_len}→{new_len}文字, カード{card_count}個）")
    return True


# ════════════════════════════════════════
# スケジュール操作
# ════════════════════════════════════════

def go_to_detail_settings(page: Page):
    """公開設定画面で「詳細設定」タブに移動する。"""
    try:
        tab = page.locator(SEL["detail_tab"])
        if tab.count() > 0:
            tab.click()
            time.sleep(1)
    except Exception:
        pass


def set_schedule(page: Page, schedule_str: str):
    """予約日時を設定する。公開設定画面の詳細設定タブで使う。"""
    dt = datetime.strptime(schedule_str, "%Y-%m-%d %H:%M")

    # 日時ピッカーを開く
    date_btn = page.locator(SEL["datepicker_btn"])
    if date_btn.count() > 0:
        date_btn.click()
        time.sleep(1)
    else:
        page.wait_for_selector('button:has-text("日時の設定")', timeout=5000).click()
        time.sleep(1)

    # 月移動
    try:
        month_el = page.locator(SEL["datepicker_month"])
        if month_el.count() > 0:
            target = f"{dt.year}年{dt.month}月"
            while target not in month_el.inner_text():
                page.locator(SEL["datepicker_next"]).click()
                time.sleep(0.5)
    except Exception:
        if dt.month == 4:
            try:
                page.locator(SEL["datepicker_next"]).click()
                time.sleep(0.5)
            except Exception:
                pass

    # 日付選択
    page.wait_for_selector(
        f'.react-datepicker__day--0{dt.day:02d}:not(.react-datepicker__day--outside-month)',
        timeout=5000,
    ).click()
    time.sleep(0.5)

    # 時刻選択
    time_str = dt.strftime("%H:%M")
    item = page.wait_for_selector(
        f'li.react-datepicker__time-list-item:text-is("{time_str}")', timeout=5000
    )
    item.scroll_into_view_if_needed()
    item.click()
    time.sleep(1)


def finalize(page: Page):
    """「予約投稿」or「更新する」ボタンを押す。"""
    final = page.wait_for_selector(SEL["btn_finalize"], timeout=5000)
    final.first.click() if hasattr(final, 'first') else final.click()
    time.sleep(5)


# ════════════════════════════════════════
# タグ・マガジン
# ════════════════════════════════════════

def set_tags(page: Page, tags: list[str]):
    """ハッシュタグを設定する。"""
    try:
        inp = page.wait_for_selector(SEL["tag_input"], timeout=5000)
        for tag in tags:
            inp.fill(tag)
            time.sleep(0.5)
            inp.press("Enter")
            time.sleep(0.5)
    except Exception as e:
        print(f"    [警告] タグ設定失敗: {e}")


def add_to_magazine(page: Page):
    """マガジンに追加する。"""
    try:
        btn = page.wait_for_selector(
            f'button:has-text("追加"):near(:text("{NOTE_MAGAZINE}"))', timeout=5000
        )
        btn.click()
        time.sleep(1)
    except Exception as e:
        print(f"    [警告] マガジン追加失敗: {e}")


# ════════════════════════════════════════
# ID収集
# ════════════════════════════════════════

def collect_note_ids(page: Page) -> list[dict]:
    """APIレスポンスから全記事のIDを収集する。"""
    collected = []

    def on_response(response):
        if "/note_list/contents" in response.url and response.status == 200:
            try:
                data = response.json()
                notes = data.get("data", {}).get("notes", [])
                for n in notes:
                    if isinstance(n, dict) and "key" in n:
                        collected.append({
                            "id": n["key"],
                            "title": n.get("name", ""),
                            "status": n.get("status", ""),
                            "publish_at": n.get("publish_at", ""),
                        })
            except Exception:
                pass

    page.on("response", on_response)
    page.goto("https://note.com/dashboard")
    time.sleep(2)
    page.goto("https://note.com/notes", wait_until="networkidle")
    time.sleep(5)

    for _ in range(8):
        page.keyboard.press("End")
        time.sleep(2)

    # 重複排除
    seen = set()
    return [n for n in collected if n["id"] not in seen and not seen.add(n["id"])]


# ════════════════════════════════════════
# ユーティリティ
# ════════════════════════════════════════

def load_article(md_path: pathlib.Path) -> tuple[str, str]:
    """mdファイルからタイトルと本文を分離する。"""
    text = md_path.read_text(encoding="utf-8")
    title = ""
    body_lines = []
    for line in text.split("\n"):
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        else:
            body_lines.append(line)
    return title, "\n".join(body_lines).strip()
