"""OAuth token ヘルスチェック (5/10 incident 由来 A1).

投稿ジョブ (publish-youtube 等) の発火 1 時間前に launchd で実行し、
token が valid かを軽量に確認する。invalid_grant 等で失敗したら
exit 1 で終了し、run_with_notify.sh が ops-triage Gmail 通知を送る。

これにより 5/10 のような「投稿時刻になってから初めてエラー発覚」を
回避し、最大 1 時間早く気付ける (ユーザーが reauth.py を実行する余裕)。

使い方:
    python3 scripts/health_check_oauth.py

exit code:
    0: token valid (Sheets API call 成功)
    1: token invalid (invalid_grant / 401 / その他)
"""
from __future__ import annotations

import os
import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main():
    try:
        import sheets  # type: ignore
    except ImportError as exc:
        print(f"[health-check] sheets module の import に失敗: {exc}", file=sys.stderr)
        sys.exit(1)

    sheet_id = os.getenv("YOUTUBE_SHEET_ID", "")
    if not sheet_id:
        # sheet_id が未設定なら、環境問題で auto_publish 自体が動かない
        print("[health-check] YOUTUBE_SHEET_ID が未設定", file=sys.stderr)
        sys.exit(1)

    # 軽量な API call: spreadsheet のメタデータ (title) だけ取る
    try:
        svc = sheets.get_service()
        meta = svc.spreadsheets().get(
            spreadsheetId=sheet_id,
            fields="properties.title",
        ).execute()
        title = meta.get("properties", {}).get("title", "?")
        print(f"[health-check] OK: sheet title={title!r}")
        sys.exit(0)
    except Exception as exc:
        print(f"[health-check] FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        # invalid_grant の場合は reauth が必要
        if "invalid_grant" in str(exc):
            print(
                f"[health-check] hint: python3 {PROJECT_ROOT}/scripts/reauth.py を実行して再認証",
                file=sys.stderr,
            )
        sys.exit(1)


if __name__ == "__main__":
    main()
