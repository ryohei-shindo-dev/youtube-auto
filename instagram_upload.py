"""
instagram_upload.py
Instagram Graph API で Reels をアップロードするモジュール。

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

# Facebook Graph API
GRAPH_API_BASE = "https://graph.facebook.com/v21.0"

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
    account_id = token_data.get("instagram_business_account_id", "")

    if not account_id:
        account_id = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")
    if not account_id:
        print("  [エラー] Instagram Business Account ID が設定されていません。")
        return None

    # Step 1: 動画をGoogle Driveにアップロードして公開URLを取得
    print("  Instagram: 動画を一時的に公開URL化中...")
    video_url = _upload_to_drive(video_file, access_token)
    if not video_url:
        print("  [エラー] 動画の公開URL化に失敗しました。")
        print("  代替方法: 動画を手動でWeb公開し、URLを指定してください。")
        return None

    try:
        # Step 2: メディアコンテナを作成
        print("  Instagram: Reelsコンテナ作成中...")
        container_id = _create_media_container(
            access_token, account_id, video_url, caption
        )
        if not container_id:
            return None

        # Step 3: 処理完了を待つ
        print("  Instagram: 動画処理中（最大5分）...")
        if not _wait_for_processing(access_token, container_id):
            return None

        # Step 4: 公開
        print("  Instagram: 公開中...")
        media_id = _publish_media(access_token, account_id, container_id)
        if not media_id:
            return None

        # Step 5: パーマリンクを取得
        permalink = _get_permalink(access_token, media_id)
        if permalink:
            print(f"  Instagram投稿完了: {permalink}")
        else:
            print(f"  Instagram投稿完了: media_id={media_id}")

        return permalink or media_id

    finally:
        # Google Drive から一時ファイルを削除
        if video_url and "_drive_file_id" in dir():
            _delete_from_drive(_drive_file_id)


def _upload_to_drive(video_file: pathlib.Path, access_token: str) -> str:
    """
    Google Drive に動画をアップロードし、公開共有リンクを返す。

    Google認証は sheets.py の既存の仕組みを利用する。
    """
    try:
        import sheets
        from googleapiclient.http import MediaFileUpload

        # Google Drive サービスを取得
        creds = sheets._get_credentials()
        from googleapiclient.discovery import build
        drive_service = build("drive", "v3", credentials=creds)

        # アップロード
        file_metadata = {
            "name": f"ig_temp_{video_file.name}",
            "mimeType": "video/mp4",
        }
        media = MediaFileUpload(str(video_file), mimetype="video/mp4", resumable=True)
        uploaded = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id,webContentLink",
        ).execute()

        file_id = uploaded["id"]

        # 公開共有に設定
        drive_service.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()

        # 直接ダウンロードURLを取得
        # webContentLink は Google Drive のダウンロードリンク
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"

        # グローバル変数で保持（finally でクリーンアップ用）
        global _drive_file_id
        _drive_file_id = file_id

        print(f"  Google Drive にアップロード完了: {file_id}")
        return download_url

    except Exception as e:
        print(f"  [エラー] Google Drive アップロード失敗: {e}")
        return None


def _delete_from_drive(file_id: str):
    """Google Drive から一時ファイルを削除する。"""
    try:
        import sheets
        from googleapiclient.discovery import build
        creds = sheets._get_credentials()
        drive_service = build("drive", "v3", credentials=creds)
        drive_service.files().delete(fileId=file_id).execute()
        print(f"  Google Drive 一時ファイル削除完了")
    except Exception as e:
        print(f"  [警告] Google Drive 一時ファイル削除失敗: {e}")


def _create_media_container(
    access_token: str, account_id: str, video_url: str, caption: str
) -> str:
    """Instagram Reels のメディアコンテナを作成する。"""
    resp = requests.post(
        f"{GRAPH_API_BASE}/{account_id}/media",
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
        print(f"  [エラー] コンテナIDが取得できませんでした")
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
                "fields": "status_code",
                "access_token": access_token,
            },
            timeout=30,
        )

        if resp.status_code != 200:
            continue

        status = resp.json().get("status_code", "")

        if status == "FINISHED":
            print(f"  Instagram: 動画処理完了（{elapsed}秒）")
            return True
        elif status == "ERROR":
            _save_debug("instagram_processing_error.json", resp.text)
            print(f"  [エラー] Instagram動画処理に失敗しました")
            return False
        # IN_PROGRESS の場合は継続

    print(f"  [エラー] Instagram動画処理がタイムアウトしました（{POLL_MAX_WAIT}秒）")
    return False


def _publish_media(access_token: str, account_id: str, container_id: str) -> str:
    """メディアコンテナを公開する。"""
    resp = requests.post(
        f"{GRAPH_API_BASE}/{account_id}/media_publish",
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
        f"{GRAPH_API_BASE}/oauth/access_token",
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
