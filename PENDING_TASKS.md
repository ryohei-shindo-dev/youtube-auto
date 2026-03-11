# PENDING_TASKS - 残タスク一覧

> 最終更新: 2026-03-12
> Codex / Claude Code 共有。各タスクは「状態 → 次のアクション → 関連ファイル」だけ書く。

---

## 1. TikTok 本番審査の通過対応

**状態**: 再審査中（2026-03-06 再申請済み）。Meta 側は本人確認審査待ち（マイナンバーカード提出済み、通常48時間以内）。

**次のアクション**:
1. TikTok Developer Portal で審査結果を確認
2. 承認 → `.env` の Client Key を Production に切替 → `tiktok_auth.py` で本番トークン取得 → cron に `tiktok` 追加
3. 否認 → 否認理由を確認し `docs/` 配下を修正して再申請
4. Meta 承認後 → `instagram_auth.py` 再実行して IG 再投稿

**関連ファイル**: `tiktok_auth.py`, `auto_publish.py`, `docs/privacy.html`, `docs/terms.html`, `.env`

---

## 2. 5分動画（長尺）2本目の企画・制作

**状態**: 1本目「含み損で眠れない夜に」は 2026-03-10 21:00 に公開済み（視聴回数3）。

**次のアクション**:
1. 1本目のパフォーマンスを1〜2週間観察
2. 2本目のテーマ・構成を決定
3. 制作・投稿

**関連ファイル**: `long_video_builder.py`, `long_video/`, `publish_long_video.py`

---

## 3. 英語版チャンネルの立ち上げ

**状態**: 検討中。台本20本・hook集・TTS原稿は準備済み。

**次のアクション**:
1. チャンネル名を最終決定（候補: Stay Invested / Hold Steady / Still Holding）
2. YouTube チャンネル作成 → ElevenLabs 英語音声テスト → 20本生成・投稿

**関連ファイル**: `memory/english_channel.md`, `memory/english_tts_scripts.md`

---

## 4. 投稿タイミングのプラットフォーム別最適化

**状態**: 完了。launchd で分離済み（YouTube 07:00/19:00、X 07:30/19:30、IG 12:00/21:00）。

**次のアクション**:
1. 1〜2週間データを取って効果比較
2. TikTok 承認後に TikTok 08:00/20:00 を追加

**関連ファイル**: `auto_publish.py`, `~/Library/LaunchAgents/com.youtube-auto.publish-*.plist`

---

## 5. note 記事の量産・公開開始

**状態**: 15本予約投稿済み。追加テーマの生成を継続。

**次のアクション**:
1. 30本到達を目指して追加テーマを生成
2. Sheets の note管理タブで未生成テーマを確認 → `note_gen.py` で生成

**関連ファイル**: `note_gen.py`, `batch_note_gen.py`, `sheets.py`（note管理タブ）

---

## 6. Shorts 300本到達（量産継続）

**状態**: 継続中（142本生成済み、うち87本未公開・15本公開済み）。在庫スコアリング済み（A:10本、B:20本、C:57本）。

**次のアクション**:
1. Cランク57本（「売りたい」系25本・「暴落」系13本が大量偏り）の扱いを決める
2. 次回バッチ生成で不足テーマ（比較焦り・積立疲れ・含み損系など）を重点補充
3. `publish_queue.json` の最適順で自動投稿中

**関連ファイル**: `batch_gen.py`, `stock_scorer.py`, `publish_queue.json`

---

## 優先度まとめ

| 優先度 | タスク | 状態 |
|--------|--------|------|
| 高 | TikTok / Meta 審査対応 | 審査結果待ち |
| 高 | Shorts 追加バッチ生成（後悔系・具体数字系・積立疲れ系・比較焦り系を重点） | Cランク35本除外済み、在庫52本 |
| 中 | note 記事 30本到達 | 15本予約投稿済み |
| 中 | 長尺動画 2本目 | 1本目の効果観察中 |
| 済 | 投稿タイミング最適化 | launchd分離済み |
| 済 | 長尺動画 1本目公開 | 2026-03-10 公開済み |
| 低 | 英語版チャンネル | 検討・準備済み |
