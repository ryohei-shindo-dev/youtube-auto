---
name: batch-generate
description: Generate Shorts videos in batch for ガチホのモチベ. Supports normal batch and Batch API (submit/status/fetch). Use when user wants to generate multiple Shorts at once.
argument-hint: "[count] or [api-submit count|api-status batch-id|api-fetch batch-id]"
allowed-tools:
  - Read
  - Bash
  - Grep
  - Glob
---

# バッチ生成

Shorts 動画をまとめて生成するワークフロー。

## モード判定

`$ARGUMENTS` で分岐する:
- 数字のみ（例: `10`）→ 通常バッチ生成
- `api-submit 数字`（例: `api-submit 30`）→ Batch API で投入
- `api-status batch-id`（例: `api-status msgbatch_xxx`）→ Batch API ステータス確認
- `api-fetch batch-id`（例: `api-fetch msgbatch_xxx`）→ Batch API 結果取得
- 引数なし → 在庫確認のみ（生成は実行しない）

## 手順（通常バッチ）

1. **在庫確認**: Google Sheets の G列ステータスを確認し、残り本数を報告
2. **生成実行**:
   ```bash
   source venv/bin/activate
   python batch_gen.py --count <本数>
   ```
3. **結果確認**: 生成されたフォルダ数、成功/失敗本数を報告
4. **品質ゲート結果**: batch_gen.py 内蔵の品質ゲート3層（style_rules / scene_linter / queue_guard）の結果を要約

## 手順（Batch API）

1. **submit**: `python batch_api_gen.py submit --count <本数>`
2. **status**: `python batch_api_gen.py status --batch-id <batch-id>`
3. **fetch**: `python batch_api_gen.py fetch --batch-id <batch-id>`

## 注意事項

- **唯一のデータソースは Google Sheets**（posting_schedule.json は廃止済み）
- コードは B列（フォルダ名）のみをキーに使う。A列・タイトル検索は禁止
- Python 3.9 互換: `from __future__ import annotations` を忘れない
- 在庫30本（15日分）を切ったら補充を提案する
