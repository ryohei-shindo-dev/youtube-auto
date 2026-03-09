# 運用 Runbook

## 日常運用

### 動画が自動投稿されているか確認
```bash
# cron ログを確認
cat logs/auto_publish.log

# posting_schedule.json で最新の投稿状態を確認
python -c "import json; d=json.load(open('posting_schedule.json')); print(f'総数: {len(d)}本'); print(f'投稿済み: {sum(1 for x in d if x.get(\"published\"))}本')"

# Google Sheets でも確認可能（F列: Status、J-M列: URL）
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

## トラブルシューティング

### cron が動かない
1. cron 登録を確認: `crontab -l`
2. ログを確認: `cat logs/auto_publish.log`
3. 手動実行でエラーを確認: `cd ~/youtube-auto && ./run_with_notify.sh auto_publish venv/bin/python auto_publish.py --platforms youtube instagram x`

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
