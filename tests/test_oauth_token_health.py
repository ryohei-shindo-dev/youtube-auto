"""OAuth token ヘルスチェック回帰テスト (5/10 incident A2).

5/10 incident: refresh_token revoke で auto_publish_youtube が失敗、
ユーザーが Gmail 通知で気付くまで silent failure 状態だった。

このテストは:
1. health_check_oauth.py が import 可能 + 構文 OK
2. sheets._get_credentials() が invalid_grant で `RefreshError` を raise
   (try/except で握りつぶしていないこと)
3. token rename 退避が動作すること

実際の Google API call は env 依存 + 副作用あり (token 書き換え) のため
unit テストでは mock で代替。

実 API smoke テスト (手元 pre-commit / CI で skip 制御):
    YOUTUBE_SHEET_ID=... pytest tests/test_oauth_token_health.py -v
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_health_check_script_importable():
    """scripts/health_check_oauth.py が syntax error なくロードできる."""
    script = PROJECT_ROOT / "scripts" / "health_check_oauth.py"
    assert script.exists(), "5/10 A1 で作成された health check が消えている"
    import ast
    ast.parse(script.read_text(encoding="utf-8"))


def test_reauth_script_importable():
    """scripts/reauth.py が syntax error なくロードできる."""
    script = PROJECT_ROOT / "scripts" / "reauth.py"
    assert script.exists(), "5/10 A1 で作成された reauth が消えている"
    import ast
    ast.parse(script.read_text(encoding="utf-8"))


def test_get_credentials_handles_invalid_grant_with_rename(tmp_path, monkeypatch):
    """sheets._get_credentials() が invalid_grant 時に token を退避し RefreshError を raise する.

    旧コード (5/10 修正前) は creds.refresh() の例外を握りつぶさずに伝搬していたが、
    token のリネーム退避もしていなかった (bug: 同じ token で reauth.py が動かない)。
    新コードは RefreshError を try/except → token rename → 再 raise する。
    """
    from google.auth.exceptions import RefreshError

    sys.path.insert(0, str(PROJECT_ROOT))
    import sheets  # type: ignore

    # ダミー token を作成 (本物の TOKEN_FILE を汚さない)
    fake_token = tmp_path / "token.json"
    fake_token.write_text(
        '{"token": "fake", "refresh_token": "fake", "client_id": "fake", '
        '"client_secret": "fake", "token_uri": "https://oauth2.googleapis.com/token"}'
    )
    monkeypatch.setattr(sheets, "TOKEN_FILE", str(fake_token))

    # Credentials.from_authorized_user_file が「expired creds with refresh_token」を返す
    mock_creds = MagicMock()
    mock_creds.valid = False
    mock_creds.expired = True
    mock_creds.refresh_token = "fake"
    # refresh() で invalid_grant を発生させる
    mock_creds.refresh.side_effect = RefreshError(
        "invalid_grant: Bad Request",
        {"error": "invalid_grant", "error_description": "Bad Request"},
    )

    with patch.object(sheets.Credentials, "from_authorized_user_file", return_value=mock_creds):
        with pytest.raises(RefreshError) as exc_info:
            sheets._get_credentials()

    assert "invalid_grant" in str(exc_info.value)
    # token がリネーム退避されていること
    assert not fake_token.exists(), "token が rename されていない"
    bak_files = list(tmp_path.glob("token.json.bak_invalid_*"))
    assert len(bak_files) == 1, f"退避ファイルが見つからない: {list(tmp_path.iterdir())}"


def test_get_credentials_propagates_helpful_message(tmp_path, monkeypatch, capsys):
    """invalid_grant 時に reauth.py の hint がエラーメッセージ or stderr に出る."""
    from google.auth.exceptions import RefreshError

    sys.path.insert(0, str(PROJECT_ROOT))
    import sheets  # type: ignore

    fake_token = tmp_path / "token.json"
    fake_token.write_text(
        '{"token": "fake", "refresh_token": "fake", "client_id": "fake", '
        '"client_secret": "fake", "token_uri": "https://oauth2.googleapis.com/token"}'
    )
    monkeypatch.setattr(sheets, "TOKEN_FILE", str(fake_token))

    mock_creds = MagicMock()
    mock_creds.valid = False
    mock_creds.expired = True
    mock_creds.refresh_token = "fake"
    mock_creds.refresh.side_effect = RefreshError("invalid_grant: Bad Request", {})

    with patch.object(sheets.Credentials, "from_authorized_user_file", return_value=mock_creds):
        with pytest.raises(RefreshError):
            sheets._get_credentials()

    captured = capsys.readouterr()
    # stderr に hint が出ていること
    assert "reauth.py" in captured.err, "reauth.py の hint が stderr に出ていない"


@pytest.mark.skipif(
    not os.getenv("YOUTUBE_SHEET_ID"),
    reason="実 API smoke は YOUTUBE_SHEET_ID 設定時のみ",
)
def test_oauth_token_real_smoke():
    """実 API で 1 call 通すヘルスチェック (CI で env 揃わなければ skip)."""
    sys.path.insert(0, str(PROJECT_ROOT))
    import sheets  # type: ignore

    sheet_id = os.environ["YOUTUBE_SHEET_ID"]
    svc = sheets.get_service()
    meta = svc.spreadsheets().get(
        spreadsheetId=sheet_id,
        fields="properties.title",
    ).execute()
    title = meta.get("properties", {}).get("title", "")
    assert title, "シートタイトル取得失敗 = token 不正の疑い"
