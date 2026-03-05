"""
x_upload.py
X（旧Twitter）API v2 でテキストポストを投稿するモジュール。

使い方:
    import x_upload
    tweet_id = x_upload.post_tweet("含み損。\\n\\nでも20年続けた人\\n元本割れゼロ。\\n\\n#長期投資 #ガチホ")

前提条件:
    - x_auth.py で初回認証を済ませていること（x_token.json が存在すること）
    - .env に X_CLIENT_ID と X_CLIENT_SECRET が設定されていること
"""

import json
import os
import pathlib
import time

import requests
from dotenv import load_dotenv

SCRIPT_DIR = pathlib.Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")

TOKEN_FILE = SCRIPT_DIR / "x_token.json"

# X API v2 エンドポイント
TWEETS_URL = "https://api.twitter.com/2/tweets"
TOKEN_URL = "https://api.twitter.com/2/oauth2/token"


def post_tweet(text: str) -> str | None:
    """
    Xにテキストポストを投稿する。

    Args:
        text: 投稿テキスト（280文字以内）

    Returns:
        ツイートID（成功時）、None（失敗時）
    """
    token_data = _get_valid_token()
    if not token_data:
        return None

    access_token = token_data["access_token"]

    resp = requests.post(
        TWEETS_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={"text": text},
        timeout=30,
    )

    if resp.status_code == 201:
        data = resp.json()
        tweet_id = data.get("data", {}).get("id")
        return tweet_id

    print(f"  [エラー] X投稿失敗 (HTTP {resp.status_code}): {resp.text}")

    # デバッグ用にレスポンスを保存
    debug_dir = SCRIPT_DIR / "debug"
    debug_dir.mkdir(exist_ok=True)
    debug_path = debug_dir / f"x_error_{int(time.time())}.json"
    debug_path.write_text(resp.text, encoding="utf-8")

    return None


def _get_valid_token() -> dict | None:
    """有効なトークンを取得する。期限切れならリフレッシュする。"""
    try:
        with open(TOKEN_FILE, encoding="utf-8") as f:
            token_data = json.load(f)
    except FileNotFoundError:
        print("  [エラー] x_token.json が見つかりません。")
        print("  先に python x_auth.py を実行してください。")
        return None

    if "access_token" not in token_data:
        print("  [エラー] x_token.json にアクセストークンがありません。")
        print("  python x_auth.py を再実行してください。")
        return None

    # リフレッシュが必要かチェック
    if "refresh_token" in token_data and _should_refresh(token_data):
        print("  X: トークンをリフレッシュ中...")
        refreshed = _refresh_token(token_data["refresh_token"])
        if refreshed:
            token_data = refreshed
            _save_token(token_data)
            print("  X: トークンリフレッシュ完了")
        else:
            print("  [警告] Xトークンリフレッシュ失敗。既存トークンで続行します。")

    return token_data


def _should_refresh(token_data: dict) -> bool:
    """トークンのリフレッシュが必要かどうかを判定する。"""
    saved_at = token_data.get("saved_at", 0)
    expires_in = token_data.get("expires_in", 7200)  # X のデフォルトは2時間
    # 有効期限の10分前にリフレッシュ
    return time.time() > saved_at + expires_in - 600


def _refresh_token(refresh_token: str) -> dict | None:
    """リフレッシュトークンで新しいアクセストークンを取得する。"""
    client_id = os.getenv("X_CLIENT_ID", "")
    client_secret = os.getenv("X_CLIENT_SECRET", "")

    resp = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        auth=(client_id, client_secret),
        timeout=30,
    )

    if resp.status_code != 200:
        print(f"  [警告] Xトークンリフレッシュ失敗: {resp.status_code}")
        return None

    data = resp.json()
    if "access_token" not in data:
        print(f"  [警告] Xトークンリフレッシュ失敗: {data}")
        return None

    data["saved_at"] = int(time.time())
    return data


def _save_token(token_data: dict):
    """トークンデータをファイルに保存する。"""
    TOKEN_FILE.write_text(
        json.dumps(token_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
