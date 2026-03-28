---
id: incident-2026-03-28-note-card-top-incomplete-repair
date: 2026-03-28
project: youtube-auto
severity: medium
status: resolved
tags:
  - note
  - prosemirror
  - card-link
  - cursor-position
services:
  - note
components:
  - note_article_updater
root_causes:
  - _append_card_linksのカーソル末尾移動が不確実（Meta+ArrowDownがProseMirrorで信頼できない）
  - repair_top_cardsの修復が不完全（Sheet 78で冒頭カードが残存）
cross_project: true
related_incidents:
  - incident-20260320-note-link-cards
  - incident-20260323-note-404-mass
lessons:
  - ProseMirrorでのカーソル移動はキーボードショートカットに依存せず、JS でSelection APIを使って検証すべき
  - 修復スクリプト実行後は全件の目視確認または自動検証が必要
---

# Incident: noteリンクカード冒頭誤挿入の修復不完全

**日付**: 2026-03-28
**影響**: 25記事中少なくとも1記事（Sheet 78）でリンクカードが記事冒頭に残存。他にも未修復の記事がある可能性
**深刻度**: medium

## 事象

3/28 12:30に公開されたnote記事「投資初心者が怖くて始められない理由」（Sheet 78、`n779de44278ed`）で、関連リンクが記事末尾ではなく本文の冒頭付近に表示されている。

スクリーンショットで確認された状態:
- 記事ヘッダー画像の直後にURLテキスト `https://note.com/gachiho_motive/n/n4962f0177e3a` が表示
- その下にリンクカード「現金のまま10年置いた100万円」が表示
- 本来は記事末尾の「あわせて読みたい」の後にカード化されて表示されるべき

## 直接原因

1. **3/27〜28の `_append_card_links()` 実行**: `Meta+ArrowDown` でカーソル末尾移動を試みるが、ProseMirrorのフォーカス挙動により**カーソルが冒頭のまま** → URLが記事冒頭に挿入された

2. **修復スクリプトの不完全実行**: `repair_top_cards.py` が作成されたが、Sheet 78の修復が完了していない（冒頭のカードが残存）

## 間接原因

1. `_append_card_links()` がカーソル位置を**検証せずに**URLペーストを実行していた。`body.click()` + `Meta+ArrowDown` は「試みる」だけで、成功を確認していない

2. `Meta+ArrowDown` はProseMirrorエディタで信頼できない操作 — エディタの実装によりキーイベントが正しく処理されないことがある

3. 修復スクリプト実行後の自動検証がない — 修復が成功したかどうかを目視に依存

## 暫定対応

- Sheet 78の記事は手動で修正が必要（冒頭のリンクカード/URLテキストを削除し、末尾に正しく配置）
- 他の影響記事24本の状態確認が必要

## 恒久対応（D+E方針: 2026-03-28 ChatGPT評価に基づく）

**既存記事への自動カード追加を廃止**。根本原因はカーソル制御の修正ではなく、ProseMirrorエディタへの末尾追記という戦略自体が構造的に信頼できないこと。

1. `run_note_body_update.py` を検出のみモードに変更（カード追加は実行しない）
2. `_append_card_links()` は停止。既存記事へのリンク追加は手動
3. 新規投稿時（`note_publish.py`）のみカード自動化を継続
4. `repair_duplicate_cards.py` を削除専用スクリプトとして整備
5. Playwrightスクリプトの共通バグ修正:
   - `wait_for_load_state("networkidle")` → `"domcontentloaded"` に変更（noteエディタはnetworkidleに到達しない）
   - `_close_browser(wait_for_user=False)` を自動スクリプトでは必須に

## 修復結果

### Sheet 78（初報の記事）
- 3/28: tmp_repair_sheet78.py で冒頭URLテキスト削除＋末尾カード追加 → 重複発生（4枚）
- 3/29: tmp_fix78.py で再確認 → カード2枚・空白1行で正常（前回修復が実は成功していた）
- 3/29: ユーザー目視確認で正常を確認

### 全25記事（3/29 repair_duplicate_cards.py）
- 修正: 11本（重複カード各1個を削除）
- 正常: 14本（修正不要）
- 失敗: 0本

修正対象: #40, #67, #70, #71, #72, #73, #76, #82, #90, #91, #92

## 経緯

| 日時 | 事象 |
|------|------|
| 3/27 21:30 | `_append_card_links()` で24記事にカード追加。フォーカス不足でカーソルが冒頭のまま → 冒頭にカード挿入 |
| 3/28 13:00 | 追加1記事で同様の問題発生。合計25記事 |
| 3/28 19:01 | `body.click()` 追加 + `repair_top_cards.py` で19記事修復（6記事はカードなしでスキップ） |
| 3/28 20:01 | 修復完了を報告（abf3cf2）。しかし Sheet 78 で冒頭にURLテキスト残存 |
| 3/28 21:06 | ユーザー報告: Sheet 78 に冒頭リンクカード残存 |
| 3/28 22:15 | Selection API検証を `_append_card_links` に追加（11e8fef） |
| 3/28 22:30 | tmp_repair_sheet78.py で Sheet 78 修復 → 重複カード4枚を作ってしまう（既存2枚を確認せず追加） |
| 3/28 22:55 | ユーザー報告: カード4枚＋空白行。「何十回もやってるから根本解決して」 |
| 3/28 23:00 | ChatGPT相談 → D+E方針採用。`_append_card_links` 廃止決定 |
| 3/28 23:10 | `run_note_body_update.py` 検出のみモードに変更、`repair_duplicate_cards.py` 作成 |
| 3/28 23:10〜23:55 | repair スクリプトが3回ハング（原因: `networkidle` + `_close_browser(wait_for_user=True)`） |
| 3/29 00:05 | 原因特定・修正。tmp_fix78.py で Sheet 78 正常確認 |
| 3/29 00:20 | ユーザーが全25記事 dry-run 実行: 重複11本検出 |
| 3/29 00:25 | ユーザーが全25記事 実修復実行: 修正11/正常14/失敗0 |

## 再発防止策

| 間接原因 | 対策 |
|---|---|
| 既存記事への末尾追記が構造的に不安定 | D+E方針: 既存記事への自動カード追加を廃止（恒久） |
| 修復時に既存カードを確認せず追加 | repair スクリプトは削除専用に限定 |
| Playwright の networkidle ハング | noteエディタでは domcontentloaded を使用 |
| _close_browser のユーザー待ち | 自動スクリプトでは wait_for_user=False 必須 |
| 修復の繰り返し試行で状態悪化 | 「追加しない・削除中心・末尾限定」の保守的修復方針を採用 |
