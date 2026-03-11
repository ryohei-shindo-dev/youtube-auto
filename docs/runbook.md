# 運用 Runbook

## 日常運用

### 動画が自動投稿されているか確認
```bash
# launchd ジョブの状態確認
launchctl list | grep youtube-auto

# 各プラットフォームのログを確認
cat logs/auto_publish_youtube.log
cat logs/auto_publish_instagram.log
cat logs/auto_publish_x.log

# Google Sheets で確認（G列: ステータス、K-N列: URL）
```

### 分析データの確認
```bash
# 最新の分析結果
cat analytics_insights.json

# 分析ログ（再生数の推移）
cat analytics_log.json
```

## よくある操作

### Shorts を 1 本手動生成
```bash
source venv/bin/activate
python main.py
# --dry-run で生成だけ（投稿しない）
# --theme テーマ名 でテーマ指定
```

### Shorts をバッチ生成
```bash
python batch_gen.py --count 10
```

### 手動で投稿
```bash
python auto_publish.py --platforms youtube instagram x
```

### note 記事を生成
```bash
# 1 本
python note_gen.py

# バッチ
python batch_note_gen.py
```

### X にスタンドアロン投稿
```bash
python note_x_announce.py --x-only
```

### 長尺動画を生成
```bash
python main.py --long
```

## コード修正時の手順（重要）

投稿ロジック（auto_publish.py / sheets.py 等）を修正するときは、**必ずジョブを停止してから修正する**。
ジョブ稼働中に修正すると、旧コードで動くジョブと新コードが混在して不整合が起きる（2026-03-11 障害の原因）。

```bash
# 1. 投稿ジョブを一時停止
launchctl unload ~/Library/LaunchAgents/com.youtube-auto.publish-youtube-morning.plist
launchctl unload ~/Library/LaunchAgents/com.youtube-auto.publish-youtube-evening.plist
launchctl unload ~/Library/LaunchAgents/com.youtube-auto.publish-x-morning.plist
launchctl unload ~/Library/LaunchAgents/com.youtube-auto.publish-x-evening.plist
launchctl unload ~/Library/LaunchAgents/com.youtube-auto.publish-instagram-noon.plist
launchctl unload ~/Library/LaunchAgents/com.youtube-auto.publish-instagram-evening.plist

# 2. コード修正・テスト
#    python auto_publish.py --dry-run で動作確認

# 3. ジョブを再開
launchctl load ~/Library/LaunchAgents/com.youtube-auto.publish-youtube-morning.plist
launchctl load ~/Library/LaunchAgents/com.youtube-auto.publish-youtube-evening.plist
launchctl load ~/Library/LaunchAgents/com.youtube-auto.publish-x-morning.plist
launchctl load ~/Library/LaunchAgents/com.youtube-auto.publish-x-evening.plist
launchctl load ~/Library/LaunchAgents/com.youtube-auto.publish-instagram-noon.plist
launchctl load ~/Library/LaunchAgents/com.youtube-auto.publish-instagram-evening.plist
```

一括停止・再開用（コピペ用）:
```bash
# 一括停止
for f in ~/Library/LaunchAgents/com.youtube-auto.publish-*.plist; do launchctl unload "$f"; done

# 一括再開
for f in ~/Library/LaunchAgents/com.youtube-auto.publish-*.plist; do launchctl load "$f"; done
```

## トラブルシューティング

### launchd ジョブが動かない
1. ジョブ登録を確認: `launchctl list | grep youtube-auto`
2. ログを確認: `cat logs/auto_publish_youtube.log`
3. 手動実行でエラーを確認: `bin/auto-publish-youtube`

### トークン期限切れ
各プラットフォームのトークンは有効期限がある：
- **Instagram**: 60 日（`instagram_auth.py` で更新）
- **TikTok**: `tiktok_auth.py` で再認証
- **X**: `x_auth.py` で再認証
- **YouTube / Sheets**: `token.json` が自動更新（失敗時は削除して再認証）

### Instagram アップロード失敗
- catbox.moe の一時ホスティングが不調な場合がある
- ログで URL を確認し、手動リトライ

### 音声の読み間違い
- `voice_gen.py` の読み辞書にエントリを追加
- 複合語 → ETF/ファンド名 → 証券/制度 → 人名 → 投資単語 の順で整理されている

## メニューコマンド
```bash
youtube-menu  # または ym
# 0: 定期実行ステータス一覧
# 1: 動画生成パイプライン
# 2: 投稿・配信
# 3: 分析
```
