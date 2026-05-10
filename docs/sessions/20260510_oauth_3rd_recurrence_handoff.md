# 20260510 OAuth invalid_grant 3 度目再発 — youtube-auto への引き継ぎ

## 経緯

- **2026-05-10 (日) 19:00**: `com.youtube-auto.publish-youtube.1900` が失敗
  - `google.auth.exceptions.RefreshError: invalid_grant: Bad Request`
  - sheets.py:_get_credentials() で refresh_token revoke 検出
- **19:30**: `com.youtube-auto.publish-x.1930` も同根失敗
- 4/27 → 5/5 → 5/10 の **3 度目** の同根再発

5/5 incident (`otona-renai/docs/sessions/20260505_oauth_recurrence_remaining.md`)
の クローズ条件 A1〜A3 が **5 日間未着手のまま放置** されていたため、検出も
復旧も遅延した。

このセッション (otona-renai 側) で対応に着手したが、ユーザー指示
「youtube-auto の障害なら youtube-auto で対応するから引き継ぎ文を書いて」を
受けて本ドキュメントを作成。

## 本セッションで対応済み (otona-renai セッションで実施)

### A1+A2+A3 実装 (commit `619f6db`、push 済)

- `sheets.py:_get_credentials()` に `RefreshError` の try/except 追加 (A3)
  - token を `.bak_invalid_<ts>` に rename して退避
  - エラー時 stderr に reauth.py の hint 出力
- `scripts/health_check_oauth.py` 新規作成 (A1)
  - YOUTUBE_SHEET_ID で軽量 spreadsheets.get(fields=properties.title) 1 call
  - invalid_grant / その他例外で exit 1
- `launchd_examples/com.youtube-auto.health-check-oauth.plist` 新規作成 (A1)
  - 06:00 (07:00 ジョブの 1h 前) と 18:00 (19:00 ジョブの 1h 前) で発火
- `tests/test_oauth_token_health.py` 新規 (A2、4/4 PASSED + 1 SKIPPED)
- `scripts/reauth.py` 新規 (otona-renai 版を参考)
- `docs/incidents/20260510_oauth_invalid_grant_3rd_recurrence.md` 障害報告書

### 連鎖通知停止

`launchctl unload ~/Library/LaunchAgents/com.youtube-auto.*.plist` で **15 ジョブ
全 unload 済**。21:00 publish-instagram, 22:00 analytics-collect 等の続発予想を
止めた。`com.youtube-auto.health-check-oauth.plist` は新規 plist でまだ
load していない (token 復旧後に load する想定)。

### token.json の状態

- **revoke 状態のまま**
- `token.json.bak_reauth_20260510_193010` に退避済 (reauth.py 中断のため)
- 現在 youtube-auto/token.json は **不在**

### ops-hub 側通知改善 (commit `dfbc326`、push 済)

ユーザー指摘「障害メールに youtube-auto って書いてないから分からない」を受けて、
`ops-hub/runtime/failure-triage.py:format_triage_email()` を修正:
- 件名: `[ops-triage] [youtube-auto] auto_publish_youtube 失敗`
- 本文: `  - [youtube-auto] auto_publish_youtube  5/10(日) 19:00`

次回からは Gmail 件名で project が即判別可能。

## 引き継ぎ要請事項 (youtube-auto セッションで対応してほしい)

### Step 1: Google Cloud Console で OAuth client 設定確認 (ユーザー手動)

5/10 19:30 に reauth.py を実行したが、**ブラウザで「サービスをご利用いただけません」
エラー**(画像 #4 参照、参照コード `ABAdc_hLrdKXYZ7cB6kj6OmuADm3kQ3OhYQu3llxA2PXiFSL36BkgcHyiLbTE-z6lccHfb8lZJiXmKcxJGT6gZZqRNjS2gPY0jsfUpbj6be-YGl_tZWc-_g`)
が出て認証完了できなかった。

確認手順:

1. https://console.cloud.google.com/apis/credentials/consent?project=purchase-logger-488506 を開く
2. **Publishing status** を確認
   - "In production": 一般ユーザー誰でもログイン可能
   - "Testing": **Test users** に登録されたアカウントのみ可能
3. "Testing" モードなら **Test users** に `llc.zenshin@gmail.com` を追加
   (登録済でも有効期限切れの可能性あり、再登録推奨)
4. または "Production" に切り替える (個人 gmail なら問題ない)

### Step 2: reauth.py 再実行 (Step 1 完了後)

```bash
python3 /Users/shindoryohei/youtube-auto/scripts/reauth.py
```

ブラウザで認証完了 → 新しい `token.json` が生成される。

### Step 3: 動作確認

```bash
cd /Users/shindoryohei/youtube-auto
venv/bin/python scripts/health_check_oauth.py
```

OK 出力なら token 有効。

### Step 4: launchd 再 load

```bash
for f in ~/Library/LaunchAgents/com.youtube-auto.*.plist; do
  launchctl load "$f"
done
```

### Step 5: ヘルスチェック plist の本番 load (オプション、推奨)

新規 `com.youtube-auto.health-check-oauth.plist` を `~/Library/LaunchAgents/`
へコピーして load:

```bash
cp launchd_examples/com.youtube-auto.health-check-oauth.plist \
   ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.youtube-auto.health-check-oauth.plist
```

これで以降の **token revoke は最大 1 時間以内に Gmail で気付ける**。

## 残タスク (本 incident クローズ条件)

`docs/incidents/20260510_oauth_invalid_grant_3rd_recurrence.md` のクローズ条件:

- [x] 直接原因の修正 (sheets.py 例外処理 = A3)
- [ ] 同症状の他経路を列挙
  - youtube-auto/token.json (今回失敗、revoke 済)
  - buyma-auto/purchase-logger/token.json (同 OAuth client、影響あり可能性、要確認)
  - otona-renai/token (別 token、直接影響なし、念のため確認)
- [x] 主要経路に品質ゲート (= A1 ヘルスチェック launchd 新設、load は Step 5 で)
- [x] 回帰テスト 1 件以上 (= A2 4 件追加)
- [ ] 既存成果物への影響調査 (横展開検査、上の表)

### A4: credentials.json symlink 整理 (低優先)

```
youtube-auto/credentials.json -> buyma-auto/purchase-logger/credentials.json
```

全プロジェクトが同じ OAuth client を共有しているため、1 つ revoke で全滅。
将来的には用途別に分離 (project ごとに独立した OAuth client) が安全。
ただし管理コスト増、ChatGPT 相談で要否判断推奨。

## 関連リンク

### youtube-auto 側 (本リポジトリ)

- `docs/incidents/20260510_oauth_invalid_grant_3rd_recurrence.md` (本障害)
- `scripts/reauth.py` (5/10 起源、復旧スクリプト)
- `scripts/health_check_oauth.py` (5/10 起源、A1)
- `launchd_examples/com.youtube-auto.health-check-oauth.plist` (5/10 起源、A1)
- `tests/test_oauth_token_health.py` (5/10 起源、A2)

### otona-renai 側 (別リポジトリ、参考)

- `docs/incidents/20260427_oauth_token_revoked.md` (1 度目、4/27)
- `docs/incidents/20260505_oauth_invalid_grant_recurrence.md` (2 度目、5/5)
- `docs/sessions/20260505_oauth_recurrence_remaining.md` (5/5 残タスク 起票)
- `scripts/reauth.py` (otona-renai 用 reauth、参考実装)

### ops-hub 側 (別リポジトリ、通知改善)

- commit `dfbc326`: `runtime/failure-triage.py:format_triage_email()` に
  project tag 追加 (5/10 ユーザー指摘対応)
- `tests/test_format_triage_email_project_tag.py` 新規 4 test

## メモ: ユーザーの認識ズレ (説明済)

ユーザー質問「日曜 19 時は投稿予定ないはずなのになんで失敗?」への回答:
- `com.youtube-auto.publish-youtube.1900.plist` は **Weekday 指定なし、毎日 19:00 起動**
- 通常は Google スプレッドシート「投稿管理」を読みに行って状態列が「生成済み」の
  エントリがなければ silent exit 0 (通知なし)
- 今回は **シート自体が token revoke で読めない** ため例外 exit 1 → 通知発火
- = 「投稿予定なくても launchd は毎日起動してチェックする設計」

「投稿予定がある日だけ launchd 起動」する設計は別プロジェクト相当の規模変更。
本 incident のスコープ外、別途検討。
