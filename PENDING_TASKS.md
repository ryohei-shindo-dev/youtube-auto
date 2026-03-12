# PENDING_TASKS - 残タスク一覧

> 最終更新: 2026-03-12
> Codex / Claude Code 共有。各タスクは「状態 → 次のアクション → 関連ファイル」だけ書く。

---

## 1. TikTok 本番審査の通過対応

**状態**: TikTok 再審査中（2026-03-06 再申請済み）。Meta / Instagram は審査通過済み。

**次のアクション**:
1. TikTok Developer Portal で審査結果を確認
2. 承認 → `.env` の Client Key を Production に切替 → `tiktok_auth.py` で本番トークン取得 → cron に `tiktok` 追加
3. 否認 → 否認理由を確認し `docs/` 配下を修正して再申請

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

## 4. Shorts 在庫管理

**状態**: 品質再設計+再生成完了（2026-03-12）。在庫約118本（59日分）。

**実績**: 失敗27本中26本を回収（成功率65%、改善前31%から倍増）。1本除外。

**次のアクション**:
1. Cランク57本（「売りたい」系25本・「暴落」系13本が大量偏り）の扱いを決める
2. `stock_scorer.py` で再スコアリング+公開順最適化を実行
3. 在庫が30本（15日分）を切ったら次の補充バッチ

**関連ファイル**: `batch_gen.py`, `stock_scorer.py`, `check_failed.py`

---

## 優先度まとめ

| 優先度 | タスク | 状態 |
|--------|--------|------|
| 高 | TikTok 審査対応 | TikTok審査結果待ち（Meta通過済み） |
| 中 | Cランク57本の扱い決定 | 未着手 |
| 中 | 長尺動画 2本目 | 1本目の効果観察中 |
| 低 | 英語版チャンネル | 検討・準備済み |
| 済 | バッチ品質再設計+再生成 | 26/27回収、成功率65% |
| 済 | note 記事 27本+予約投稿 | 3/31まで予約済み |
| 済 | 投稿タイミング最適化 | launchd分離済み |
