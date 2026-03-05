"""
tiktok_auth.py
TikTok Content Posting API の初回OAuth認証を行うヘルパースクリプト。

使い方:
    python tiktok_auth.py

処理の流れ:
    1. ブラウザが開く → TikTokでログイン → アプリを許可
    2. リダイレクト先のページに認可コードが表示される
    3. コードをコピーしてターミナルに貼り付け
    4. 認可コードをアクセストークンに交換
    5. tiktok_token.json に保存
"""

import base64
import hashlib
import json
import os
import pathlib
import secrets
import urllib.parse
import webbrowser

import requests
from dotenv import load_dotenv

SCRIPT_DIR = pathlib.Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")

TOKEN_FILE = SCRIPT_DIR / "tiktok_token.json"
REDIRECT_URI = "https://ryohei-shindo-dev.github.io/youtube-auto/callback"

# TikTok OAuth エンドポイント
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"

# 必要なスコープ
SCOPES = "user.info.basic,video.publish,video.upload"


def _exchange_code_for_token(client_key: str, client_secret: str, code: str, code_verifier: str) -> dict:
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
            "code_verifier": code_verifier,
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
        return

    # PKCE: code_verifier と code_challenge を生成
    code_verifier = secrets.token_urlsafe(64)[:128]
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).rstrip(b"=").decode()

    # 認証URLを構築
    params = {
        "client_key": client_key,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    print(f"\n{'='*60}")
    print("  TikTok OAuth 認証")
    print(f"{'='*60}")
    print("\n  ブラウザが開きます。TikTokにログインしてアプリを許可してください。")
    print("  許可後、認可コードが表示されるページにリダイレクトされます。")
    print("  そのコードをコピーして、ここに貼り付けてください。\n")

    # ブラウザを開く
    webbrowser.open(auth_url)

    # ユーザーにコードを入力してもらう
    auth_code = input("  認可コードを貼り付けてEnter: ").strip()

    if not auth_code:
        print("  [エラー] 認可コードが入力されませんでした。")
        return

    print("  トークンを取得中...")

    # トークン交換
    token_data = _exchange_code_for_token(client_key, client_secret, auth_code, code_verifier)

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
