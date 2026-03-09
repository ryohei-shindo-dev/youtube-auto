# アーキテクチャ概要

## システム全体像

```
┌─────────────────────────────────────────────────────────┐
│                    入力ソース                            │
│  topics.json / Google Sheets / analytics_insights.json  │
└────────────────────────┬────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────┐
│               生成パイプライン（9ステップ）               │
│                                                         │
│  script_gen ──→ voice_gen ──→ slide_gen ──→ video_gen   │
│  (Claude API)  (ElevenLabs)   (Pillow)     (FFmpeg)     │
│       │                                                 │
│       ▼                                                 │
│  thumbnail_gen → subtitle_gen → note_gen → social_gen   │
│  (Pillow)        (SRT+JSON)    (Claude)   (テンプレート) │
└────────────────────────┬────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────┐
│            配信（auto_publish.py が統括）                 │
│                                                         │
│  youtube_upload ─── YouTube Data API v3                  │
│  instagram_upload ─ IG Graph API（catbox.moe 経由）      │
│  x_upload ───────── X API v2                            │
│  tiktok_upload ──── TikTok Content API v2（審査中）      │
│  note_x_announce ── X スタンドアロン投稿                 │
└────────────────────────┬────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────┐
│                   分析フィードバック                      │
│                                                         │
│  analytics_collect（毎晩 22:00）                         │
│       ▼                                                 │
│  analytics_analyze（毎週月曜 23:00）                      │
│       ▼                                                 │
│  analytics_insights.json → script_gen に自動注入         │
└─────────────────────────────────────────────────────────┘
```

## 各ステップの詳細

### 1. script_gen.py — 台本生成
- **入力**: トピック、テーマ、analytics_insights.json
- **処理**: Claude API で 5 シーン（hook / empathy / data / resolve / closing）を生成
- **出力**: script_data（辞書）
- **補足**: 弱い hook の自動検出・置換、誇張表現の自動修正あり

### 2. voice_gen.py — 音声合成
- **入力**: script_data
- **処理**: ElevenLabs REST API で各シーンの音声を生成
- **出力**: .m4a ファイル（シーンごと）
- **補足**: 読み辞書 160+ エントリ（ETF名・人名・投資用語の読み間違い対策）、速度 1.15x

### 3. slide_gen.py — スライド画像生成
- **入力**: script_data、テーマ、assets/ の背景画像
- **処理**: Pillow で 1080x1920 のスライドを生成（テキストオーバーレイ）
- **出力**: PNG（シーンごと）
- **補足**: 禁則処理あり

### 4. video_gen.py — 動画合成
- **入力**: スライド画像、音声ファイル、bgm_ambient.m4a
- **処理**: FFmpeg でスライド+音声+BGM を結合
- **出力**: output.mp4（H.264 + AAC）

### 5. thumbnail_gen.py — サムネイル生成
- **入力**: hook テキスト、resolve テキスト
- **処理**: Pillow で 1280x720 のサムネイル生成
- **出力**: thumbnail.png

### 6. subtitle_gen.py — 字幕生成
- **入力**: script_data、実尺秒数
- **処理**: 40文字/行でSRTファイルを生成
- **出力**: .srt、.json（トランスクリプト）

### 7. note_gen.py — note 記事生成
- **入力**: script_data またはトピック
- **処理**: Claude API で 800〜1500 字の記事を生成
- **出力**: note_articles/note_NN_title.md

### 8. social_gen.py — SNS キャプション生成
- **入力**: script_data、テーマ
- **処理**: 32 テンプレートからプラットフォーム別キャプション生成（API不要）
- **出力**: 各プラットフォーム用テキスト

### 9. auto_publish.py — 投稿スケジューラ
- **入力**: posting_schedule.json
- **処理**: 日付・時刻に基づき未投稿の動画をプラットフォームに投稿、Google Sheets 更新
- **出力**: 各プラットフォームの URL を posting_schedule.json と Sheets に記録

## データの流れ

### Google Sheets 列構成
```
A: No  B: Type  C: Topic  D: Keyword  E: Purpose  F: Status  G: Title
H: Gen_Date  I: Publish_Date
J: YouTube URL  K: IG URL  L: X URL  M: TikTok URL
N: Views  O-U: Review scores
```

### ステータス遷移
```
未生成 → 生成済み → 公開済み
```

## 長尺動画パイプライン

Shorts とは別系統で、以下のスクリプトを使用：
- `long_voice_gen.py` — 速度 1.05x（Shorts より遅め）
- `long_video_builder.py` — Ken Burns ズーム（100%→103.5%）、1画面1メッセージ
- `publish_long_video.py` — YouTube に予約投稿

出力先: `long_video/` ディレクトリ（エピソードごとにサブフォルダ）

## cron 定期実行

| 時刻 | スクリプト | 内容 |
|------|-----------|------|
| 毎日 07:00 / 19:00 | auto_publish.py | YouTube / IG / X に投稿 |
| 毎日 21:30 | note_x_announce.py | X スタンドアロン投稿 |
| 毎日 22:00 | analytics_collect.py | 再生数・エンゲージメント収集 |
| 毎週月曜 23:00 | analytics_analyze.py | 週次分析レポート生成 |

すべて `run_with_notify.sh` 経由で実行され、失敗時は `error_notify.py` が Gmail で通知。

## 外部サービス依存

| サービス | 用途 | 認証 |
|----------|------|------|
| Claude API | 台本・note 記事生成 | ANTHROPIC_API_KEY（.env） |
| ElevenLabs | 音声合成 | ELEVENLABS_API_KEY（.env） |
| YouTube Data API v3 | 動画投稿・分析収集 | token.json（OAuth） |
| Instagram Graph API | 画像/動画投稿 | instagram_token.json |
| X API v2 | ツイート投稿 | x_token.json |
| TikTok Content API v2 | 動画投稿（審査中） | tiktok_token.json |
| Google Sheets API | 投稿管理 | credentials.json（OAuth） |
| catbox.moe | IG アップロード用一時ホスティング | 不要 |
| Gmail API | エラー通知 | buyma-auto の credentials を流用 |
