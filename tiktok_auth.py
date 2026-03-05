"""
tiktok_auth.py
TikTok Content Posting API の初回OAuth認証を行うヘルパースクリプト。

使い方:
    python tiktok_auth.py

前提条件:
    1. TikTok Developer (https://developers.tiktok.com/) でアプリを作成済み
    2. Content Posting API をアプリに追加済み
    3. リダイレクトURIに http://localhost:8585/callback を設定済み
    4. .env に TIKTOK_CLIENT_KEY と TIKTOK_CLIENT_SECRET を設定済み

処理の流れ:
    1. ブラウザが開く → TikTokでログイン → アプリを許可
    2. ローカルサーバーが認可コードを受信
    3. 認可コードをアクセストークンに交換
    4. tiktok_token.json に保存
"""

import http.server
import json
import os
import pathlib
import threading
import urllib.parse
import webbrowser

import requests
from dotenv import load_dotenv

SCRIPT_DIR = pathlib.Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")

TOKEN_FILE = SCRIPT_DIR / "tiktok_token.json"
REDIRECT_URI = "http://localhost:8585/callback"
REDIRECT_PORT = 8585

# TikTok OAuth エンドポイント
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"

# 必要なスコープ
SCOPES = "user.info.basic,video.publish,video.upload"


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """OAuth認可コードを受信するローカルHTTPサーバー。"""

    auth_code = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            _CallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                "<html><body><h2>認証成功！このタブを閉じてください。</h2></body></html>".encode()
            )
        else:
            error = params.get("error", ["不明なエラー"])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                f"<html><body><h2>認証エラー: {error}</h2></body></html>".encode()
            )

    def log_message(self, format, *args):
        pass  # ログを抑制


def _exchange_code_for_token(client_key: str, client_secret: str, code: str) -> dict:
    """認可コードをアクセストークンに交換する。"""
    resp = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    client_key = os.getenv("TIKTOK_CLIENT_KEY", "")
    client_secret = os.getenv("TIKTOK_CLIENT_SECRET", "")

    if not client_key or not client_secret:
        print("\n[エラー] .env に以下を設定してください:")
        print("  TIKTOK_CLIENT_KEY=あなたのClient Key")
        print("  TIKTOK_CLIENT_SECRET=あなたのClient Secret")
        print("\n取得方法:")
        print("  1. https://developers.tiktok.com/ にログイン")
        print("  2. 「Manage apps」→ アプリを選択")
        print("  3. 「App credentials」からキーをコピー")
        return

    # 認証URLを構築
    params = {
        "client_key": client_key,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    print(f"\n{'='*60}")
    print("  TikTok OAuth 認証")
    print(f"{'='*60}")
    print("\n  ブラウザが開きます。TikTokにログインしてアプリを許可してください。")
    print(f"  （自動で開かない場合はこのURLにアクセス）:\n  {auth_url}\n")

    # ローカルサーバーを起動してコールバックを待つ
    server = http.server.HTTPServer(("localhost", REDIRECT_PORT), _CallbackHandler)
    server_thread = threading.Thread(target=server.handle_request)
    server_thread.start()

    # ブラウザを開く
    webbrowser.open(auth_url)

    # コールバックを待つ
    server_thread.join(timeout=120)
    server.server_close()

    if not _CallbackHandler.auth_code:
        print("  [エラー] 認可コードを受信できませんでした。")
        return

    print("  認可コードを受信しました。トークンを取得中...")

    # トークン交換
    token_data = _exchange_code_for_token(client_key, client_secret, _CallbackHandler.auth_code)

    if "access_token" not in token_data:
        print(f"  [エラー] トークン取得に失敗: {json.dumps(token_data, ensure_ascii=False)}")
        return

    # トークンを保存
    TOKEN_FILE.write_text(json.dumps(token_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  トークン保存完了: {TOKEN_FILE.name}")
    print(f"  open_id: {token_data.get('open_id', '不明')}")
    print(f"  有効期限: {token_data.get('expires_in', '不明')}秒")
    print(f"  リフレッシュトークン有効期限: {token_data.get('refresh_expires_in', '不明')}秒")
    print("\n  これで tiktok_upload.py が使えるようになりました！")


if __name__ == "__main__":
    main()
