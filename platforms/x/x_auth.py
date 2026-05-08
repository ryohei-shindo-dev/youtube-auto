"""
x_auth.py
X（旧Twitter）API v2 の初回OAuth 2.0認証を行うヘルパースクリプト。

使い方:
    python x_auth.py

前提条件:
    1. X Developer Portal (https://developer.x.com/) でアプリを作成済み
    2. OAuth 2.0 を有効化し、Type of App を「Web App」に設定済み
    3. Callback URI に http://localhost:8686/callback を設定済み
    4. .env に X_CLIENT_ID と X_CLIENT_SECRET を設定済み

処理の流れ:
    1. ブラウザが開く → Xでログイン → アプリを許可
    2. ローカルサーバーが認可コードを受信
    3. 認可コードをアクセストークン + リフレッシュトークンに交換（PKCE）
    4. x_token.json に保存
"""

import base64
import hashlib
import http.server
import json
import os
import pathlib
import secrets
import threading
import time
import urllib.parse
import webbrowser

import requests
from dotenv import load_dotenv

SCRIPT_DIR = pathlib.Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")

TOKEN_FILE = SCRIPT_DIR / "x_token.json"
REDIRECT_URI = "http://localhost:8686/callback"
REDIRECT_PORT = 8686

# X OAuth 2.0 エンドポイント
AUTH_URL = "https://twitter.com/i/oauth2/authorize"
TOKEN_URL = "https://api.twitter.com/2/oauth2/token"

# 必要なスコープ（ツイート読み書き + オフラインアクセス = リフレッシュトークン取得）
SCOPES = "tweet.read tweet.write users.read offline.access"


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """OAuth認可コードを受信するローカルHTTPサーバー。"""

    auth_code = None
    expected_state = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        # CSRF対策: stateパラメータを検証
        received_state = params.get("state", [None])[0]
        if received_state != _CallbackHandler.expected_state:
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                "<html><body><h2>認証エラー: stateが一致しません</h2></body></html>".encode()
            )
            return

        if "code" in params:
            _CallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                "<html><body><h2>X認証成功！このタブを閉じてください。</h2></body></html>".encode()
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


def _generate_pkce_pair() -> tuple[str, str]:
    """PKCE用の code_verifier と code_challenge を生成する。"""
    # code_verifier: 43〜128文字のランダム文字列
    code_verifier = secrets.token_urlsafe(64)
    # code_challenge: code_verifier の SHA256 → Base64URL
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def _exchange_code_for_token(client_id: str, client_secret: str, code: str, code_verifier: str) -> dict:
    """認可コードをアクセストークンに交換する（PKCE）。"""
    resp = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
            "code_verifier": code_verifier,
        },
        auth=(client_id, client_secret),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    client_id = os.getenv("X_CLIENT_ID", "")
    client_secret = os.getenv("X_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        print("\n[エラー] .env に以下を設定してください:")
        print("  X_CLIENT_ID=あなたのClient ID")
        print("  X_CLIENT_SECRET=あなたのClient Secret")
        print("\n取得方法:")
        print("  1. https://developer.x.com/ にログイン")
        print("  2. プロジェクト → アプリを選択")
        print("  3. 「Keys and tokens」からOAuth 2.0のキーをコピー")
        print("  4. 「User authentication settings」で:")
        print("     - Type of App: Web App")
        print("     - Callback URI: http://localhost:8686/callback")
        return

    # PKCE ペア生成
    code_verifier, code_challenge = _generate_pkce_pair()

    # 状態リセット（再実行時の残留防止）
    _CallbackHandler.auth_code = None

    # 認証URLを構築
    state = secrets.token_urlsafe(32)
    _CallbackHandler.expected_state = state
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    print(f"\n{'='*60}")
    print("  X（旧Twitter）OAuth 2.0 認証")
    print(f"{'='*60}")
    print("\n  ブラウザが開きます。Xにログインしてアプリを許可してください。")
    print(f"  （自動で開かない場合はこのURLにアクセス）:\n  {auth_url}\n")

    # ローカルサーバーを起動してコールバックを待つ
    server = http.server.HTTPServer(("localhost", REDIRECT_PORT), _CallbackHandler)
    server_thread = threading.Thread(target=server.handle_request, daemon=True)
    server_thread.start()

    # ブラウザを開く
    webbrowser.open(auth_url)

    # コールバックを待つ
    try:
        server_thread.join(timeout=120)
    finally:
        server.server_close()

    if not _CallbackHandler.auth_code:
        print("  [エラー] 認可コードを受信できませんでした。")
        return

    print("  認可コードを受信しました。トークンを取得中...")

    # トークン交換（PKCE）
    token_data = _exchange_code_for_token(
        client_id, client_secret, _CallbackHandler.auth_code, code_verifier
    )

    if "access_token" not in token_data:
        print(f"  [エラー] トークン取得に失敗: {json.dumps(token_data, ensure_ascii=False)}")
        return

    # 保存時刻を追加
    token_data["saved_at"] = int(time.time())

    # トークンを保存
    TOKEN_FILE.write_text(json.dumps(token_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  トークン保存完了: {TOKEN_FILE.name}")
    print(f"  有効期限: {token_data.get('expires_in', '不明')}秒")
    print("\n  これで x_upload.py が使えるようになりました！")


if __name__ == "__main__":
    main()
