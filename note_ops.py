"""
note_ops.py — note記事のPlaywright操作を集約した共通ライブラリ。

全セレクタ・操作手順をここに一元管理する。
note_tool.py から呼ばれる。直接実行はしない。

構成:
  A. 低レベルUI関数 — セレクタ操作・ダイアログ処理・エディタ状態管理
  B. 高レベル業務関数 — 画像差し替え・本文再投入・スケジュール変更等
  C. 検証関数 — 保存前後の状態チェック
  D. ログ・デバッグ — 実行ログ・スクリーンショット保存
  E. ユーティリティ — ファイル読み込み・manifest操作
"""
from __future__ import annotations

import json
import pathlib
import re
import time
from datetime import datetime
from typing import Optional

from playwright.sync_api import Page, BrowserContext

from note_publish import _launch_browser, _close_browser

SCRIPT_DIR = pathlib.Path(__file__).parent
IMAGES_DIR = SCRIPT_DIR / "note_images"
ARTICLES_DIR = SCRIPT_DIR / "note_articles"
LOG_DIR = SCRIPT_DIR / "note_run_logs"
MANIFEST_PATH = SCRIPT_DIR / "note_manifest.json"

# ── 定数 ──
NOTE_TAGS = ["長期投資", "積立投資", "資産形成", "投資メンタル", "NISA"]
NOTE_MAGAZINE = "こつこつ積み立てを続ける人の読みもの"
MIN_BODY_LENGTH = 200

# ── 結果定数（タイポ防止） ──
RESULT_SUCCESS = "success"
RESULT_FAILED = "failed"
RESULT_ERROR = "error"
RESULT_SKIPPED = "skipped"

# ── セレクタ一覧（変更時はここだけ修正） ──
SEL = {
    # エディタ
    "title": 'textarea[placeholder="記事タイトル"]',
    "body": 'div.ProseMirror[role="textbox"]',
    # 画像
    #   ×ボタン: 画像アップロード後に既存画像を削除するために使う。
    #   span[role="img"][aria-label="削除"] の親buttonがクリック対象。
    "img_add": 'button[aria-label="画像を追加"]',
    "img_delete": 'span[role="img"][aria-label="削除"]',
    "img_upload": 'button:has-text("画像をアップロード")',
    "img_save": '.ReactModal__Content button:has-text("保存")',
    # ナビゲーション
    "publish_nav": 'button:has-text("公開に進む")',
    "detail_tab": 'text="詳細設定"',
    # 保存ボタン
    #   予約投稿: 予約設定済みの記事で使う
    #   更新する/更新: 公開済み記事の再保存で使う
    "btn_reserve": 'button:has-text("予約投稿")',
    "btn_update": 'button:has-text("更新する"), button:has-text("更新")',
    "btn_finalize": 'button:has-text("予約投稿"), button:has-text("更新する"), button:has-text("更新")',
    # 日時ピッカー
    #   既に予約設定済みの記事では datepicker_btn に日時テキストが表示される。
    #   未設定の場合は「日時の設定」ボタンが表示される。
    "datepicker_btn": ".react-datepicker__input-container button",
    "datepicker_next": ".react-datepicker__navigation--next",
    "datepicker_prev": ".react-datepicker__navigation--previous",
    "datepicker_month": ".react-datepicker__current-month",
    # ダイアログ
    #   下書きダイアログ: 編集画面を開いたとき、下書きがあると
    #   「公開した時点の記事」「最新の下書き」の選択肢が出る。
    #   常に「公開した時点の記事」を選び、下書きを破棄する。
    "draft_published": 'label[for="target-published"]',
    "draft_edit": 'button:has-text("編集する")',
    #   複数画面ダイアログ: 別タブで同じ記事を開いていると出る。
    "multi_local": 'label[for="local-checkbox"]',
    "multi_save": 'button:has-text("保存する")',
    # リンクカード（正本: figure[data-src]。iframe[src]は補助。a[href]は使わない）
    "card_figure": 'figure[data-src*="note.com/gachiho_motive/n/"]',
    "card_iframe": 'iframe[src*="note.com/embed/notes/"]',
    # タグ
    "tag_input": 'input[placeholder="ハッシュタグを追加する"]',
    # モーダル（バッジ獲得等の予期せぬポップアップ）
    "modal_close": [
        'div[role="dialog"] button[aria-label="閉じる"]',
        'div[role="dialog"] button:has-text("閉じる")',
        'button:has-text("あとで")',
    ],
    # URL検出（本文内のURL単独行をカード変換するため）
    "url_line": re.compile(r"^https?://\S+$"),
    # カード検出（埋め込みカードの存在確認用）
    "embed_selectors": [
        "div.ProseMirror iframe",
        'div.ProseMirror [data-embed-card]',
        'div.ProseMirror .embed-card',
        'div.ProseMirror [class*="embed"]',
    ],
}


# ════════════════════════════════════════════════════
# A. 低レベルUI関数
#    セレクタ操作・ダイアログ処理・エディタ状態管理
# ════════════════════════════════════════════════════

def launch() -> tuple:
    """永続ブラウザを起動する。Returns (pw, context, page)."""
    return _launch_browser(headless=False)


def close(pw, context):
    _close_browser(pw, context, wait_for_user=False)


def dismiss_modals(page: Page):
    """バッジ獲得等の予期せぬモーダルを閉じる。
    各操作の前に呼ぶ。出なければ何もしない。
    """
    for sel in SEL["modal_close"]:
        try:
            el = page.locator(sel)
            if el.count() > 0:
                el.first.click(force=True)
                time.sleep(0.5)
        except Exception:
            pass


def handle_draft_dialog(page: Page) -> bool:
    """下書きダイアログを処理する。
    下書きが残っている記事を開くと「公開した時点の記事」「最新の下書き」の
    選択ダイアログが出る。常に「公開した時点の記事」を選んで下書きを破棄する。
    """
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
    """「複数画面で編集されています」ダイアログを処理する。
    別タブで同じ記事を開いていた場合に出現する。
    「現在の画面」を選んで「保存する」。
    """
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
    """記事の編集画面を開き、全ダイアログを処理する。
    編集操作の最初に必ず呼ぶ。
    """
    page.goto(f"https://editor.note.com/notes/{note_id}/edit/")
    page.wait_for_load_state("networkidle")
    time.sleep(5)
    dismiss_modals(page)
    handle_draft_dialog(page)
    time.sleep(1)
    handle_multi_edit_dialog(page)
    time.sleep(1)


def wait_for_editor_ready(page: Page) -> bool:
    """エディタのタイトル・本文・保存UIが揃うまで待つ。"""
    try:
        page.wait_for_selector(SEL["title"], timeout=10000)
        page.wait_for_selector(SEL["body"], timeout=10000)
        page.wait_for_selector(SEL["publish_nav"], timeout=10000)
        return True
    except Exception:
        return False


def resync_editor_state(page: Page):
    """タイトル・本文に1文字入力→削除でエディタの内部状態を再同期する。

    なぜ必要か:
    画像の削除→再アップロード後にそのまま「公開に進む」を押すと、
    noteのProseMirrorが「タイトル・本文未入力」と判定してエラーになる。
    実際の入力イベントを発生させることで、エディタの内部状態を再計算させる。
    """
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


def go_to_publish(page: Page):
    """エディタから公開設定画面へ遷移する。「下書き保存」は使わない。"""
    page.keyboard.press("Escape")
    time.sleep(2)
    page.wait_for_selector(SEL["publish_nav"], timeout=10000).click()
    page.wait_for_load_state("networkidle")
    time.sleep(3)


def go_to_detail_settings(page: Page):
    """公開設定画面で「詳細設定」タブに移動する。予約投稿の日時はここにある。"""
    try:
        tab = page.locator(SEL["detail_tab"])
        if tab.count() > 0:
            tab.click()
            time.sleep(1)
    except Exception:
        pass


def finalize(page: Page) -> bool:
    """「予約投稿」or「更新する」ボタンを押して保存を確定する。"""
    try:
        final = page.locator(SEL["btn_finalize"])
        if final.count() > 0:
            final.first.click()
            time.sleep(5)
            return True
        return False
    except Exception:
        return False


def save_article(page: Page) -> bool:
    """記事を保存する完全フロー: 公開に進む → 予約投稿/更新する。
    下書き保存は使わない（下書きが残る原因になるため）。
    """
    try:
        go_to_publish(page)
        return finalize(page)
    except Exception:
        return False


# ════════════════════════════════════════════════════
# B. 高レベル業務関数
#    画像差し替え・本文再投入・スケジュール変更等
# ════════════════════════════════════════════════════

# ── 画像 ──

def _do_image_upload(page: Page, image_path: pathlib.Path):
    """画像追加ボタン→アップロード→保存の共通処理（内部用）。"""
    page.wait_for_selector(SEL["img_add"], timeout=5000).click()
    time.sleep(1)
    with page.expect_file_chooser() as fc:
        page.click(SEL["img_upload"])
    fc.value.set_files(str(image_path))
    time.sleep(3)
    page.wait_for_selector(SEL["img_save"], timeout=5000).click()
    time.sleep(3)


def replace_header_image(page: Page, image_path: pathlib.Path) -> bool:
    """ヘッダー画像を差し替える。

    手順:
    1. 既存画像の×ボタン（aria-label="削除"）で削除
    2. 「画像を追加」ボタンで新画像をアップロード
    3. タイトル・本文に1文字入力→削除で状態を再同期
       （これをしないと「タイトル、本文を入力してください」エラーになる）
    """
    try:
        delete_btn = page.locator(SEL["img_delete"]).locator("..")
        if delete_btn.count() > 0:
            delete_btn.first.click()
            time.sleep(2)

        _do_image_upload(page, image_path)
        time.sleep(2)
        resync_editor_state(page)
        return True
    except Exception as e:
        print(f"    [エラー] 画像差し替え失敗: {e}")
        return False


def upload_header_image(page: Page, image_path: pathlib.Path) -> bool:
    """新規記事にヘッダー画像をアップロードする（既存画像なし前提）。"""
    try:
        _do_image_upload(page, image_path)
        return True
    except Exception as e:
        print(f"    [警告] 画像アップロード失敗: {e}")
        return False


# ── 本文 ──

def count_embed_cards(page: Page) -> int:
    """埋め込みカード数を返す。"""
    for sel in SEL["embed_selectors"]:
        c = page.locator(sel).count()
        if c > 0:
            return c
    return 0


def _input_body_text(page: Page, body_text: str) -> int:
    """本文テキストをエディタに入力する（内部用）。

    URL単独行は press_sequentially + Enter でカード変換をトリガーする。
    insert_text は使わない（noteのProseMirrorでカード変換が動かないため）。

    投入前に非linkableなnote URLを除去する（有料記事・予約投稿中の記事への
    リンクカードは「この記事は閲覧できません」になるため）。

    Returns: カード変換成功数
    """
    # 非linkableなURLを事前除去
    try:
        from note_workflows import validate_body_urls
        body_text, removed = validate_body_urls(body_text)
        for url in removed:
            print(f"    [除去] 非linkable URL: {url}")
    except Exception:
        pass  # note_workflows が使えない場合はチェックなしで続行

    body = page.locator(SEL["body"])
    body.click()

    card_count = 0
    for line in body_text.splitlines():
        stripped = line.strip()
        if SEL["url_line"].match(stripped):
            before = count_embed_cards(page)
            body.press_sequentially(stripped, delay=15)
            body.press("Enter")
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


def fill_editor(page: Page, title: str, body_text: str) -> int:
    """タイトルと本文をエディタに入力する（新規投稿用）。

    Returns: カード変換成功数
    """
    title_el = page.wait_for_selector(SEL["title"], timeout=10000)
    title_el.click()
    page.keyboard.type(title, delay=10)
    time.sleep(1)

    current = title_el.input_value().strip()
    if current != title:
        raise RuntimeError(f"タイトル入力未反映: {current!r}")

    return _input_body_text(page, body_text)


def rewrite_body(page: Page, md_path: pathlib.Path) -> bool:
    """記事の本文を全文再投入する。

    末尾だけの部分削除は本文全消し事故の原因になるため、
    常にCtrl+A→削除→全文再入力する方式を使う。
    """
    title, body = load_article(md_path)
    expected_urls = sum(1 for l in body.splitlines() if SEL["url_line"].match(l.strip()))

    body_el = page.locator(SEL["body"])
    original_len = len(body_el.inner_text().strip())

    if count_embed_cards(page) >= expected_urls > 0:
        print(f"    [スキップ] カード既存")
        return True

    body_el.click()
    page.keyboard.press("Meta+a")
    time.sleep(0.3)
    page.keyboard.press("Backspace")
    time.sleep(0.5)

    # 本文のみ再入力（タイトルは既存のまま。fill_editorを使うとタイトル二重入力になる）
    card_count = _input_body_text(page, body)

    new_len = len(body_el.inner_text().strip())
    if new_len < MIN_BODY_LENGTH:
        print(f"    [中断] 本文短すぎ: {new_len}文字")
        return False

    print(f"    本文再投入完了（{original_len}→{new_len}文字, カード{card_count}個）")
    return True


# ── リンクカード操作 ──

def find_card(page, note_key: str):
    """エディタ内で指定note_keyのリンクカードを探す。

    正本は figure[data-src]。見つからなければ iframe[src] で補助検索。
    a[href] は使わない（noteのカードにはaタグがない）。

    Returns:
        Locator or None
    """
    fig = page.locator(f'figure[data-src*="{note_key}"]')
    if fig.count() > 0:
        return fig.first

    iframe = page.locator(f'iframe[src*="{note_key}"]')
    if iframe.count() > 0:
        # iframeの親figureを返す
        parent_fig = iframe.first.locator("xpath=ancestor::figure")
        if parent_fig.count() > 0:
            return parent_fig.first
        return iframe.first

    return None


def delete_card(page, note_key: str) -> bool:
    """エディタ内の指定note_keyのリンクカードを削除する。"""
    card = find_card(page, note_key)
    if not card:
        return False
    card.click()
    time.sleep(0.5)
    page.keyboard.press("Backspace")
    time.sleep(0.5)
    return True


def replace_card(page, old_key: str, new_key: str) -> bool:
    """エディタ内のリンクカードを差し替える（旧カード削除→新URL入力）。

    旧カードと同じURLのテキストリンク段落も削除する。
    """
    body_loc = page.locator('div.ProseMirror[role="textbox"]')
    new_url = f"https://note.com/gachiho_motive/n/{new_key}"

    # 1. 旧カード削除
    card = find_card(page, old_key)
    if not card:
        return False
    card.click()
    time.sleep(0.5)
    page.keyboard.press("Backspace")
    time.sleep(1)

    # 2. 旧URLのテキストリンク段落も削除
    page.evaluate(
        """(key) => {
            const editor = document.querySelector('.ProseMirror[role="textbox"]');
            if (!editor) return;
            const ps = Array.from(editor.querySelectorAll('p'));
            for (const p of ps) {
                if (p.textContent.trim().includes(key)) {
                    p.remove();
                }
            }
        }""",
        old_key,
    )
    time.sleep(0.3)

    # 3. 新URL入力→カード変換
    body_loc.press_sequentially(new_url, delay=15)
    body_loc.press("Enter")
    time.sleep(3)

    return True


def cleanup_empty_paragraphs(page, max_trailing: int = 1):
    """エディタ末尾の連続空段落を制限し、カード前後の不要な空段落を削除する。"""
    page.evaluate(
        """(maxTrailing) => {
            const editor = document.querySelector('.ProseMirror[role="textbox"]');
            if (!editor) return;

            // 末尾の連続空段落を制限
            const children = Array.from(editor.children);
            let trailingEmpty = 0;
            for (let j = children.length - 1; j >= 0; j--) {
                if (children[j].tagName === 'P' && !children[j].textContent.trim()) {
                    trailingEmpty++;
                    if (trailingEmpty > maxTrailing) {
                        children[j].remove();
                    }
                } else {
                    break;
                }
            }

            // 「あわせて読みたい」前の連続空段落を1個に制限
            const allChildren = Array.from(editor.children);
            for (let j = 0; j < allChildren.length; j++) {
                if (allChildren[j].tagName === 'P' &&
                    allChildren[j].textContent.trim() === 'あわせて読みたい') {
                    let emptyBefore = 0;
                    for (let k = j - 1; k >= 0; k--) {
                        if (allChildren[k].tagName === 'P' && !allChildren[k].textContent.trim()) {
                            emptyBefore++;
                            if (emptyBefore > 1) { allChildren[k].remove(); }
                        } else { break; }
                    }
                }
            }
        }""",
        max_trailing,
    )
    time.sleep(0.3)


# ── スケジュール ──

def _parse_datepicker_month(text: str):
    """'9月 2026' or '2026年4月' → (year, month) or (None, None)"""
    m = re.search(r'(\d+)月\s*(\d{4})', text)
    if m:
        return int(m.group(2)), int(m.group(1))
    m = re.search(r'(\d{4})\s*年?\s*(\d+)月', text)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def set_schedule(page: Page, schedule_str: str):
    """予約日時を設定する。公開設定画面の詳細設定タブで使う。"""
    dt = datetime.strptime(schedule_str, "%Y-%m-%d %H:%M")

    date_btn = page.locator(SEL["datepicker_btn"])
    if date_btn.count() > 0:
        date_btn.click()
        time.sleep(1)
    else:
        page.wait_for_selector('button:has-text("日時の設定")', timeout=5000).click()
        time.sleep(1)

    try:
        month_el = page.locator(SEL["datepicker_month"])
        if month_el.count() > 0:
            # フォーマットは "4月 2026" 形式 — 前後どちらにも移動
            current_text = month_el.inner_text()
            cur_y, cur_m = _parse_datepicker_month(current_text)
            if cur_y and cur_m:
                tgt_total = dt.year * 12 + dt.month
                cur_total = cur_y * 12 + cur_m
                diff = tgt_total - cur_total
                nav = SEL["datepicker_next"] if diff > 0 else SEL["datepicker_prev"]
                for _ in range(abs(diff)):
                    page.locator(nav).click()
                    time.sleep(0.5)
    except Exception:
        pass

    page.wait_for_selector(
        f'.react-datepicker__day--0{dt.day:02d}:not(.react-datepicker__day--outside-month)',
        timeout=5000,
    ).click()
    time.sleep(0.5)

    time_str = dt.strftime("%H:%M")
    item = page.wait_for_selector(
        f'li.react-datepicker__time-list-item:text-is("{time_str}")', timeout=5000
    )
    item.scroll_into_view_if_needed()
    item.click()
    time.sleep(1)


# ── タグ・マガジン ──

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


def add_to_magazine(page: Page, magazine_name: str | None = None):
    """マガジンに追加する。"""
    name = magazine_name or NOTE_MAGAZINE
    try:
        btn = page.wait_for_selector(
            f'button:has-text("追加"):near(:text("{name}"))', timeout=5000
        )
        btn.click()
        time.sleep(1)
    except Exception as e:
        print(f"    [警告] マガジン追加失敗: {e}")


# ── ID収集 ──

def collect_note_ids(page: Page) -> list[dict]:
    """noteの記事一覧APIレスポンスから全記事のIDを収集する。

    /api/v2/note_list/contents のレスポンスを監視して data.notes から抽出する。
    """
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
    try:
        page.goto("https://note.com/dashboard")
        time.sleep(2)
        page.goto("https://note.com/notes", wait_until="networkidle")
        time.sleep(5)

        for _ in range(8):
            page.keyboard.press("End")
            time.sleep(2)
    finally:
        page.remove_listener("response", on_response)

    seen = set()
    return [n for n in collected if n["id"] not in seen and not seen.add(n["id"])]


# ════════════════════════════════════════════════════
# C. 検証関数
#    保存前後の状態チェック
# ════════════════════════════════════════════════════

def verify_article_state(page: Page, expected_cards: int = 0) -> dict:
    """エディタの現在の状態を検証する。

    Returns: {"ok": bool, "title_len": int, "body_len": int, "cards": int, "errors": list}
    """
    errors = []

    # タイトル
    title_el = page.locator(SEL["title"])
    title_len = len(title_el.input_value().strip()) if title_el.count() > 0 else 0
    if title_len == 0:
        errors.append("タイトルが空です")

    # 本文
    body_el = page.locator(SEL["body"])
    body_text = body_el.inner_text().strip() if body_el.count() > 0 else ""
    body_len = len(body_text)
    if body_len < MIN_BODY_LENGTH:
        errors.append(f"本文が短すぎます（{body_len}文字 < {MIN_BODY_LENGTH}）")

    # カード
    cards = count_embed_cards(page)
    if expected_cards > 0 and cards < expected_cards:
        errors.append(f"カード不足（{cards} < {expected_cards}）")

    # 画像
    img_delete = page.locator(SEL["img_delete"])
    has_image = img_delete.count() > 0

    return {
        "ok": len(errors) == 0,
        "title_len": title_len,
        "body_len": body_len,
        "cards": cards,
        "has_image": has_image,
        "errors": errors,
    }


# ════════════════════════════════════════════════════
# D. ログ・デバッグ
#    実行ログ・スクリーンショット保存
# ════════════════════════════════════════════════════

def _ensure_log_dir():
    LOG_DIR.mkdir(exist_ok=True)


def log_result(note_id: str, command: str, result: str,
               error_message: str = "", extra: dict = None):
    """実行結果を note_run_logs/run_log.jsonl に追記する。"""
    _ensure_log_dir()
    entry = {
        "note_id": note_id,
        "command": command,
        "result": result,
        "error_message": error_message,
        "timestamp": datetime.now().isoformat(),
    }
    if extra:
        entry.update(extra)

    log_file = LOG_DIR / "run_log.jsonl"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def take_debug_snapshot(page: Page, label: str):
    """失敗時のスクリーンショットを保存する。"""
    _ensure_log_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = LOG_DIR / f"snapshot_{label}_{ts}.png"
    try:
        page.screenshot(path=str(path))
        print(f"    スナップショット保存: {path.name}")
    except Exception:
        pass


# ════════════════════════════════════════════════════
# E. ユーティリティ
#    ファイル読み込み・manifest操作
# ════════════════════════════════════════════════════

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


# ── manifest (JSON) ──


def load_manifest(path: pathlib.Path = None) -> list[dict]:
    """note_manifest.json を読み込む。"""
    p = path or MANIFEST_PATH
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_manifest(data: list[dict], path: pathlib.Path = None):
    """note_manifest.json に書き込む。"""
    p = path or MANIFEST_PATH
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def update_manifest_row(manifest: list[dict], note_id: str,
                        action: str, result: str):
    """manifestの1行を更新する。"""
    for row in manifest:
        if row.get("note_id") == note_id:
            row["last_action"] = action
            row["last_result"] = result
            row["last_synced_at"] = datetime.now().isoformat()
            break


def build_manifest_from_sheet() -> list[dict]:
    """note管理シートからmanifestを構築する。

    sheet_no → note_id（note URL列から抽出）→ md_path → image_path の対応を作る。
    """
    import os
    from dotenv import load_dotenv
    from sheets import _get_cached_service
    load_dotenv()

    svc = _get_cached_service("sheets", "v4")
    sheet_id = os.environ["YOUTUBE_SHEET_ID"]
    result = svc.spreadsheets().values().get(
        spreadsheetId=sheet_id, range="note管理!A:J"
    ).execute()
    rows = result.get("values", [])

    from note_publish_additional import ARTICLE_SPECS

    manifest = []
    for r in rows[1:]:
        if len(r) < 5:
            continue
        no = r[0]
        title = r[5] if len(r) > 5 else r[2] if len(r) > 2 else ""
        note_url = r[8] if len(r) > 8 else ""
        status = r[4] if len(r) > 4 else ""

        note_id = ""
        if note_url and "note.com" in note_url:
            m = re.search(r"/n/(n[a-f0-9]+)", note_url)
            if m:
                note_id = m.group(1)

        # 画像パス特定（sheet_noベース）
        no_int = int(no) if no.isdigit() else 0
        image_path = ""
        md_path = ""

        if 1 <= no_int <= 27:
            image_path = f"note_images/note_{no_int:02d}.png"
        elif no_int >= 57:
            ugokite_map = {57: "01", 58: "02", 59: "03", 60: "02", 61: "03",
                           62: "04", 63: "05", 64: "06"}
            if no_int in ugokite_map:
                image_path = f"note_images/note_ugokite_{ugokite_map[no_int]}.png"
        else:
            # ARTICLE_SPECSからタイトルマッチ
            for spec in ARTICLE_SPECS:
                spec_title = spec.get("title", "")
                if title and (title[:15] in spec_title or spec_title[:15] in title):
                    image_path = str(spec["image_path"])
                    break
                # ファイル名キーワードマッチ
                keywords = [w for w in re.split(r"[。、｜\s]+", title) if len(w) >= 3]
                fname = pathlib.Path(str(spec.get("article_path", ""))).stem
                if any(kw in fname for kw in keywords):
                    image_path = str(spec["image_path"])
                    break

        scheduled_at = r[7] if len(r) > 7 else ""

        manifest.append({
            "sheet_no": no,
            "note_id": note_id,
            "title": title,
            "status": status,
            "scheduled_at": scheduled_at,
            "md_path": md_path,
            "image_path": image_path,
            "last_action": "",
            "last_result": "",
            "last_synced_at": "",
        })

    return manifest
