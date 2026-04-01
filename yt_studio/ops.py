"""YouTube Studio UI操作ライブラリ.

note/ops.py と同じパターン。セレクタはSEL辞書に一元管理し、
UI変更時はここだけ修正する。

セレクタは実際のHTMLを確認してから埋める。
"""
from __future__ import annotations

import json
import pathlib
import time
from datetime import datetime

from playwright.sync_api import Page

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent.parent
LOG_DIR = SCRIPT_DIR / "yt_studio_logs"
LOG_DIR.mkdir(exist_ok=True)

# ── セレクタ一覧 ──
SEL: dict[str, str] = {
    # 関連動画ドロップダウン（詳細ページ右サイドパネル）
    "related_video_trigger": "#linked-video-editor-link",
    # 動画選択ダイアログ
    "pick_dialog": "ytcp-video-pick-dialog",
    "pick_search": "ytcp-video-pick-dialog input#search-yours",
    "pick_card": "ytcp-video-pick-dialog ytcp-entity-card",
    "pick_close": "ytcp-video-pick-dialog #close-button, ytcp-video-pick-dialog yt-icon-button",
    # 保存
    "save_button": 'ytcp-button#save button[aria-label="保存"]',
}

# ── チャンネル設定 ──
CHANNELS: dict[str, dict] = {
    "gachiho": {
        "channel_id": "UCnPOwPO3nKHyGOH9UQJvkXQ",
        "studio_base": "https://studio.youtube.com/video",
    },
}


def open_video_details(page: Page, video_id: str, channel: str = "gachiho"):
    """YouTube Studio の動画詳細ページを開く。"""
    base = CHANNELS[channel]["studio_base"]
    url = f"{base}/{video_id}/edit"
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    # 保存ボタンが表示されるまで待つ（ページ読み込み完了の指標）
    try:
        page.wait_for_selector("#save-button", timeout=15000)
    except Exception:
        pass
    time.sleep(3)


def set_related_video(page: Page, target_title: str) -> bool:
    """関連動画を設定する。

    1. #linked-video-editor-link をクリック → 動画選択ダイアログが開く
    2. 検索欄にタイトルを入力
    3. 検索結果から aria-label で対象動画を特定してクリック
    4. ダイアログが閉じる → 保存ボタンを押す
    """
    # 1. 関連動画ドロップダウンをクリック
    trigger = page.locator(SEL["related_video_trigger"])
    trigger.click()
    time.sleep(2)

    # ダイアログが開いたか確認
    dialog = page.locator(SEL["pick_dialog"])
    if dialog.count() == 0:
        print("  [エラー] 動画選択ダイアログが開きませんでした")
        return False

    # 2. 検索欄にタイトルの一部を入力
    search_text = target_title[:20]  # 先頭20文字で検索
    search = page.locator(SEL["pick_search"])
    search.fill(search_text)
    time.sleep(2)

    # 3. 検索結果から対象動画を選択
    # aria-label にタイトルが含まれるカードの #content をクリック
    cards = page.locator(SEL["pick_card"])
    found = False
    for i in range(cards.count()):
        card = cards.nth(i)
        label = card.get_attribute("aria-label") or ""
        if target_title[:15] in label:
            # カード内の #content をクリック（外側のクリックでは選択されない場合がある）
            content = card.locator("#content")
            if content.count() > 0:
                content.click()
            else:
                card.click()
            found = True
            time.sleep(2)
            break

    if not found:
        # フォールバック: 先頭10文字で再検索
        for i in range(cards.count()):
            card = cards.nth(i)
            label = card.get_attribute("aria-label") or ""
            if target_title[:10] in label:
                card.locator("#content").click() if card.locator("#content").count() > 0 else card.click()
                found = True
                time.sleep(2)
                break

    if not found:
        print(f"  [エラー] 関連動画が見つかりません: {target_title}")
        # ダイアログを閉じる
        close_btn = page.locator(SEL["pick_close"]).first
        if close_btn.count() > 0:
            close_btn.click()
            time.sleep(1)
        return False

    # 4. 保存
    time.sleep(2)
    return save(page)


def save(page: Page) -> bool:
    """保存ボタンを押す。"""
    save_btn = page.locator(SEL["save_button"])
    if save_btn.count() > 0 and save_btn.is_enabled():
        save_btn.click()
        time.sleep(3)
        return True
    # 変更がない場合は保存ボタンが無効のことがある
    print("  [情報] 保存ボタンが無効（変更なし？）")
    return True


def inspect_related_video_html(page: Page):
    """関連動画セクションのHTMLをファイルに出力する（セレクタ調査用）。"""
    html = page.content()
    out = LOG_DIR / f"studio_html_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    out.write_text(html, encoding="utf-8")
    print(f"  HTML保存: {out}")
    print(f"  ファイルサイズ: {out.stat().st_size:,} bytes")
    return out


def take_debug_snapshot(page: Page, label: str) -> str:
    """デバッグ用スクリーンショットを保存する。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = LOG_DIR / f"snapshot_{label}_{ts}.png"
    page.screenshot(path=str(path))
    print(f"  スナップショット保存: {path.name}")
    return str(path)


# ── 状態管理 ──

STATE_FILE = SCRIPT_DIR / "data" / "state" / "related_video_state.jsonl"


def load_processed_ids() -> set[str]:
    """処理済みvideo_idのセットを返す。"""
    if not STATE_FILE.exists():
        return set()
    ids = set()
    for line in STATE_FILE.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
            if d.get("result") == "success":
                ids.add(d["video_id"])
        except (json.JSONDecodeError, KeyError):
            continue
    return ids


def log_result(video_id: str, related_video_id: str, result: str,
               channel: str = "gachiho", error: str = ""):
    """処理結果をJSONLに追記する。"""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "video_id": video_id,
        "related_video_id": related_video_id,
        "result": result,
        "channel": channel,
        "timestamp": datetime.now().isoformat(),
    }
    if error:
        entry["error"] = error
    with open(STATE_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
