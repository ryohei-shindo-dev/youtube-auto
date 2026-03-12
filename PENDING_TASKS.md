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

**状態**: ✅ 完了。27本生成済み、3/31まで予約投稿済み。

**関連ファイル**: `note_gen.py`, `batch_note_gen.py`, `sheets.py`（note管理タブ）

---

## 6. Shorts 追加バッチ生成

**状態**: 品質再設計3施策を実装済み（2026-03-12）。失敗27本の再生成待ち。

**在庫**: 公開済み16本 / 公開可能約92本（46日分） / トリアージ除外44本

**実装済み改善**:
- resolve 10→25パターン（3群: 継続肯定/時間肯定/不安鎮静）、テーマ別自動振り分け
- 禁止hookステム注入（バッチ内既出hookをプロンプトで排除）
- テーマ別スコアリング（感情テーマは数字配点軽減+共感チェック追加）

**次のアクション**:
1. `check_failed.py` で失敗27本を「未生成」にリセット
2. `batch_gen.py --count 10` で小バッチ実行 → 成功率50%以上か検証
3. 成功率が改善されたら残りを再生成（1回8-12本、最大15本）
4. Cランク57本（「売りたい」系25本・「暴落」系13本が大量偏り）の扱いを決める

**関連ファイル**: `batch_gen.py`, `script_gen.py`, `candidate_ranker.py`, `stock_scorer.py`, `check_failed.py`

---

## 優先度まとめ

| 優先度 | タスク | 状態 |
|--------|--------|------|
| 高 | TikTok / Meta 審査対応 | 審査結果待ち |
| 高 | Shorts 失敗27本の再生成（品質改善の検証） | 改善実装済み、実行待ち |
| 済 | note 記事 30本到達 | 27本生成、3/31まで予約投稿済み |
| 済 | バッチ品質再設計（resolve/hook/スコア） | 3施策実装済み |
| 中 | 長尺動画 2本目 | 1本目の効果観察中 |
| 済 | 投稿タイミング最適化 | launchd分離済み |
| 低 | 英語版チャンネル | 検討・準備済み |
