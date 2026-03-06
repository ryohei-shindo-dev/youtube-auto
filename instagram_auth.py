"""
instagram_auth.py
Instagram Platform API の初回OAuth認証を行うヘルパースクリプト。

使い方:
    python instagram_auth.py

前提条件:
    1. Instagram アカウントを「ビジネスアカウント」または「クリエイターアカウント」に設定済み
    2. Facebook Developer (https://developers.facebook.com/) でアプリを作成済み
    3. アプリに「Instagram」プロダクトを追加済み

処理の流れ:
    1. ブラウザが開く → Instagramでログイン → アプリを許可
    2. リダイレクト先のページに認可コードが表示される
    3. コードをコピーしてターミナルに貼り付け
    4. 認可コードを短期トークンに交換
    5. 短期トークンを長期トークン（60日）に変換
    6. instagram_token.json に保存
"""

import json
import os
import pathlib
import urllib.parse
import webbrowser
from datetime import datetime

import requests
from dotenv import load_dotenv

SCRIPT_DIR = pathlib.Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")

TOKEN_FILE = SCRIPT_DIR / "instagram_token.json"
REDIRECT_URI = "https://ryohei-shindo-dev.github.io/youtube-auto/callback"

# Instagram Platform API エンドポイント
AUTH_URL = "https://www.instagram.com/oauth/authorize"
TOKEN_URL = "https://api.instagram.com/oauth/access_token"
GRAPH_API_BASE = "https://graph.instagram.com"

# 必要なスコープ（新しいInstagram Platform API用）
SCOPES = "instagram_business_basic,instagram_business_content_publish"


def _exchange_code_for_token(app_id: str, app_secret: str, code: str) -> dict:
    """認可コードを短期アクセストークンに交換する。"""
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": app_id,
            "client_secret": app_secret,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
            "code": code,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _exchange_for_long_lived_token(short_token: str, app_secret: str) -> dict:
    """短期トークンを長期トークン（60日）に交換する。"""
    resp = requests.get(
        f"{GRAPH_API_BASE}/access_token",
        params={
            "grant_type": "ig_exchange_token",
            "client_secret": app_secret,
            "access_token": short_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _get_user_info(access_token: str) -> dict:
    """Instagram ユーザー情報を取得する。"""
    resp = requests.get(
        f"{GRAPH_API_BASE}/me",
        params={
            "fields": "user_id,username",
            "access_token": access_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    app_id = os.getenv("INSTAGRAM_APP_ID", "")
    app_secret = os.getenv("INSTAGRAM_APP_SECRET", "")

    if not app_id or not app_secret:
        print("\n[エラー] .env に以下を設定してください:")
        print("  INSTAGRAM_APP_ID=あなたのApp ID")
        print("  INSTAGRAM_APP_SECRET=あなたのApp Secret")
        return

    # 認証URLを構築
    params = {
        "client_id": app_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
    }
    auth_url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"

    print(f"\n{'='*60}")
    print("  Instagram OAuth 認証")
    print(f"{'='*60}")
    print("\n  ブラウザが開きます。Instagramにログインしてアプリを許可してください。")
    print("  許可後、認可コードが表示されるページにリダイレクトされます。")
    print("  そのコードをコピーして、ここに貼り付けてください。\n")

    # ブラウザを開く
    webbrowser.open(auth_url)

    # ユーザーにコードを入力してもらう
    auth_code = input("  認可コードを貼り付けてEnter: ").strip()

    if not auth_code:
        print("  [エラー] 認可コードが入力されませんでした。")
        return

    # Step 1: 認可コード → 短期トークン
    print("\n  短期トークンを取得中...")
    try:
        short_token_data = _exchange_code_for_token(app_id, app_secret, auth_code)
    except Exception as e:
        print(f"  [エラー] 短期トークン取得に失敗: {e}")
        return

    short_token = short_token_data.get("access_token")
    user_id = short_token_data.get("user_id")

    if not short_token:
        print(f"  [エラー] トークン取得に失敗: {json.dumps(short_token_data, ensure_ascii=False)}")
        return

    print(f"  短期トークン取得完了（user_id: {user_id}）")

    # Step 2: 短期トークン → 長期トークン（60日）
    print("  長期トークンに変換中...")
    try:
        long_token_data = _exchange_for_long_lived_token(short_token, app_secret)
        long_token = long_token_data.get("access_token", short_token)
        expires_in = long_token_data.get("expires_in", 0)
        print(f"  長期トークン取得完了（有効期限: {expires_in // 86400}日）")
    except Exception as e:
        print(f"  [警告] 長期トークン変換に失敗: {e}")
        print("  短期トークンをそのまま使用します。")
        long_token = short_token
        expires_in = 3600

    # Step 3: ユーザー情報を取得
    print("  ユーザー情報を取得中...")
    try:
        user_info = _get_user_info(long_token)
        ig_user_id = user_info.get("user_id", user_id)
        username = user_info.get("username", "不明")
        print(f"  ユーザー名: @{username}")
        print(f"  Instagram User ID: {ig_user_id}")
    except Exception as e:
        print(f"  [警告] ユーザー情報取得に失敗: {e}")
        ig_user_id = user_id
        username = "不明"

    # 保存
    token_data = {
        "access_token": long_token,
        "instagram_user_id": str(ig_user_id),
        "username": username,
        "saved_at": datetime.now().isoformat(),
        "expires_in": expires_in,
    }

    TOKEN_FILE.write_text(json.dumps(token_data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n  保存完了: {TOKEN_FILE.name}")
    print(f"  User ID: {ig_user_id}")
    print(f"  Username: @{username}")
    print("\n  これで instagram_upload.py が使えるようになりました！")
    print(f"  ※ トークンは約{expires_in // 86400}日で期限切れになります。投稿時に自動リフレッシュされます。")


if __name__ == "__main__":
    main()
