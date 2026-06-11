---
id: incident-2026-03-27-slide-text-dangling
date: 2026-03-27
project: youtube-auto
severity: medium
status: reference
tags:
  - slide_text
  - truncation
  - japanese-nlp
services:
  - youtube
components:
  - script_gen.py
  - slide_gen.py
root_causes:
  - empathyのslide_text生成で[:10]の単純切り詰めを使用しており日本語の語尾途中切れを考慮していなかった
cross_project: false
related_incidents:
  - incident-20260320-slide-text-truncated
  - incident-20260324-slide-text-truncated-n
lessons:
  - 日本語の文字数切り詰めは数字だけでなく活用語尾・促音・助動詞の途中切れも考慮が必要
  - slide_textの全経路に同じ安全化関数を通すべき
---

# Incident: slide_textが動詞途中（促音「っ」）で切れて表示

**日付**: 2026-03-27
**影響**: 3/27 7:00投稿のYouTube Shorts 1本。empathyスライドが「あなた、もう長くやっ」と不自然な表示。
**深刻度**: medium（視聴者体験に影響するが、再生数は伸びており実害は限定的）

## 事象

3/27投稿の動画（フォルダ: 20260312_173903）のempathyシーンで、スライドテキストが「あなた、もう長くやっ」と表示された。元テキストは「あなた、もう長くやってますよね。」で、動詞「やって」の途中（促音「っ」）で切れている。

## 直接原因

`script_gen.py` line 1390:
```python
s["slide_text"] = s.get("text", "").rstrip("。？！ ")[:10]
```

empathyシーンでopeningフレーズがない場合、ナレーションテキストを**10文字で単純切り詰め**していた。日本語の語尾・活用形の途中切れを一切考慮していなかった。

## 間接原因

- 2026-03-16に数字途中切れ防止（`_single_sentence_slide_text`）は修正済みだったが、empathyの`[:10]`切り詰めはこの関数を経由しておらず、修正が漏れていた
- slide_textの生成経路が複数あり（Claude API直接返却 / `_single_sentence_slide_text` / `[:10]`直接切り詰め / 固定フレーズ）、安全化が統一されていなかった

## 暫定対応

なし（再生数が伸びていたため差し替えせず）

## 恒久対応

commit `915cde5` で以下を実装:

1. **`_safe_truncate_slide_text()` 新設**（B+D+A三段構え）
   - 危険末尾パターン辞書（`_DANGLING_ENDINGS`）: 促音・拗音・活用語尾・助動詞途中など
   - 安全切れ目文字（`_SAFE_BREAK_CHARS`）: 助詞・句読点
   - 処理: max_lenで切る → 危険末尾なら+3文字まで前方延長 → 失敗なら手前の安全切れ目まで戻す

2. **empathyの`[:10]`を`_safe_truncate_slide_text(raw, max_len=10)`に置換**

3. **`_single_sentence_slide_text()`を`_safe_truncate_slide_text()`経由に変更**

4. **プロンプト修正**（Shorts・長尺両方）: 「動詞・助動詞・否定の途中で切らない」指示を追加

## 再発防止策

| 間接原因 | 対策 |
|---|---|
| empathyの`[:10]`が安全化関数を通っていなかった | `_safe_truncate_slide_text()`に統一（実装済み） |
| slide_text生成経路が複数で安全化が不統一 | 全経路を`_safe_truncate_slide_text()`経由に変更（実装済み） |
| 数字以外の途中切れパターンが未対応だった | 危険末尾辞書で促音・活用語尾・助動詞等を網羅（実装済み） |
| Claude APIが不自然なslide_textを返す可能性 | プロンプトに明示的な禁止指示を追加（実装済み） |
