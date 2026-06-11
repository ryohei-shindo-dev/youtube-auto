# 20260510 OAuth invalid_grant 3 度目の再発 (youtube-auto)

## サマリー

5/10 (日) 19:00 の `com.youtube-auto.publish-youtube.1900` (launchd) が
`google.auth.exceptions.RefreshError: invalid_grant: Bad Request` で失敗。

これは **4/27 → 5/5 → 5/10 の 3 度目** の同根再発。前回 (5/5) の incident
クローズ条件 5 件のうち **A1〜A3 (品質ゲート / 回帰テスト / 横展開) が
未達のまま放置** されていたため、検出も復旧も遅延した。

## 発生状況

### Gmail 通知 (19:00)

```
件名: [youtube-auto] auto_publish_youtube 実行エラー
本文: ...invalid_grant: Bad Request, error_description: Bad Request...
```

### スタックトレース (要約)

```
File "auto_publish.py", line 988, in <module> main()
File "auto_publish.py", line 934, in main sheet_rows = _read_sheet_rows()
File "auto_publish.py", line 390, in _read_sheet_rows svc = sheets.get_service()
File "sheets.py", line 110, in _get_credentials creds.refresh(Request())
google.auth.exceptions.RefreshError:
  ('invalid_grant: Bad Request', {'error': 'invalid_grant', 'error_description': 'Bad Request'})
```

### ファイル状態

```
/Users/shindoryohei/youtube-auto/credentials.json -> /Users/shindoryohei/buyma-auto/purchase-logger/credentials.json (symlink)
/Users/shindoryohei/youtube-auto/token.json (4/10 22:20)  ← refresh_token revoke 済
```

## ユーザーの認識ズレ

ユーザー指摘:「日曜 19 時は投稿予定ないはずなのになんで失敗?」

事実:
- `com.youtube-auto.publish-youtube.1900.plist` の `StartCalendarInterval`:
  `{Hour: 19, Minute: 0}` (Weekday 指定なし)
- → **毎日 19:00 に launchd が起動する設計**
- 「投稿予定の有無を判定するために sheet を読みに行く」 → 投稿対象がなければ
  skip する内部ロジック
- 今回は **sheet API そのものが token revoke で失敗** → 投稿予定の有無に
  かかわらず例外で停止

ユーザー認識「投稿予定がない日は launchd 起動しない」は誤り。launchd は
毎日起動、sheet 読みで予定無ければ正常 skip するのが通常動作。

## 真因

### 直接原因

OAuth refresh_token が Google 側で **revoke** されている状態。
sheets.py の `_get_credentials()` 660 行付近:

```python
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())  # ← invalid_grant: Bad Request
    else:
        flow = InstalledAppFlow.from_client_secrets_file(...).run_local_server(...)
```

`creds.refresh()` が失敗しても try/except していないため例外が伝搬、
`run_local_server()` (ブラウザフロー) にフォールバックする経路がない。
launchd 経由ではブラウザを開けないので、仮にフォールバックしてもユーザーが
手動で認証する必要がある (Google API の制約)。

### 根本原因 (incident クローズ条件未達)

5/5 incident `docs/sessions/20260505_oauth_recurrence_remaining.md` で起票された:

- **A1. 投稿 1 時間前ヘルスチェック launchd job 新設** (post-long 17:30 / post-shorts-evening 19:00)
- **A2. 回帰テスト 1 件追加** (`get_youtube_service().channels().list(mine=True).execute()` を pytest)
- **A3. token_upload と token_analysis の物理分離 (or A1 でカバー)**

の 3 項目が未達のまま放置 → 今回 5/10 もバックグラウンド silent failure
(ユーザーが Gmail で気付くまで) を許した。

## 影響範囲

- youtube-auto (ガチホのモチベ チャンネル) の auto_publish_youtube 失敗
- 本日 (5/10 日) の sheets 読み取り全て影響、ただしシート上に「未生成」状態の
  投稿予定がなければ実害ゼロ
- token は **youtube-auto/token.json**、credentials は buyma-auto と共有
  (symlink) → buyma-auto 側にも同じ symptom が出ている可能性

## 横展開検査

| プロジェクト | token | 影響可能性 |
|---|---|---|
| youtube-auto | `youtube-auto/token.json` | ✅ 確定失敗 |
| buyma-auto | `buyma-auto/purchase-logger/token.json` (5/10 19:00 mtime) | 同 OAuth client、同 google account → 影響あり可能性高 |
| otona-renai | 別 token (otona-renai 専用) | 直接影響なし、ただし同 google account なら波及可能性 |

## 復旧方針 (2026-05-10 21:00 ユーザー判断)

**youtube-auto は縮小運用中 (Shorts 投稿停止 4/7〜、判定待ち) のため、
OAuth 復旧は実施しない。launchd 全 unload のまま現状維持。**

- token.json は不在 (`token.json.bak_reauth_20260510_193010` のみ残置)
- `~/Library/LaunchAgents/com.youtube-auto.*.plist` 15 個は配置済だが
  全て unload 状態 → 起動しない
- health-check launchd job (`com.youtube-auto.health-check-oauth.plist`)
  も load しない (チェック対象が全停止のため意味がない)
- 投稿再開を判断するタイミングで以下「再開時の復旧手順」を実行する

### 再開時の復旧手順 (将来用、現時点では実施しない)

#### Step 1: Google Cloud Console で OAuth client 設定確認 (ユーザー手動)

5/10 reauth.py 実行時にブラウザで「サービスをご利用いただけません」
(参照コード `ABAdc_hLrdKXYZ7cB6kj6OmuADm3kQ3OhYQu3llxA2PXiFSL36BkgcHyiLbTE-z6lccHfb8lZJiXmKcxJGT6gZZqRNjS2gPY0jsfUpbj6be-YGl_tZWc-_g`)
が出て認証完了できなかった。

1. https://console.cloud.google.com/apis/credentials/consent?project=purchase-logger-488506 を開く
2. **Publishing status** を確認 ("Testing" なら Test users に `llc.zenshin@gmail.com` 追加 or "In production" に切替)

#### Step 2: ユーザーが手動で再認証 (Google API 制約で必須)

```bash
! python3 /Users/shindoryohei/youtube-auto/scripts/reauth.py
```

このスクリプトが:
1. 既存 `token.json` を `.bak_reauth_<ts>` にリネームして退避
2. ブラウザを開いて Google OAuth フローを実行
3. 新しい `token.json` を保存

#### Step 3: 復旧確認

```bash
cd /Users/shindoryohei/youtube-auto
venv/bin/python -c "
from sheets import get_service
svc = get_service()
print('OK:', svc.spreadsheets().get(spreadsheetId='YOUR_SPREADSHEET_ID', fields='properties.title').execute())
"
```

#### Step 4: launchd 再 load + health-check plist 本番投入

```bash
for f in ~/Library/LaunchAgents/com.youtube-auto.*.plist; do
  launchctl load "$f"
done
cp launchd_examples/com.youtube-auto.health-check-oauth.plist \
   ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.youtube-auto.health-check-oauth.plist
```

## 残タスク (5/5 incident クローズ条件 A1〜A3 を再起票)

これらが完了するまでは「クローズ済」と書かない。

- [ ] **A1. 投稿 1 時間前ヘルスチェック launchd job 新設**
  - youtube-auto/scripts/health_check_oauth.py 新規作成
  - launchd: 17:30 / 18:30 / 06:00 等の発火直前に実行
  - invalid_grant 検出時は ops-triage Gmail 通知 + exit 1
  - これがあれば Gmail で 30 分以内に気付ける

- [ ] **A2. 回帰テスト 1 件追加**
  - `tests/test_oauth_token_health.py` 新規
  - skip制御 + secrets 必要 (CI で skip、手元 pre-commit で実行)

- [ ] **A3. sheets.py:_get_credentials() に invalid_grant 対応の例外処理追加**
  - try/except RefreshError → token rename + 例外伝搬で ops-triage 通知
  - ブラウザフロー自動起動はせず、reauth.py を実行する hint をログに出す

- [ ] **A4. credentials.json symlink の整理**
  - youtube-auto/credentials.json が buyma-auto/purchase-logger を symlink している
  - 全プロジェクト同じ OAuth client を使うのは管理上のリスク (1 つ revoke で全滅)
  - 物理コピーする or 用途別に分離するか判断

## クローズ条件

以下 5 件すべて [x] になるまで本 incident をクローズしない:

1. [x] 直接原因の修正 (sheets.py 例外処理 = A3、commit `619f6db`)。
       token reauth 自体は縮小運用中につき投稿再開時に実施。
2. [x] 同症状の他経路を列挙 (横展開表に記載)。
       buyma-auto / otona-renai 側の対応は各プロジェクトのスコープ。
3. [x] 主要経路に品質ゲート (= A1 ヘルスチェック launchd plist 作成完了、commit `619f6db`)。
       本番 load は投稿再開時に実施。
4. [x] 回帰テスト 1 件以上 (= A2、`tests/test_oauth_token_health.py` 4 PASSED + 1 SKIPPED、commit `619f6db`)
5. [x] 既存成果物への影響調査 (横展開検査の表で完了)

→ youtube-auto 側のクローズ条件は全て対応済み。投稿再開判断時に「再開時の
復旧手順」で reauth + launchd load を実施する。

## 関連ファイル

- `otona-renai/docs/incidents/incident-20260427-oauth-token-revoked.md` (1 度目、otona-renai 側)
- `otona-renai/docs/incidents/incident-20260505-oauth-invalid-grant-recurrence.md` (2 度目、otona-renai 側)
- `docs/sessions/20260505_oauth_recurrence_remaining.md` (5/5 残タスク)
- `~/otona-renai/scripts/reauth.py` (otona-renai 側 reauth 実装、参考)
- `~/Library/LaunchAgents/com.youtube-auto.publish-youtube.1900.plist`
