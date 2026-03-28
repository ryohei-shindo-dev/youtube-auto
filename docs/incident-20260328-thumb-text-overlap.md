---
id: incident-2026-03-28-thumb-text-overlap
date: 2026-03-28
project: youtube-auto
severity: low
status: resolved
tags:
  - thumbnail-frame
  - text-overlap
  - slide_gen
services:
  - youtube
components:
  - slide_gen
root_causes:
  - _make_thumbnail_text_v2のhook+data結合時に部分一致チェックがない
cross_project: false
related_incidents:
  - incident-20260320-thumb-text-dupe
lessons:
  - サムネフレームテキストは複数スライドの文言を結合するため、結合元が重複しないかチェックが必要
---

# Incident: サムネフレームテキストがhook/dataスライドと文言重複

**日付**: 2026-03-28
**影響**: YouTube Short 1本（「暴落が怖い。でもバフェットはそこで買っていた」）のサムネフレーム+hookスライド+dataスライドが同じ文言の繰り返しになっていた
**深刻度**: low（差し替え不要だが視聴体験が悪い）

## 事象

3/28 19:00投稿のShort（旧式レイアウト障害で差し替え再投稿した動画）で、サムネフレームの文言がhookとdataのスライドテキストと重複していた。

- サムネフレーム（0.5秒）: 「暴落」+「暴落後1年、平均＋25%」（黄色＋白テキスト）
- slide_01（hook）: 「暴落」（赤テキスト）
- slide_03（data）: 「暴落後1年 平均＋25%」（青テキスト）

動画を見ると、最初の数秒で「暴落」「暴落後1年、平均＋25%」が3回表示される状態。

## 直接原因

`slide_gen.py` の `_make_thumbnail_text_v2()` ステップ3aで「hook+dataの組み合わせ」を生成する際、hookテキスト「暴落」がdataテキスト「暴落後1年、平均＋25%」に**含まれている**ことを検出せずそのまま結合していた。

タイトル「暴落が怖い。でもバフェットはそこで買っていた。」の処理フロー:
1. ステップ1（句点分割）: line2が12文字超でスキップ
2. ステップ2（短タイトル）: 18文字超でスキップ
3. **ステップ3a（hook+data結合）**: hook「暴落」(2文字) + data「暴落後1年、平均＋25%」(11文字) → total=13で条件マッチ → 採用

## 間接原因

ステップ3aの結合条件が文字数のみで、**内容の重複チェック（部分一致）**がなかった。

## 恒久対応

`slide_gen.py` の `_make_thumbnail_text_v2()` ステップ3aに部分一致チェックを追加:

```python
# 修正前
if data_text and hook_text and len(hook_text) <= 12 and len(data_text) <= 12:
    total = len(hook_text) + len(data_text)
    if 8 <= total <= 20:
        return f"{hook_text}\n{data_text}"

# 修正後
if data_text and hook_text and len(hook_text) <= 12 and len(data_text) <= 12:
    if hook_text not in data_text and data_text not in hook_text:
        total = len(hook_text) + len(data_text)
        if 8 <= total <= 20:
            return f"{hook_text}\n{data_text}"
```

hookがdataに含まれる場合はステップ3b（data単体）や3d（resolve）にフォールバックする。

## 影響範囲

キュー内62本を全数チェック済み → 同じパターンの動画はなし（今回の1本のみ）。

## 再発防止策

| 間接原因 | 対策 |
|---|---|
| hook+data結合時の部分一致チェック不在 | `hook_text not in data_text` ガード追加（実装済み） |
