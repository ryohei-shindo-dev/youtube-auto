# CLAUDE.md

## Purpose

YouTube チャンネル「ガチホのモチベ」の動画生成〜配信〜分析を完全自動化するシステム。
長期投資を続けるモチベーションを与える Shorts 動画・note 記事・SNS 投稿を AI で生成し、マルチプラットフォームに配信する。

トーンは「煽らない・助言しない・静かに寄り添う」。詳細なコンテンツルールは `AGENTS.md` を参照。

## Repo Map

```
├── script_gen.py        # 1. 台本生成（Claude API）
├── voice_gen.py         # 2. 音声合成（ElevenLabs）
├── slide_gen.py         # 3. スライド画像生成（Pillow）
├── video_gen.py         # 4. 動画合成（FFmpeg）
├── thumbnail_gen.py     # 5. サムネイル生成（Pillow）
├── subtitle_gen.py      # 6. 字幕生成（SRT + JSON）
├── note_gen.py          # 7. note 記事生成（Claude API）
├── note_image_gen.py    #    note ヘッダー画像生成（Pillow）
├── social_gen.py        # 8. SNS キャプション生成（テンプレート）
├── auto_publish.py      # 9. 投稿スケジューラ（全プラットフォーム統括）
│
├── youtube_upload.py    # YouTube Data API v3
├── instagram_upload.py  # Instagram Graph API（catbox.moe 経由）
├── tiktok_upload.py     # TikTok Content Posting API v2
├── x_upload.py          # X API v2
├── note_x_announce.py   # X スタンドアロン投稿
│
├── analytics_collect.py # 毎日 22:00 — 再生数・エンゲージメント収集
├── analytics_analyze.py # 毎週月曜 23:00 — 週次分析 → insights 生成
│
├── sheets.py            # Google Sheets / YouTube / Drive API ラッパー
├── main.py              # CLI エントリポイント（--dry-run, --long, --theme）
├── batch_gen.py         # Shorts 一括生成（N 本連続）
├── batch_note_gen.py    # note 記事一括生成
├── review_gen.py        # ChatGPT レビュー用プロンプト生成
├── error_notify.py      # cron 失敗時 Gmail 通知
├── run_with_notify.sh   # cron ラッパー（エラー検知 → 通知）
│
├── long_video/          # 長尺動画の素材・出力
├── long_video_builder.py
├── long_voice_gen.py
├── publish_long_video.py
│
├── assets/              # 背景画像（12 枚）・長尺用画像・BGM・アイコン
├── note_articles/       # 生成済み note 記事（15 本）
├── bin/youtube-menu     # 対話メニュー（ym コマンド）
│
├── AGENTS.md            # コンテンツルール・表現チェックリスト（恒常）
├── CHANNEL_STRATEGY.md  # ブランド戦略・感情曲線・テーマ設計
├── OPERATIONS_MEMO.md   # 変動する運用情報・一時的な優先事項
│
├── posting_schedule.json    # 全動画の投稿スケジュール・状態
├── analytics_insights.json  # 分析結果 → script_gen に自動注入
├── hooks.json               # hook ワード 50 個（5 タイプ × 10）
├── analytics_log.json       # 再生数の時系列ログ
└── topics.json              # トピックマスタ
```

## Pipeline Flow

```
topics / Sheets → script_gen → voice_gen → slide_gen → video_gen
    → thumbnail_gen → subtitle_gen → note_gen → social_gen
    → auto_publish（YouTube / IG / X / TikTok）
    → analytics_collect（毎晩）→ analytics_analyze（毎週）
    → analytics_insights.json → script_gen にフィードバック
```

## Rules & Commands

### ビルド・実行
```bash
# 仮想環境（Python 3.9 互換）
source venv/bin/activate

# Shorts 1 本生成
python main.py

# バッチ生成
python batch_gen.py --count 10

# 手動投稿
python auto_publish.py --platforms youtube instagram x

# 分析
python analytics_collect.py
python analytics_analyze.py
```

### コード規約
- Python 3.9 互換: `from __future__ import annotations` が必要（`str | None` 構文のため）
- 外部 SDK は最小限: voice_gen / x_upload / tiktok_upload は `requests` 直接呼び出し
- Google API 認証: `sheets.py` の `_get_cached_service()` に統一
- 認証トークン（`*_token.json`, `credentials.json`）は `.gitignore` 管理

### 禁止事項
- 投資助言と受け取られる表現の生成（詳細は `AGENTS.md` の Avoid Phrases）
- 煽り・誇張・過剰断定（「絶対儲かる」「今が買い時」等）
- `done/`, `pending/`, `debug/` 内のファイルの Git 追跡

### 情報の階層
| ファイル | 役割 | 変更頻度 |
|----------|------|----------|
| `AGENTS.md` | コンテンツルール・表現規則 | 低（恒常） |
| `CHANNEL_STRATEGY.md` | ブランド戦略・構成設計 | 低 |
| `OPERATIONS_MEMO.md` | 運用数値・一時的な優先事項 | 高（変動） |
