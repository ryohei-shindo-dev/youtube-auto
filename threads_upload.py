"""
threads_upload.py
Threads APIでテキスト投稿を行うモジュール。

使い方:
    # テスト投稿（1本）
    python threads_upload.py --test

    # 指定テキストで投稿
    python threads_upload.py --text "投稿テキスト"
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

SCRIPT_DIR = pathlib.Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")

TOKEN_FILE = SCRIPT_DIR / "threads_token.json"
GRAPH_API_BASE = "https://graph.threads.net/v1.0"


def _load_token() -> tuple[str, str]:
    """トークンとユーザーIDを読み込む。"""
    if TOKEN_FILE.exists():
        data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        return data["access_token"], data["threads_user_id"]

    # フォールバック: .env から
    token = os.getenv("THREADS_ACCESS_TOKEN", "")
    if not token:
        raise RuntimeError("threads_token.json も THREADS_ACCESS_TOKEN も見つかりません")
    # ユーザーID を API から取得
    resp = requests.get(
        f"{GRAPH_API_BASE}/me",
        params={"fields": "id", "access_token": token},
        timeout=30,
    )
    resp.raise_for_status()
    user_id = resp.json()["id"]
    return token, user_id


def post_text(text: str) -> dict | None:
    """テキスト投稿を行う。

    Threads APIの投稿は2ステップ:
    1. メディアコンテナ作成（POST /{user_id}/threads）
    2. 公開（POST /{user_id}/threads_publish）

    Returns:
        成功時: {"id": "投稿ID", "permalink": "URL"} / 失敗時: None
    """
    token, user_id = _load_token()

    # Step 1: メディアコンテナ作成
    create_resp = requests.post(
        f"{GRAPH_API_BASE}/{user_id}/threads",
        data={
            "media_type": "TEXT",
            "text": text,
            "access_token": token,
        },
        timeout=30,
    )

    if create_resp.status_code != 200:
        print(f"  [エラー] コンテナ作成失敗: {create_resp.status_code}")
        print(f"  {create_resp.text}")
        return None

    container_id = create_resp.json().get("id")
    if not container_id:
        print(f"  [エラー] コンテナIDが取得できません: {create_resp.json()}")
        return None

    # Step 2: 公開
    time.sleep(2)  # コンテナ処理待ち

    publish_resp = requests.post(
        f"{GRAPH_API_BASE}/{user_id}/threads_publish",
        data={
            "creation_id": container_id,
            "access_token": token,
        },
        timeout=30,
    )

    if publish_resp.status_code != 200:
        print(f"  [エラー] 公開失敗: {publish_resp.status_code}")
        print(f"  {publish_resp.text}")
        return None

    post_id = publish_resp.json().get("id")
    print(f"  投稿成功: post_id={post_id}")

    # パーマリンク取得
    permalink = None
    try:
        meta_resp = requests.get(
            f"{GRAPH_API_BASE}/{post_id}",
            params={
                "fields": "id,permalink",
                "access_token": token,
            },
            timeout=30,
        )
        if meta_resp.status_code == 200:
            permalink = meta_resp.json().get("permalink")
            print(f"  URL: {permalink}")
    except Exception:
        pass

    return {"id": post_id, "permalink": permalink}


def main():
    parser = argparse.ArgumentParser(description="Threads投稿ツール")
    parser.add_argument("--test", action="store_true",
                        help="テスト投稿（1本）")
    parser.add_argument("--text", type=str,
                        help="投稿テキストを直接指定")
    args = parser.parse_args()

    if args.text:
        print(f"\n投稿中...\n  テキスト: {args.text[:50]}...")
        result = post_text(args.text)
        if result:
            print("\n完了")
        else:
            print("\n失敗")

    elif args.test:
        test_text = (
            "積み立てって、\n"
            "増えた日より\n"
            "何も変えなかった日のほうが、\n"
            "あとで効いてくることがあります。"
        )
        print(f"\nテスト投稿中...\n  テキスト: {test_text}\n")
        result = post_text(test_text)
        if result:
            print("\n完了")
        else:
            print("\n失敗")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
