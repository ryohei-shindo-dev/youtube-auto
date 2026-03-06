"""
定期実行タスクのエラー通知（Gmail API経由）

buyma-auto の credentials.json / token.json を共用してメール送信する。

Usage:
    python error_notify.py <コマンド名> <エラーログファイル>
"""
from __future__ import annotations

import base64
import os
import sys
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

load_dotenv(Path(__file__).parent / ".env")

CREDENTIALS_FILE = str(Path.home() / "buyma-auto" / "purchase-logger" / "credentials.json")
TOKEN_FILE = str(Path.home() / "buyma-auto" / "purchase-logger" / "token.json")
# buyma-auto の token.json と同じスコープを指定する必要がある（不一致だとトークン検証エラー）
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/spreadsheets",
]


def _get_gmail_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
        else:
            raise RuntimeError("token.json が無効です。buyma-auto 側で再認証してください。")
    return build("gmail", "v1", credentials=creds)


def notify_error(command_name: str, error_text: str):
    """定期実行タスクのエラーをメール通知する。"""
    to = os.getenv("NOTIFY_EMAIL", "")
    if not to:
        print("[error_notify] NOTIFY_EMAIL が未設定のため通知スキップ")
        return

    subject = f"[youtube-auto] {command_name} 実行エラー"
    body = f"定期実行タスク「{command_name}」がエラーで終了しました。\n\n"
    if len(error_text) > 2000:
        body += "...(省略)...\n" + error_text[-2000:]
    else:
        body += error_text

    service = _get_gmail_service()
    msg = EmailMessage()
    msg.set_content(body)
    msg["To"] = to
    msg["Subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    print(f"[error_notify] エラー通知送信: {command_name}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python error_notify.py <コマンド名> <エラーログファイル>")
        sys.exit(1)

    cmd_name = sys.argv[1]
    log_file = sys.argv[2]

    try:
        with open(log_file) as f:
            error_text = f.read()
    except FileNotFoundError:
        error_text = "(ログファイルが見つかりません)"

    notify_error(cmd_name, error_text)
