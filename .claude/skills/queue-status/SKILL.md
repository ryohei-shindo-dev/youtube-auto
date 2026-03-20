---
name: queue-status
description: Check Shorts queue health for ガチホのモチベ. Use when user wants queue count, category bias, duplication risk, theme balance, or inventory forecast.
argument-hint: "[all|today|week]"
allowed-tools:
  - Read
  - Bash
  - Grep
  - Glob
model: sonnet
---

# キュー状況確認

ガチホのモチベの投稿キュー健全性を確認する。

## 確認項目

1. **残本数**: Google Sheets の G列=「生成済み」の本数を数える
2. **カテゴリ偏り**: high_pain / mid_pain / recovery の比率を確認
3. **重複テーマ**: 直近14日分のキューで同じトピックが近接していないか
4. **朝枠/夜枠バランス**: 投稿スケジュールの偏りがないか
5. **補充判断**: 残30本（15日分）を切っていたら補充を提案

## 実行手順

1. Google Sheets から現在のキューデータを取得
   ```bash
   source venv/bin/activate
   python -c "
   from sheets import get_sheet_data
   import json
   data = get_sheet_data()
   generated = [r for r in data if r.get('status') == '生成済み']
   print(f'生成済み（未公開）: {len(generated)}本')
   "
   ```
2. publish_queue.json があればそちらも確認
3. カテゴリ・テーマの集計を行う
4. 結果を見やすい表形式で報告

## 出力形式

- 残本数（何日分か）
- カテゴリ偏り（比率）
- 重複リスク（あれば具体的に）
- 補充推奨（必要なら本数とテーマ方向）
