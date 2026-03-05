"""
instagram_auth.py
Instagram Graph API の初回トークン取得を行うヘルパースクリプト。

使い方:
    python instagram_auth.py

前提条件:
    1. Instagram アカウントを「ビジネスアカウント」または「クリエイターアカウント」に設定済み
    2. Facebook Page を作成し、Instagram アカウントと接続済み
    3. Facebook Developer (https://developers.facebook.com/) でアプリを作成済み
    4. Instagram Graph API をアプリに追加済み

処理の流れ:
    1. アクセストークンの取得方法を案内
    2. ユーザーがトークンを入力
    3. トークンを長期トークンに変換
    4. Instagram Business Account ID を自動取得
    5. instagram_token.json に保存
"""

import json
import os
import pathlib
from datetime import datetime

import requests
from dotenv import load_dotenv

SCRIPT_DIR = pathlib.Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")

TOKEN_FILE = SCRIPT_DIR / "instagram_token.json"

# Facebook Graph API
GRAPH_API_BASE = "https://graph.facebook.com/v21.0"


def _exchange_for_long_lived_token(short_token: str, app_id: str, app_secret: str) -> dict:
    """短期トークンを長期トークン（60日）に交換する。"""
    resp = requests.get(
        f"{GRAPH_API_BASE}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": short_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _get_instagram_account_id(access_token: str) -> str:
    """接続されたInstagramビジネスアカウントIDを取得する。"""
    # まずFacebook Pagesを取得
    resp = requests.get(
        f"{GRAPH_API_BASE}/me/accounts",
        params={"access_token": access_token},
        timeout=30,
    )
    resp.raise_for_status()
    pages = resp.json().get("data", [])

    if not pages:
        print("  [エラー] Facebook Pageが見つかりません。")
        return None

    # 各PageからInstagramアカウントを探す
    for page in pages:
        page_id = page["id"]
        page_token = page["access_token"]

        ig_resp = requests.get(
            f"{GRAPH_API_BASE}/{page_id}",
            params={
                "fields": "instagram_business_account",
                "access_token": page_token,
            },
            timeout=30,
        )
        ig_data = ig_resp.json()
        ig_account = ig_data.get("instagram_business_account", {})
        if ig_account.get("id"):
            print(f"  Instagram Business Account ID: {ig_account['id']}")
            print(f"  接続先 Facebook Page: {page.get('name', '不明')}")
            return ig_account["id"]

    print("  [エラー] Instagram Business Account が見つかりません。")
    print("  Instagram をビジネスアカウントに設定し、Facebook Page に接続してください。")
    return None


def main():
    app_id = os.getenv("INSTAGRAM_APP_ID", "")
    app_secret = os.getenv("INSTAGRAM_APP_SECRET", "")

    print(f"\n{'='*60}")
    print("  Instagram Graph API トークン取得")
    print(f"{'='*60}")

    if not app_id or not app_secret:
        print("\n  [準備] .env に以下を設定してください:")
        print("    INSTAGRAM_APP_ID=あなたのApp ID")
        print("    INSTAGRAM_APP_SECRET=あなたのApp Secret")
        print("\n  取得方法:")
        print("    1. https://developers.facebook.com/ にログイン")
        print("    2. 「マイアプリ」→ アプリを選択")
        print("    3. 「設定」→「ベーシック」からApp IDとApp Secretをコピー")
        return

    print("\n  アクセストークンの取得手順:")
    print("  1. https://developers.facebook.com/tools/explorer/ にアクセス")
    print("  2. 右上の「アプリ」から自分のアプリを選択")
    print("  3. 「ユーザーまたはページ」→「ページアクセストークンを取得」を選択")
    print("  4. 権限を追加: pages_show_list, instagram_basic, instagram_content_publish")
    print("  5. 「アクセストークンを取得」をクリック")
    print("  6. 表示されたトークンをコピー")

    token = input("\n  アクセストークンを貼り付け: ").strip()

    if not token:
        print("  [エラー] トークンが入力されませんでした。")
        return

    # 長期トークンに交換
    print("\n  長期トークンに変換中...")
    try:
        long_token_data = _exchange_for_long_lived_token(token, app_id, app_secret)
        long_token = long_token_data.get("access_token", token)
        print("  長期トークン取得完了（有効期限: 約60日）")
    except Exception as e:
        print(f"  [警告] 長期トークン変換に失敗しました: {e}")
        print("  入力されたトークンをそのまま使用します。")
        long_token = token

    # Instagram Business Account ID を取得
    print("\n  Instagram Business Account ID を取得中...")
    ig_account_id = _get_instagram_account_id(long_token)

    if not ig_account_id:
        ig_account_id = input("\n  手動でInstagram Business Account IDを入力（分かる場合）: ").strip()
        if not ig_account_id:
            print("  [エラー] IDが取得できませんでした。")
            return

    # 保存
    token_data = {
        "access_token": long_token,
        "instagram_business_account_id": ig_account_id,
        "saved_at": datetime.now().isoformat(),
        "expires_in_days": 60,
    }

    TOKEN_FILE.write_text(json.dumps(token_data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n  保存完了: {TOKEN_FILE.name}")
    print(f"  Account ID: {ig_account_id}")
    print("\n  .env にも以下を追加してください:")
    print(f"    INSTAGRAM_BUSINESS_ACCOUNT_ID={ig_account_id}")
    print("\n  これで instagram_upload.py が使えるようになりました！")
    print("  ※ トークンは60日で期限切れになります。投稿時に自動リフレッシュされます。")


if __name__ == "__main__":
    main()
