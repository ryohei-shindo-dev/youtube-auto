---
date: 2026-03-29
severity: minor
status: resolved
affected: YouTube 19:00 投稿 1本欠損 + エラー通知未送信
root_cause: 旧形式フォルダがフォールバック選択されて受け入れテスト失敗 / NOTIFY_EMAIL未読み込み
---

# 障害報告: YouTube 19:00 投稿失敗（2026-03-29）

## タイムライン

| 時刻 | イベント |
|------|---------|
| 07:00 | YouTube投稿ジョブ正常完了（No.123） |
| 19:00 | YouTube投稿ジョブ実行 → 受け入れテスト失敗で投稿中止 |
| 19:00 | エラー通知（NOTIFY_EMAIL未設定のためスキップ） |
| ~19:25 | ユーザーが未投稿を発見、手動対応を依頼 |
| ~19:30 | 手動で `auto_publish.py --platforms youtube` 実行 → No.80 投稿成功 |
| ~19:35 | 旧形式フォルダ95本のステータスを「破棄」に一括更新 |
| ~20:50 | エラー通知が届かない問題を調査 → NOTIFY_EMAIL が launchd で未設定と判明 |
| ~20:55 | run_with_notify.sh に .env 読み込み処理を追加、動作確認完了 |

## 症状

19:00のYouTube自動投稿ジョブが動画を投稿せず終了（exit_code=1）。

## 原因

### 直接原因

1. publish_queue.json の先頭候補のhook「不安」が、7:00投稿分のhook「不安」と一致 → hook近接チェックでスキップ
2. フォールバックでシートの「生成済み」行を走査 → No.18（`20260305_122608`）が選択された
3. No.18は初期バッチ（2026-03-05）生成分で `thumbnail_frame.png` がない旧形式
4. 受け入れテスト「thumbnail_frame.pngなし（旧式レイアウトの可能性）」で投稿中止

### 根本原因

- 2026-03-05の初期バッチ生成分（93本）がシート上「生成済み」のまま残存
- これらは thumbnail_frame.png を持たない旧形式だが、ステータスが「破棄」に変更されていなかった
- 通常はpublish_queue.json内の新形式フォルダが選ばれるが、hook近接チェックでスキップされるとシート全体からフォールバック選択が行われ、旧形式フォルダが選ばれうる

## 影響

- YouTube 19:00枠の投稿が約30分遅延
- 手動投稿で復旧済み、コンテンツ欠損なし

## 問題2: エラー通知が届かない

### 症状

投稿失敗（exit_code=1）にもかかわらず、エラーメール通知が届かなかった。

### 原因

- `NOTIFY_EMAIL` は `.env` ファイルにのみ定義（`llc.zenshin@gmail.com`）
- `run_with_notify.sh` が `.env` を読み込んでいなかった
- launchdジョブは `~/.zshrc` を経由しないため、`.env` にしかない環境変数が見えない
- `error_notify.py` → `ops_shared.notify` が `NOTIFY_EMAIL` 未設定を検知 → 通知スキップ

## 対応

1. ✅ 手動で `auto_publish.py --platforms youtube` を実行して投稿（No.80）
2. ✅ シート上のthumbnail_frame.pngなし旧形式フォルダ95本のステータスを「破棄」に一括更新
3. ✅ `run_with_notify.sh` に `.env` 読み込み処理を追加（`set -a; source .env; set +a`）
4. ✅ launchd経由で `NOTIFY_EMAIL` が読み込まれることを動作確認済み

## 再発防止

- **投稿失敗**: 旧形式フォルダ95本を「破棄」に更新済み。フォールバック選択されても対象外になる
- **通知未送信**: `.env` が全ジョブで読み込まれるようになり、次回エラー時はメール通知が届く
