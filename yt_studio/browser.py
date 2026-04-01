"""YouTube Studio ブラウザ起動・終了.

note/browser.py と同じパターン。プロファイルは別ディレクトリで管理し、
note操作とのPlaywright衝突を防ぐ。

初回は login コマンドでブラウザを起動し、手動でGoogleログインする。
以降は cookie が永続化されるため自動ログインされる。
"""
from __future__ import annotations

import os
import pathlib

from playwright.sync_api import sync_playwright

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent.parent

# ブラウザプロファイル: チャンネルごとに分離
_BROWSER_PROFILE = os.environ.get("YT_STUDIO_BROWSER_PROFILE", "gachiho")
USER_DATA_DIR = SCRIPT_DIR / f".yt_studio_browser_{_BROWSER_PROFILE}"


def launch(headless: bool = False) -> tuple:
    """永続化されたブラウザコンテキストを起動する。

    Googleログインがbot検出でブロックされるため、
    Playwright内蔵Chromiumではなくシステムの Google Chrome を使う。
    """
    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        user_data_dir=str(USER_DATA_DIR),
        headless=headless,
        channel="chrome",
        viewport={"width": 1440, "height": 900},
        locale="ja-JP",
        args=[
            "--disable-blink-features=AutomationControlled",
        ],
        ignore_default_args=["--enable-automation"],
    )
    page = context.pages[0] if context.pages else context.new_page()
    return pw, context, page


def close(pw, context):
    """ブラウザを安全に閉じる。"""
    try:
        context.close()
    except Exception:
        pass
    try:
        pw.stop()
    except Exception:
        pass
