---
title: note記事2本が同時刻に公開（3/26 12:30、reschedule重複チェック欠落）
date: 2026-03-26
severity: medium
status: resolved
root_cause: reorganize-missing-duplicate-check
cross_project: false
---

# note記事2本が同時刻に公開（2026-03-26 12:30）

## 症状

2026-03-26 12:30 に以下の2記事が同時公開された:
- 「オルカンかS&P500か迷って決められない｜比較疲れの整理」(naaa4579ff970)
- 「40代から新NISA・積み立て投資を始めるのは遅い？ 不安になる理由を整理」(nd93ee5e8ee67)

noteのダッシュボードで2記事が「2026年3月26日 12:30 公開中」と表示。

## 根本原因

### 直接原因: `cmd_reorganize` に重複チェックがなかった

`note_schedule_mixer.py` の `cmd_plan`（新規計画）には `find_duplicate_slots()` による重複チェック+エラー終了があるが、`cmd_reorganize`（並べ替え）には同じチェックがなかった。重複スロットを含む `reschedule_plan.json` がそのまま保存・適用された。

### 間接原因: `full_schedule.json` に前回未修正の重複が残存

2026-03-24 の障害で `full_schedule.json` の重複5箇所のうち4箇所を修正したが、**3/24 21:00 の重複1箇所が残存**していた。この重複入力を `reorganize_queue()` が `original_slots` としてそのまま引き継ぎ、記事の入れ替え時に重複が別スロット（3/26, 3/29, 4/1）に伝播した。

### 因果関係

```
full_schedule.json に 3/24 21:00 重複残存（前回修正漏れ）
    ↓
reorganize_queue() が重複スロットをそのまま original_slots に
    ↓
記事シャッフル後、重複が 3/26, 3/29, 4/1 に伝播
    ↓
cmd_reorganize に重複チェックなし → reschedule_plan.json に3箇所の重複
    ↓
apply-reschedule-plan でnote.comに適用
    ↓
3/26 12:30 に2記事同時公開
```

## 影響

- 2記事が同時公開（読者の通知が2件同時に届く、フィードで片方が埋もれる可能性）
- 3/29 12:30、4/1 12:30 にも同時公開が予定されていた（修正済み）

## 修正内容

### コード修正（再発防止）

1. **`cmd_reorganize` に `find_duplicate_slots()` チェック追加** — `cmd_plan` と同じガード。重複があればエラー終了し、`reschedule_plan.json` を保存しない

2. **`reorganize_queue` の `original_slots` 重複排除** — 入力データに重複スロットがあっても、出力に伝播しない。重複分は末尾に新スロットを自動生成

### データ修正

1. `full_schedule.json` — 3/24 21:00 重複を解消（1本を 4/5 12:30 に移動）
2. `reschedule_plan.json` — 3箇所の重複を解消:
   - 3/26 12:30: オルカンS&P500 → 4/9 21:00
   - 3/29 12:30: 暴落で積み立て → 4/10 21:00
   - 4/1 12:30: SNS爆益 → 4/16 12:30

### note.com 側の対応（手動必要）

- 3/26 12:30 に同時公開された2記事のうち1本の公開時刻をずらす（すでに公開済みのため、記事自体の修正は不要だが、今後の集計時に注意）

## 前回障害との関係

前回（incident-20260324-note-double-publish）で `full_schedule.json` の重複を修正したが:
- 5箇所中4箇所のみ修正、**1箇所（3/24 21:00）が残存**
- `cmd_reorganize` の重複チェック欠落は横展開調査の対象外だった
- `reorganize_queue` 自体の入力バリデーションも未実装だった

## 再発防止

- `cmd_reorganize` と `cmd_plan` の両方に重複チェックを統一（今回実装済み）
- `reorganize_queue` が重複入力を自動補正（今回実装済み）
- スケジュール関連の全コマンドで `find_duplicate_slots` を通す方針
