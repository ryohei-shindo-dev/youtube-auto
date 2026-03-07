# PENDING_TASKS - 残タスク一覧

> 最終更新: 2026-03-08
> メモリファイルから抽出した未完了タスクの整理

---

## 1. TikTok 本番審査の通過対応

### 目的
TikTok Production API の審査を通過し、自動投稿を有効化する。

### 関連ファイル
- `tiktok_auth.py` — OAuth認証（PKCE + GitHub Pagesコールバック）
- `auto_publish.py` — `--platforms` にtiktokを追加する箇所
- `docs/privacy.html`, `docs/terms.html`, `docs/index.html` — 審査用ページ
- `docs/callback.html` — OAuthコールバック
- `.env` — Sandbox/Production Client Key切替

### 実行手順
1. TikTok Developer Portal で審査結果を確認（2026-03-06 再申請済み）
2. **承認された場合**:
   - `.env` の Client Key を Production に切替（現在Sandbox設定）
   - `tiktok_auth.py` で本番トークン取得
   - テスト投稿で動作確認
   - cron の `--platforms` に `tiktok` を追加
3. **再度否認された場合**: 否認理由を確認し、docs/ 配下を修正して再申請

### 注意点
- Sandbox では `video.publish` スコープが使えない（本番のみ）
- Production切替時、Redirect URI が Sandbox 側にもクローンされているか確認
- テスターアカウント追加は Sandbox のみ必要

### 再開時の最初の一手
TikTok Developer Portal（https://developers.tiktok.com/）で審査ステータスを確認する。

### 関連メモ
- 2026-03-08: Meta の Instagram 投稿失敗 (`API access blocked`) を調査。`instagram_business_content_publish` の App Review に加え、Meta Business の `Access verification` / `ビジネス認証` が未完了であることを確認。
- 2026-03-08: Meta 審査用の整合性を取るため、`docs/index.html`、`docs/privacy.html`、`docs/terms.html` に運営主体 `合同会社漸進`、`代表社員 進藤亮平`、登記住所、問い合わせ先を追記。TikTok 審査中のサービス名 `gachiho-motive` 自体は維持。
- 2026-03-08: Meta 側では個人名義ではなく法人名義 `合同会社漸進` で進める方針に切り替え。使用予定書類は `2024-07-29` 取得の履歴事項全部証明書。
- 2026-03-08: Meta の `Access verification status` から `合同会社漸進` を法人候補として選択できる状態まで到達。候補名は `ZENSHIN, LIMITED LIABILITY COMPANY`、住所は `横浜市西区平沼1-40-9 パークハイツ横浜304` で一致。
- 2026-03-08: `本人確認` ルートで `Ryohei Shindo` の候補を選択し、運転免許証を提出。Meta 上は `本人確認が進行中です` / `通常48時間以内` の状態。
- 2026-03-08: 現時点のブロッカーは Meta 側の本人確認審査待ち。承認後に `instagram_business_content_publish` のアクセス状態を再確認し、必要なら `instagram_auth.py` を再実行して day 5 / day 6 の Instagram 再投稿を行う。

---

## 2. 5分動画（長尺）1本目の完成

### 目的
Shortsで集客 → 5分動画で信頼・ファン化・登録率UPの流れを作る。まず手動で3本作り、当たり構成を見つける。

### 現在の進捗
- 2026-03-07: このセッションで着手開始。
- 確認できた素材: `long_video/01_fukumison/audio/` に7セクション分の音声あり、合計約4分31秒。
- `memory/` 配下の補助メモは現時点で見当たらないため、`long_voice_gen.py` と `voice_result.json` を基準に再構成して進める。
- 2026-03-07: `long_video_builder.py` を追加し、1本目の長尺動画初稿を生成。
- 生成済み成果物:
  - `long_video/01_fukumison/output.mp4` — 約5分07秒
  - `long_video/01_fukumison/thumbnail.png`
  - `long_video/01_fukumison/slides/` — 15枚
  - `long_video/01_fukumison/video_meta.json` — タイトル・概要・タグ
- 2026-03-07: レビュー添付ミス防止のため、レビュー用コピー `long_video/01_fukumison/gachiho_long_01_5min05s.mp4` と `long_video/01_fukumison/gachiho_long_01_thumbnail.png` を追加。
- 2026-03-07: ChatGPTレビュー反映に着手。`overview` 短縮、前半スライド変化増加、`data` の数字強調、読み辞書追加を実施中。
- 2026-03-07: ChatGPTレビューを反映して、長尺1本目を再生成。
  - `overview` を短縮
  - 前半スライド枚数とレイアウト変化を増加
  - `data` を `-57% / 2013回復` 中心の見せ方へ変更
  - 読み辞書に `見逃す / 見逃している / 正念場 / 手数料` を追加
  - 新しいレビュー用ファイル `long_video/01_fukumison/gachiho_long_01_review.mp4` を追加
- 2026-03-07: 追加指摘を反映。
  - 読み辞書に `二文字 -> ふたもじ` を追加
  - `closing` をさらに短縮
  - `data` 後の断言を補強
  - 音声ノイズ対策として、長尺動画の結合方式を「音声付きクリップの連結」から「映像トラックと音声トラックの別結合」に変更
  - 再生成後のレビュー用ファイルは `long_video/01_fukumison/gachiho_long_01_review.mp4`

### 関連ファイル
- `memory/long_video_script_01.md` — 1本目の台本（含み損で眠れない夜）
- `long_voice_gen.py` — 長尺用音声生成スクリプト
- `long_video/01_fukumison/audio/` — 生成済み音声ファイル（7セクション、合計4分31秒）
- `memory/long_video.md` — 制作ガイド・進捗メモ

### 実行手順
1. スライド切り替え位置を決める（台本のセクション区切りに合わせる）
2. スライドを手動作成（1枚1メッセージ、見出し+補助短文+背景）
3. BGM選定（静かなアンビエント、声が主役）
4. 動画編集（音声+スライド+BGM+セクション間の間を結合）
5. サムネイル作成（Shortsと世界観統一、テーマを少し説明する型）
6. YouTubeにアップロード（概要欄・タグ・終了画面設定）
7. 2本目・3本目も同様に制作 → 8本時点で判断指標を評価

### 注意点
- セクション間の推奨間隔: 0.8〜1.2秒（long_video.md参照）
- 30秒ごとに画面か論点を変える（維持率対策）
- 投稿タイミング: 夜20:00（朝はShortsに譲る）
- パイプライン化は当たり構成が2〜3個固まってから

### 再開時の最初の一手
`long_video/01_fukumison/gachiho_long_01_review.mp4` を実再生で確認し、30秒以降のノイズが解消したかを先に耳で検証する。その後に ChatGPT へ再レビュー依頼する。

---

## 3. 英語版チャンネルの立ち上げ

### 目的
日本語Shortsの台本を70%流用・30%現地化し、英語圏の長期投資家向けに展開。20本テスト→反応確認→本格化。

### 関連ファイル
- `memory/english_channel.md` — チャンネル設計・台本20本・hook集
- `memory/english_tts_scripts.md` — TTS用原稿（ElevenLabs向け調整済み）
- `memory/english_20_scripts.json`（存在すれば）— 20本の投入用JSON

### 実行手順
1. チャンネル名を決定（候補: Stay Invested / Hold Steady / Still Holding）
2. YouTubeチャンネルを新規作成
3. ElevenLabsで英語音声テスト（速度1.10推奨）
4. 英語版 `script_gen` テンプレートを作成
5. 20本を生成→投稿→反応確認
6. 反応が良いテーマだけ追加量産

### 注意点
- 直訳NG（用語マッピングは english_channel.md 参照）
- data は1文のみに固定（説明を増やすと英語版は弱くなる）
- resolve は6種をローテーション（Time wins. / Don't quit. / Stay invested. 等）
- S&P 500 → "S and P five hundred" 等のTTS置換ルールあり

### 再開時の最初の一手
チャンネル名を最終決定し、YouTubeチャンネルを作成する。

---

## 4. 投稿タイミングのプラットフォーム別最適化

### 目的
現在は YouTube/Instagram/X を同時刻（7:00/19:00）に投稿しているが、プラットフォームごとの最適時刻にずらす。

### 関連ファイル
- `auto_publish.py` — 投稿実行スクリプト
- crontab — 現在 `0 7,19 * * *` で一括実行

### 実行手順
1. cron を分割設定:
   - YouTube: 07:00 / 19:00
   - X: 07:30 / 19:30（Shorts投稿30〜60分後が最適）
   - Instagram: 12:00 / 21:00
   - TikTok: 08:00 / 20:00（審査通過後）
2. `auto_publish.py` を個別プラットフォーム指定で呼び分ける
3. 1〜2週間データを取って効果を比較

### 注意点
- X は Shorts 投稿の30〜60分後が爆発パターンの鍵（初期評価タイミング）
- 1日2投稿の範囲なら凍結リスクなし
- 同一ポスト連投NG、外部リンクは1日1回

### 再開時の最初の一手
現在の crontab を確認し、プラットフォーム別に分割した cron エントリを作成する。

---

## 5. note 記事の量産・公開開始

### 目的
Shorts → note への導線を作り、信頼・SEO・ファン化を強化する。目標40記事。

### 関連ファイル
- `note_gen.py`（パイプラインの一部） — note記事生成
- `sheets.py` — `get_next_note_topic()`, `update_note_generated()`, `update_note_published()`
- Google Sheets「note管理」タブ — 15テーマ投入済み

### 実行手順
1. Google Sheets のnote管理タブから次のテーマを取得
2. `note_gen.py` で記事生成
3. ChatGPTレビュー（品質確認、平均9.02/10が基準）
4. noteに手動公開（公式APIなし）
5. 公開後、Sheetsのステータス・URL・公開日を更新
6. 推奨公開順: Day1 含み損→ Day3 確認回数→ Day5 暴落→ Day7 退場→ Day10 利確

### 注意点
- noteは公式APIがないため、公開は手動
- 週2〜3本ペース、800〜1500字
- 確約表現禁止（「傾向」「過去のデータでは」を使う）
- 毎回同じ5タグ: 長期投資, インデックス投資, 資産形成, NISA, 投資初心者

### 再開時の最初の一手
Google Sheets の note管理タブで未生成テーマを確認し、最初の1本を `note_gen.py` で生成する。

---

## 6. Shorts 300本到達（量産継続）

### 目的
10万登録の成功条件「300〜500本投稿」を達成する。現在142本 → あと約160本。

### 関連ファイル
- `script_gen.py` — 台本生成
- `auto_publish.py` — 自動投稿
- `posting_schedule.json` — 投稿スケジュール管理
- `analytics_collect.py` — アナリティクス収集（毎日22:00）

### 実行手順
1. 毎日投稿を継続（初期50本 → その後週5本）
2. hook偏りチェック（売りたい/暴落だけでなく退場/比較/増えない/焦りも使う）
3. 視聴維持率85%+を監視
4. ヒット動画が出たら同テーマで連続投稿
5. 100万再生ポテンシャルTOP20テーマを優先的に消化

### 現在の進捗
- 2026-03-07: `done/` のアーカイブ整理に着手。既存参照を壊さないため、トップレベルの生成フォルダは維持しつつ、日付別フォルダ側に参照用リンクを作る方針で整理する。
- 2026-03-07: `done/2026-03-04/` と `done/2026-03-05/` を作成し、既存生成フォルダへの参照リンクを配置。既存の `posting_schedule.json` などの参照先は未変更。

### 注意点
- hookチェック機能あり（弱いhookを自動検出・置換）
- 同テーマ5本以上連続NG（ローテーション必須）
- 説明動画にならないよう感情→データの順を守る
- Shorts尺は12〜15秒がベスト（最大17秒）

### 再開時の最初の一手
`posting_schedule.json` と `analytics_collect.py` のログで現在の投稿状況と視聴データを確認する。

---

## タスク優先度まとめ

| 優先度 | タスク | 状態 |
|---|---|---|
| 高 | TikTok審査対応 | 審査結果待ち |
| 高 | Shorts 300本到達 | 継続中（142/300本） |
| 高 | 投稿タイミング最適化 | 未着手 |
| 中 | 5分動画 1本目完成 | 初稿完成 → 目視レビュー・アップロード準備待ち |
| 中 | note 記事の量産開始 | テーマ投入済み → 生成・公開待ち |
| 低 | 英語版チャンネル立ち上げ | 検討・台本準備済み → 実行待ち |
