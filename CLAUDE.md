# CLAUDE.md

## Purpose

`AGENTS.md` を参照。コンテンツルール・表現規則・禁止表現はすべて `AGENTS.md` が一次資料。

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
├── batch_gen.py         # Shorts 一括生成（N 本連続、3候補一括生成）
├── batch_api_gen.py     # Batch API 一括生成（50%割引、非同期）
├── batch_note_gen.py    # note 記事一括生成
├── review_gen.py        # ChatGPT レビュー用プロンプト生成
├── error_notify.py      # 定期実行失敗時 Gmail 通知
├── run_with_notify.sh   # 定期実行ラッパー（エラー検知 → 通知）
│
├── long_video/          # 長尺動画の素材・出力
├── long_video_builder.py
├── long_voice_gen.py
├── publish_long_video.py
│
├── assets/              # 背景画像（12 枚）・長尺用画像・BGM・アイコン
├── note_articles/       # 生成済み note 記事（28 本）
├── bin/youtube-menu     # 対話メニュー（ym コマンド）
│
├── AGENTS.md            # コンテンツルール・表現チェックリスト（恒常）
├── CHANNEL_STRATEGY.md  # ブランド戦略・感情曲線・テーマ設計
├── OPERATIONS_MEMO.md   # 変動する運用情報・一時的な優先事項
│
├── analytics_insights.json  # 分析結果 → script_gen に自動注入
├── hooks.json               # hook ワード 50 個（5 タイプ × 10）
├── analytics_log.json       # 再生数の時系列ログ
└── topics.json              # トピックマスタ
```

## Pipeline Flow

```
Sheets(投稿管理) → script_gen → voice_gen → slide_gen → video_gen
    → thumbnail_gen → subtitle_gen → note_gen → social_gen
    → done/{folder}/ にアーカイブ → Sheets に B列フォルダ名 + G=生成済み を記録
    → auto_publish: Sheets から G=生成済み を取得 → 各プラットフォーム投稿
    → Sheets に G=公開済み + URL を記録
    → analytics_collect（毎晩）→ analytics_analyze（毎週）
    → analytics_insights.json → script_gen にフィードバック
```

### 投稿管理シート列構成（正本）
```
A: No.（通番、人間用） B: フォルダ名（コードの唯一のキー）
C: 種別  D: トピック  E: 検索KW  F: 狙い
G: ステータス（未生成/生成済み/公開済み/投稿失敗）
H: タイトル  I: 生成日  J: 公開日
K: YouTube URL  L: Instagram URL  M: X URL  N: TikTok URL
O: 再生数  P: 備考  Q-V: レビュー列
```
- **コードは B列（フォルダ名）のみをキーに使う。A列・タイトル検索は禁止。**

## Rules & Commands

### ビルド・実行
```bash
# 仮想環境（Python 3.9 互換）
source venv/bin/activate

# Shorts 1 本生成
python main.py

# バッチ生成（逐次、3候補一括生成）
python batch_gen.py --count 10

# Batch API 生成（非同期、50%割引）
python batch_api_gen.py run --count 30
# または段階的に: submit → status → fetch
python batch_api_gen.py submit --count 30
python batch_api_gen.py status --batch-id msgbatch_xxx
python batch_api_gen.py fetch --batch-id msgbatch_xxx

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
- `done/`, `pending/`, `debug/` 内のファイルの Git 追跡
- コンテンツの禁止表現は `AGENTS.md` の Avoid Phrases を参照

### 情報の階層（1つの情報は1箇所だけに書く）
| ファイル | 役割 | 読み手 |
|----------|------|--------|
| `AGENTS.md` | コンテンツルール・表現規則（恒常） | Codex / Claude Code 共通 |
| `CLAUDE.md` | リポジトリの地図・コマンド | Claude Code |
| `PENDING_TASKS.md` | 残タスク・次のアクション | Codex / Claude Code 共通 |
| `CHANNEL_STRATEGY.md` | ブランド戦略・構成設計 | 両方 |
| `OPERATIONS_MEMO.md` | 変動する運用数値・一時的な優先事項 | 両方 |

### 詳細ドキュメント
- `docs/architecture.md` — システム全体像・各ステップの詳細・外部サービス依存
- `docs/runbook.md` — 日常運用・よくある操作・トラブルシューティング
- `docs/long-video.md` — 長尺動画のビジュアルルール・ディレクトリ構成
