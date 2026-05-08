"""
tiktok_upload.py
TikTok Content Posting API v2 で動画をアップロードするモジュール。

使い方:
    import tiktok_upload
    url = tiktok_upload.upload_video(
        video_path="done/20260305_105657/output.mp4",
        title="含み損がつらい人へ｜長期投資",
        tags=["長期投資", "ガチホ", "投資"],
    )

前提条件:
    - tiktok_auth.py で初回認証を済ませていること（tiktok_token.json が存在すること）
    - .env に TIKTOK_CLIENT_KEY と TIKTOK_CLIENT_SECRET が設定されていること

注意:
    - TikTok API の審査が完了していない場合、プライベート投稿のみ可能
    - 審査完了後は .env に TIKTOK_APPROVED=true を設定して公開投稿を有効化
"""

import json
import os
import pathlib
import time

import requests
from dotenv import load_dotenv

SCRIPT_DIR = pathlib.Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")

TOKEN_FILE = SCRIPT_DIR / "tiktok_token.json"

# TikTok API エンドポイント
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
CREATOR_INFO_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
UPLOAD_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
PUBLISH_STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"


def upload_video(
    video_path: str,
    title: str = "",
    tags: list = None,
    privacy: str = "public",
) -> str:
    """
    TikTokに動画をアップロードする。

    Args:
        video_path: 動画ファイルのパス（.mp4）
        title: 動画タイトル（TikTokでは投稿テキストとして表示）
        tags: ハッシュタグリスト（例: ["長期投資", "ガチホ"]）
        privacy: "public" または "private"

    Returns:
        投稿のpublish_id（成功時）、None（失敗時）
    """
    video_file = pathlib.Path(video_path)
    if not video_file.exists():
        print(f"  [エラー] 動画ファイルが見つかりません: {video_path}")
        return None

    # トークン取得（期限切れならリフレッシュ）
    token_data = _get_valid_token()
    if not token_data:
        return None

    access_token = token_data["access_token"]

    # 審査状態に応じてプライバシー設定
    approved = os.getenv("TIKTOK_APPROVED", "false").lower() == "true"
    if not approved:
        privacy = "private"
        print("  [情報] TikTok API未審査のため、プライベート投稿になります。")

    # 投稿テキストを構築（タイトル + ハッシュタグ）
    post_text = _build_post_text(title, tags or [])

    # ファイルサイズ取得
    file_size = video_file.stat().st_size

    # Step 1: アップロード初期化（Direct Post）
    print("  TikTok: アップロード初期化中...")
    privacy_level = "SELF_ONLY" if privacy == "private" else "PUBLIC_TO_EVERYONE"

    init_body = {
        "post_info": {
            "title": post_text[:150],  # TikTok上限150文字
            "privacy_level": privacy_level,
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": file_size,
            "chunk_size": file_size,  # 1チャンクでアップロード
            "total_chunk_count": 1,
        },
    }

    resp = requests.post(
        UPLOAD_INIT_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json=init_body,
        timeout=30,
    )

    if resp.status_code != 200:
        _save_debug("tiktok_init_error.json", resp.text)
        print(f"  [エラー] TikTok初期化失敗: {resp.status_code}")
        return None

    init_data = resp.json()
    if init_data.get("error", {}).get("code") != "ok":
        _save_debug("tiktok_init_error.json", json.dumps(init_data, ensure_ascii=False))
        error_msg = init_data.get("error", {}).get("message", "不明なエラー")
        print(f"  [エラー] TikTok初期化エラー: {error_msg}")
        return None

    publish_id = init_data["data"]["publish_id"]
    upload_url = init_data["data"]["upload_url"]

    # Step 2: 動画ファイルをアップロード
    print("  TikTok: 動画アップロード中...")
    with open(video_file, "rb") as f:
        video_data = f.read()

    upload_resp = requests.put(
        upload_url,
        headers={
            "Content-Range": f"bytes 0-{file_size - 1}/{file_size}",
            "Content-Type": "video/mp4",
        },
        data=video_data,
        timeout=120,
    )

    if upload_resp.status_code not in (200, 201):
        _save_debug("tiktok_upload_error.json", upload_resp.text)
        print(f"  [エラー] TikTokアップロード失敗: {upload_resp.status_code}")
        return None

    # Step 3: 公開状態を確認
    print("  TikTok: 公開処理中...")
    tiktok_url = _wait_for_publish(access_token, publish_id)

    if tiktok_url:
        print(f"  TikTok投稿完了: {tiktok_url}")
    else:
        print(f"  TikTok投稿完了: publish_id={publish_id}")

    return publish_id


def _build_post_text(title: str, tags: list) -> str:
    """投稿テキストを構築する（タイトル + ハッシュタグ）。"""
    # #Shorts を除去
    text = title.replace("#Shorts", "").replace("#shorts", "").strip()

    # ハッシュタグを追加
    if tags:
        hashtags = " ".join(f"#{t}" for t in tags if not t.startswith("#"))
        text = f"{text} {hashtags}"

    # #fyp を追加（TikTokのFor You Page向け）
    if "#fyp" not in text.lower():
        text += " #fyp"

    return text[:150]  # TikTok上限


def _get_valid_token() -> dict:
    """有効なトークンを取得する。期限切れならリフレッシュする。"""
    if not TOKEN_FILE.exists():
        print("  [エラー] tiktok_token.json が見つかりません。")
        print("  先に python tiktok_auth.py を実行してください。")
        return None

    with open(TOKEN_FILE, encoding="utf-8") as f:
        token_data = json.load(f)

    # トークンの有効期限チェック
    # TikTok のトークンには expires_in（秒）が含まれるが、
    # 取得時刻が記録されていない場合はリフレッシュを試みる
    if "access_token" not in token_data:
        print("  [エラー] tiktok_token.json にアクセストークンがありません。")
        print("  python tiktok_auth.py を再実行してください。")
        return None

    # リフレッシュが必要な場合
    if "refresh_token" in token_data and _should_refresh(token_data):
        print("  TikTok: トークンをリフレッシュ中...")
        refreshed = _refresh_token(token_data["refresh_token"])
        if refreshed:
            token_data = refreshed
            TOKEN_FILE.write_text(
                json.dumps(token_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print("  TikTok: トークンリフレッシュ完了")

    return token_data


def _should_refresh(token_data: dict) -> bool:
    """トークンのリフレッシュが必要かチェックする。"""
    saved_at = token_data.get("saved_at", 0)
    expires_in = token_data.get("expires_in", 86400)
    if saved_at == 0:
        return True
    return time.time() > saved_at + expires_in - 3600  # 1時間前にリフレッシュ


def _refresh_token(refresh_token: str) -> dict:
    """リフレッシュトークンで新しいアクセストークンを取得する。"""
    client_key = os.getenv("TIKTOK_CLIENT_KEY", "")
    client_secret = os.getenv("TIKTOK_CLIENT_SECRET", "")

    resp = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=30,
    )

    if resp.status_code != 200:
        print(f"  [警告] TikTokトークンリフレッシュ失敗: {resp.status_code}")
        return None

    data = resp.json()
    if "access_token" not in data:
        print(f"  [警告] TikTokトークンリフレッシュ失敗: {data}")
        return None

    data["saved_at"] = int(time.time())
    return data


def _wait_for_publish(access_token: str, publish_id: str, max_wait: int = 60) -> str:
    """投稿の公開完了を待つ。URLが取得できればそれを返す。"""
    for _ in range(max_wait // 5):
        time.sleep(5)
        resp = requests.post(
            PUBLISH_STATUS_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={"publish_id": publish_id},
            timeout=30,
        )

        if resp.status_code != 200:
            continue

        data = resp.json()
        status = data.get("data", {}).get("status", "")

        if status == "PUBLISH_COMPLETE":
            # 公開完了
            return None  # TikTok APIではURLは直接返らない場合あり
        elif status in ("FAILED", "PUBLISH_FAILED"):
            fail_reason = data.get("data", {}).get("fail_reason", "不明")
            print(f"  [エラー] TikTok公開失敗: {fail_reason}")
            return None

    print("  [警告] TikTok公開確認がタイムアウトしました（バックグラウンドで処理中の可能性）")
    return None


def _save_debug(filename: str, content: str):
    """デバッグ情報を debug/ に保存する。"""
    debug_dir = SCRIPT_DIR / "debug"
    debug_dir.mkdir(exist_ok=True)
    try:
        (debug_dir / filename).write_text(content, encoding="utf-8")
    except Exception:
        pass
