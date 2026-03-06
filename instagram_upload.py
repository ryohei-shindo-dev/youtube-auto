"""
instagram_upload.py
Instagram Platform API で Reels をアップロードするモジュール。

使い方:
    import instagram_upload
    url = instagram_upload.upload_video(
        video_path="done/20260305_105657/output.mp4",
        caption="含み損がつらい人へ #長期投資 #ガチホ",
    )

前提条件:
    - instagram_auth.py で初回トークン取得を済ませていること（instagram_token.json が存在すること）
    - .env に INSTAGRAM_APP_ID と INSTAGRAM_APP_SECRET が設定されていること
    - Instagram がビジネス/クリエイターアカウントであること

注意:
    - Instagram Graph API はローカルファイルを直接アップロードできない
    - Google Drive の共有リンク経由で一時的に動画を公開してアップロードする
"""

import json
import os
import pathlib
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

SCRIPT_DIR = pathlib.Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")

TOKEN_FILE = SCRIPT_DIR / "instagram_token.json"

# Instagram Graph API
GRAPH_API_BASE = "https://graph.instagram.com/v22.0"

# ポーリング設定
POLL_INTERVAL = 5  # 秒
POLL_MAX_WAIT = 300  # 最大5分


def upload_video(
    video_path: str,
    caption: str = "",
    thumbnail_path: str = None,
) -> str:
    """
    Instagram Reels に動画をアップロードする。

    Args:
        video_path: 動画ファイルのパス（.mp4）
        caption: 投稿キャプション（ハッシュタグ含む、最大2200文字）
        thumbnail_path: サムネイル画像のパス（未使用、将来対応）

    Returns:
        投稿のパーマリンクURL（成功時）、None（失敗時）
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
    user_id = token_data.get("instagram_user_id", "")

    if not user_id:
        print("  [エラー] Instagram User ID が設定されていません。")
        return None

    # Step 1: 動画を一時ファイルホスティングにアップロードして公開URLを取得
    print("  Instagram: 動画を一時的に公開URL化中...")
    video_url = _upload_to_temp_hosting(video_file)
    if not video_url:
        print("  [エラー] 動画の公開URL化に失敗しました。")
        return None

    # Step 2: メディアコンテナを作成
    print("  Instagram: Reelsコンテナ作成中...")
    container_id = _create_media_container(
        access_token, user_id, video_url, caption
    )
    if not container_id:
        return None

    # Step 3: 処理完了を待つ
    print("  Instagram: 動画処理中（最大5分）...")
    if not _wait_for_processing(access_token, container_id):
        return None

    # Step 4: 公開
    print("  Instagram: 公開中...")
    media_id = _publish_media(access_token, user_id, container_id)
    if not media_id:
        return None

    # Step 5: パーマリンクを取得
    permalink = _get_permalink(access_token, media_id)
    if permalink:
        print(f"  Instagram投稿完了: {permalink}")
    else:
        print(f"  Instagram投稿完了: media_id={media_id}")

    return permalink or media_id


def _upload_to_temp_hosting(video_file: pathlib.Path) -> str:
    """
    一時ファイルホスティング（litterbox.catbox.moe）に動画をアップロードし、
    直接ダウンロード可能なURLを返す。ファイルは72時間後に自動削除される。
    """
    try:
        with open(video_file, "rb") as f:
            resp = requests.post(
                "https://litterbox.catbox.moe/resources/internals/api.php",
                data={"reqtype": "fileupload", "time": "72h"},
                files={"fileToUpload": (video_file.name, f, "video/mp4")},
                timeout=120,
            )

        if resp.status_code == 200 and resp.text.strip().startswith("https://"):
            url = resp.text.strip()
            print(f"  一時ホスティングにアップロード完了: {url}")
            return url

        print(f"  [エラー] 一時ホスティングアップロード失敗: {resp.status_code} {resp.text[:100]}")
        return None

    except Exception as e:
        print(f"  [エラー] 一時ホスティングアップロード失敗: {e}")
        return None


def _create_media_container(
    access_token: str, user_id: str, video_url: str, caption: str
) -> str:
    """Instagram Reels のメディアコンテナを作成する。"""
    resp = requests.post(
        f"{GRAPH_API_BASE}/{user_id}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption[:2200],  # Instagram上限
            "share_to_feed": "true",
            "access_token": access_token,
        },
        timeout=60,
    )

    if resp.status_code != 200:
        _save_debug("instagram_container_error.json", resp.text)
        print(f"  [エラー] Instagramコンテナ作成失敗: {resp.status_code}")
        error_data = resp.json().get("error", {})
        print(f"    {error_data.get('message', resp.text[:100])}")
        return None

    data = resp.json()
    container_id = data.get("id")
    if not container_id:
        _save_debug("instagram_container_error.json", json.dumps(data, ensure_ascii=False))
        print("  [エラー] コンテナIDが取得できませんでした")
        return None

    return container_id


def _wait_for_processing(access_token: str, container_id: str) -> bool:
    """動画の処理完了を待つ（最大5分）。"""
    elapsed = 0
    while elapsed < POLL_MAX_WAIT:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

        resp = requests.get(
            f"{GRAPH_API_BASE}/{container_id}",
            params={
                "fields": "status_code,status",
                "access_token": access_token,
            },
            timeout=30,
        )

        if resp.status_code != 200:
            continue

        data = resp.json()
        status = data.get("status_code", "")

        if status == "FINISHED":
            print(f"  Instagram: 動画処理完了（{elapsed}秒）")
            return True
        elif status == "ERROR":
            _save_debug("instagram_processing_error.json", resp.text)
            error_detail = data.get("status", "詳細なし")
            print(f"  [エラー] Instagram動画処理に失敗しました: {error_detail}")
            return False
        # IN_PROGRESS の場合は継続

    print(f"  [エラー] Instagram動画処理がタイムアウトしました（{POLL_MAX_WAIT}秒）")
    return False


def _publish_media(access_token: str, user_id: str, container_id: str) -> str:
    """メディアコンテナを公開する。"""
    resp = requests.post(
        f"{GRAPH_API_BASE}/{user_id}/media_publish",
        data={
            "creation_id": container_id,
            "access_token": access_token,
        },
        timeout=60,
    )

    if resp.status_code != 200:
        _save_debug("instagram_publish_error.json", resp.text)
        print(f"  [エラー] Instagram公開失敗: {resp.status_code}")
        return None

    return resp.json().get("id")


def _get_permalink(access_token: str, media_id: str) -> str:
    """投稿のパーマリンクを取得する。"""
    resp = requests.get(
        f"{GRAPH_API_BASE}/{media_id}",
        params={
            "fields": "permalink",
            "access_token": access_token,
        },
        timeout=30,
    )

    if resp.status_code == 200:
        return resp.json().get("permalink")
    return None


def _get_valid_token() -> dict:
    """有効なトークンを取得する。期限が近ければリフレッシュする。"""
    if not TOKEN_FILE.exists():
        print("  [エラー] instagram_token.json が見つかりません。")
        print("  先に python instagram_auth.py を実行してください。")
        return None

    with open(TOKEN_FILE, encoding="utf-8") as f:
        token_data = json.load(f)

    if "access_token" not in token_data:
        print("  [エラー] instagram_token.json にアクセストークンがありません。")
        return None

    # 期限チェック（残り5日以下でリフレッシュ）
    saved_at = token_data.get("saved_at", "")
    if saved_at:
        try:
            saved_date = datetime.fromisoformat(saved_at)
            days_elapsed = (datetime.now() - saved_date).days
            days_remaining = 60 - days_elapsed

            if days_remaining <= 5:
                print(f"  Instagram: トークン残り{days_remaining}日。リフレッシュ中...")
                refreshed = _refresh_token(token_data["access_token"])
                if refreshed:
                    token_data["access_token"] = refreshed
                    token_data["saved_at"] = datetime.now().isoformat()
                    TOKEN_FILE.write_text(
                        json.dumps(token_data, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    print("  Instagram: トークンリフレッシュ完了（新しい60日間）")
            elif days_remaining <= 10:
                print(f"  [情報] Instagram トークン残り{days_remaining}日")
        except Exception:
            pass

    return token_data


def _refresh_token(current_token: str) -> str:
    """長期トークンを更新する（新しい60日間）。"""
    resp = requests.get(
        f"{GRAPH_API_BASE}/refresh_access_token",
        params={
            "grant_type": "ig_refresh_token",
            "access_token": current_token,
        },
        timeout=30,
    )

    if resp.status_code == 200:
        return resp.json().get("access_token")

    print(f"  [警告] Instagramトークンリフレッシュ失敗: {resp.status_code}")
    return None


def _save_debug(filename: str, content: str):
    """デバッグ情報を debug/ に保存する。"""
    debug_dir = SCRIPT_DIR / "debug"
    debug_dir.mkdir(exist_ok=True)
    try:
        (debug_dir / filename).write_text(content, encoding="utf-8")
    except Exception:
        pass
