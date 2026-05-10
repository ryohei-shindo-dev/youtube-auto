"""youtube-auto 用 OAuth 再認証スクリプト (5/10 incident 由来).

revoke された refresh_token は creds.refresh() で invalid_grant になり、
sheets.py の _get_credentials() がそのまま例外を投げる。
このスクリプトは既存 token を .bak_reauth_<ts> にリネームしてから
InstalledAppFlow を直接起動し、強制的にブラウザフローを走らせる。

使い方:
    python3 scripts/reauth.py

参考: /Users/shindoryohei/otona-renai/scripts/reauth.py (otona-renai 側、5/5 incident で作成)

Note:
    Google API の OAuth フローは仕様上ブラウザ認証必須のため、
    本スクリプトは手動実行のみ。launchd 自動化はできない。
"""
from __future__ import annotations

import datetime
import os
import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# sheets.py の SCOPES と TOKEN_FILE / CREDENTIALS_FILE を再利用
from sheets import CREDENTIALS_FILE, SCOPES, TOKEN_FILE  # type: ignore  # noqa: E402

from google_auth_oauthlib.flow import InstalledAppFlow


def main():
    # 既存 token を退避
    if os.path.exists(TOKEN_FILE):
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{TOKEN_FILE}.bak_reauth_{ts}"
        os.rename(TOKEN_FILE, backup_path)
        print(f"既存トークンを退避: {backup_path}")

    # ブラウザフロー実行
    print(f"認証情報: {CREDENTIALS_FILE}")
    print(f"SCOPES: {SCOPES}")
    print("ブラウザを開きます。Google アカウントでログインして許可してください。")
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0)

    # token 保存
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())
    print(f"認証完了: {TOKEN_FILE}")
    print(f"refresh_token 保存済 (revoke されない限り、以後の launchd ジョブは自動復旧)")


if __name__ == "__main__":
    main()
