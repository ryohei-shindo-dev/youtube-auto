---
id: incident-2026-04-04-data-slide-text-trailing-plus
date: 2026-04-04
project: youtube-auto
severity: medium
status: resolved
tags:
  - slide_text
  - data_scene
  - truncation
services:
  - youtube
components:
  - script_gen.py
  - scene_linter.py
root_causes:
  - dataのslide_textだけClaude生成値をそのまま通す経路が残っていた
  - 途中切れ判定が日本語語尾中心で、記号終わり（平均+）を危険末尾として扱っていなかった
cross_project: false
related_incidents:
  - incident-2026-03-27-slide-text-dangling
lessons:
  - dataのslide_textも他ロール同様にコード側で再導出し、Claude生成値を信用しすぎない
  - 数値文脈では記号終わりも途中切れとして検知する
---

# Incident: data スライドが「平均+」で切れて表示

**日付**: 2026-04-04
**影響**: YouTube Shorts 1本。data スライドが「暴落後1年のリターン 平均+」となり、数値本体が欠けた。
**深刻度**: medium（視聴体験に影響するが、ユーザー判断により削除再投稿は不要）

## 事象

2026-04-04 時点で確認した公開済み動画で、data シーンの表示テキストが「暴落後1年のリターン 平均+」となっていた。ナレーション本文は `暴落後1年のリターン、平均+25%。` で正常だったため、破損は `slide_text` の生成段階に限られていた。

同系統の既存出力として、以下も確認できた。

- `done/20260402_114512/transcript.json` の data `slide_text`: `暴落後1年のリターン、平均+`
- `done/20260402_114921/transcript.json` の data `slide_text`: `売った翌年のリターン、平均+`
- `done/20260312_170748/transcript.json` の data `slide_text`: `暴落後1年のリターン、平均+`

## 直接原因

`script_gen.py` の `_postprocess_script()` では hook / empathy / resolve / closing はコード側で `slide_text` を再生成していたが、`data` は **Claude が返した `slide_text` をそのまま残す経路** があった。

その結果、Claude が `平均+` のような途中切れを返した場合でも、そのまま `transcript.json` に保存され、スライド生成に使われていた。

## 間接原因

- `_safe_truncate_slide_text()` の危険末尾判定が日本語語尾中心で、`+` `＋` `/` などの **記号終わり** を未検知だった
- `scene_linter.py` でも `slide_text` の記号終わりをエラー扱いしておらず、候補選別で弾けなかった

## 対応

1. `script_gen.py` に `_data_slide_from_text()` を追加
2. data シーンの `slide_text` を毎回 `text` から再導出するよう変更
3. `_DANGLING_ENDINGS` に `+` `＋` `-` `−` `/` `／` と数値文脈で危険な語尾を追加
4. `scene_linter.py` に「記号終わりの slide_text」をエラーとするルールを追加

## 再発防止策

| 間接原因 | 対策 |
|---|---|
| data だけ Claude 生成 `slide_text` を信用していた | `data` もコード側で再導出に統一 |
| 記号終わりを途中切れと見なしていなかった | `_DANGLING_ENDINGS` と linter に記号終わり判定を追加 |
| 候補選別で検知できなかった | `scene_linter.py` で `平均+` 系をエラー化 |
