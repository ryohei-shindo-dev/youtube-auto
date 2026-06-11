---
title: Instagram サムネhookテキスト連続事故（焦り×2 → 増えない×2）
date: 2026-03-26
severity: low
status: resolved
root_cause: queue-reorder-broke-stem-constraint + partial-bypass
cross_project: false
---

# Instagram サムネhookテキスト連続事故

## 症状

2026-03-24〜25 の Instagram 投稿で、サムネイルの大きなhookテキストが連続：
- 3/26: **焦り**（レバレッジ9割が退場）
- 3/25: **焦り**（勝者は生存者バイアス）
- 3/25: **増えない**（積み立て10年目から加速）
- 3/24: **増えない**（3年でやめた人は翌年逃す）

Instagram のプロフィールグリッドで「焦り、焦り、増えない、増えない」と並び、同じチャンネルの投稿が単調に見える。

## 根本原因（2つ）

### 1. キュー並び替え時の stem 制約破壊

2026-03-19 に「朝＝数字/差分、夕＝共感/継続」の交互並び替えを実施（commit ace2a22）。
この並び替えが **stem の8本間隔ルール**（同じhook語幹は8本以上離す）を無視して配置した。

結果、publish_queue.json に5箇所の違反が発生：
- stem=焦: 位置35→39（間隔4）、39→45（間隔6）
- stem=増え: 位置29→33（間隔4）
- stem=退屈: 位置41→43（間隔2）
- stem=後悔: 位置46→48（間隔2）

### 2. partial（部分投稿済み）のhookチェックスキップ

`auto_publish.py` の `get_next_publishable()` で、partial 候補（YouTube済み・Instagram未投稿）は **hookテキスト近接チェックを一切行わず即 return** していた。

```python
if partial:
    partial.sort(key=lambda c: c["gen_date"])
    return partial[0]  # ← hookチェックなし
```

YouTube が先に投稿 → Instagram は partial として無条件に受け入れる流れのため、キューの順番がそのまま Instagram に反映され、stem 違反がそのまま連続投稿になった。

## 修正内容

### auto_publish.py — partial にもhookチェック追加

partial 候補が複数ある場合、直近の公開済みhookと被らないものを優先選択するよう修正。
1つしかない場合は投稿しないわけにいかないのでそのまま投稿（警告ログ出力）。

### publish_queue.json — stem+slide_text 制約で再並び替え

62本全てを「同一stem・同一slide_text は8本以上離す」制約で再配置。違反0件を確認。

## 再発防止

- キューの並び替えを行う場合は、必ず stem 間隔チェックを通してから保存する
- `stock_scorer.reorder_with_constraints()` を使うか、stem 8本間隔を検証するスクリプトを実行する
