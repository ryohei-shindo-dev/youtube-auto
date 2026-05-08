"""
threads_auth.py
Threads API の初回OAuth認証を行うヘルパースクリプト。

使い方:
    python threads_auth.py

前提条件:
    1. InstagramアカウントにThreadsアカウントを接続済み
    2. Meta Developer App に「Threads API」ユースケースを追加済み
    3. threads_basic, threads_content_publish 権限を有効化済み
    4. リダイレクトURIに callback URL を登録済み

処理の流れ:
    1. ブラウザが開く → Threadsでログイン → アプリを許可
    2. リダイレクト先のページに認可コードが表示される
    3. コードをコピーしてターミナルに貼り付け
    4. 認可コードを短期トークンに交換
    5. 短期トークンを長期トークン（60日）に変換
    6. threads_token.json に保存
"""

from __future__ import annotations

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

TOKEN_FILE = SCRIPT_DIR / "threads_token.json"
REDIRECT_URI = "https://ryohei-shindo-dev.github.io/youtube-auto/callback"

# Threads API エンドポイント
AUTH_URL = "https://threads.net/oauth/authorize"
TOKEN_URL = "https://graph.threads.net/oauth/access_token"
GRAPH_API_BASE = "https://graph.threads.net"

# 必要なスコープ
SCOPES = "threads_basic,threads_content_publish"


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
            "grant_type": "th_exchange_token",
            "client_secret": app_secret,
            "access_token": short_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _get_user_info(access_token: str) -> dict:
    """Threads ユーザー情報を取得する。"""
    resp = requests.get(
        f"{GRAPH_API_BASE}/v1.0/me",
        params={
            "fields": "id,username,threads_profile_picture_url",
            "access_token": access_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    app_id = os.getenv("THREADS_APP_ID", "")
    app_secret = os.getenv("THREADS_APP_SECRET", "")

    if not app_id or not app_secret:
        print("\n[エラー] .env に以下を設定してください:")
        print("  THREADS_APP_ID=Threads API の App ID")
        print("  THREADS_APP_SECRET=Threads API の App Secret")
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
    print("  Threads OAuth 認証")
    print(f"{'='*60}")
    print("\n  ブラウザが開きます。Threadsにログインしてアプリを許可してください。")
    print("  許可後、認可コードが表示されるページにリダイレクトされます。")
    print("  そのコードをコピーして、ここに貼り付けてください。\n")

    # ブラウザを開く
    webbrowser.open(auth_url)

    # ユーザーにコードを入力してもらう
    auth_code = input("  認可コードを貼り付けてEnter: ").strip()

    if not auth_code:
        print("  [エラー] 認可コードが入力されませんでした。")
        return

    # コードの末尾に #_ が付く場合がある
    if auth_code.endswith("#_"):
        auth_code = auth_code[:-2]

    # Step 1: 認可コード → 短期トークン
    print("\n  短期トークンを取得中...")
    try:
        short_token_data = _exchange_code_for_token(app_id, app_secret, auth_code)
    except requests.exceptions.HTTPError as e:
        print(f"  [エラー] 短期トークン取得に失敗: {e}")
        if e.response is not None:
            print(f"  レスポンス: {e.response.text}")
        return
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
        threads_user_id = user_info.get("id", user_id)
        username = user_info.get("username", "不明")
        print(f"  ユーザー名: @{username}")
        print(f"  Threads User ID: {threads_user_id}")
    except Exception as e:
        print(f"  [警告] ユーザー情報取得に失敗: {e}")
        threads_user_id = user_id
        username = "不明"

    # 保存
    token_data = {
        "access_token": long_token,
        "threads_user_id": str(threads_user_id),
        "username": username,
        "saved_at": datetime.now().isoformat(),
        "expires_in": expires_in,
    }

    TOKEN_FILE.write_text(
        json.dumps(token_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n  保存完了: {TOKEN_FILE.name}")
    print(f"  User ID: {threads_user_id}")
    print(f"  Username: @{username}")
    print("\n  これで Threads への自動投稿が使えるようになります。")
    print(f"  ※ トークンは約{expires_in // 86400}日で期限切れになります。")


if __name__ == "__main__":
    main()
