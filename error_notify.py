from __future__ import annotations

from pathlib import Path
from ops_shared.gmail_auth import GoogleAuthConfig, send_email
from ops_shared.notify import NotifyConfig, cli_main

GOOGLE_CONFIG = GoogleAuthConfig(
    credentials_path=Path.home() / "buyma-auto" / "purchase-logger" / "credentials.json",
    token_path=Path.home() / "buyma-auto" / "purchase-logger" / "token.json",
    scopes=("https://www.googleapis.com/auth/gmail.modify", "https://www.googleapis.com/auth/spreadsheets"),
)
NOTIFY_CONFIG = NotifyConfig(
    subject_prefix="[youtube-auto]",
    email_env_var="NOTIFY_EMAIL",
    sender=lambda to, subject, body: send_email(GOOGLE_CONFIG, to=to, subject=subject, body=body),
)

if __name__ == "__main__":
    cli_main(NOTIFY_CONFIG)
