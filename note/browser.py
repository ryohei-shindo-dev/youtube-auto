"""note ブラウザ起動・終了の共通ユーティリティ.

他の note モジュールはここから _launch_browser / _close_browser を import する。
"""
from __future__ import annotations

import os
import pathlib

from playwright.sync_api import sync_playwright

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent.parent

# ブラウザプロファイル: 手動作業と自動ジョブで分離して衝突を防ぐ
# 環境変数 NOTE_BROWSER_PROFILE で切り替え可能（デフォルトは手動用）
_BROWSER_PROFILE = os.environ.get("NOTE_BROWSER_PROFILE", "manual")
USER_DATA_DIR = SCRIPT_DIR / f".note_browser_{_BROWSER_PROFILE}"


def _launch_browser(headless: bool = False) -> tuple:
    """永続化されたブラウザコンテキストを起動する。"""
    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        user_data_dir=str(USER_DATA_DIR),
        headless=headless,
        viewport={"width": 1280, "height": 900},
        locale="ja-JP",
    )
    page = context.pages[0] if context.pages else context.new_page()
    return pw, context, page


def _close_browser(pw, context, wait_for_user: bool = True):
    """ブラウザを安全に閉じる。wait_for_user=True ならユーザーが閉じるまで待つ。"""
    if wait_for_user:
        print("\n確認が終わったらブラウザを閉じてください。")
        try:
            context.pages[0].wait_for_event("close", timeout=0)
        except Exception:
            pass
    context.close()
    pw.stop()
