---
id: incident-2026-03-28-old-layout-published
date: 2026-03-28
project: youtube-auto
severity: medium
status: active
tags:
  - slide-layout
  - publish-queue
  - quality-gate
services:
  - youtube
components:
  - slide_gen
  - auto_publish
root_causes:
  - v2再生成漏れ（3/13初期バッチの横長写真レイアウトが残存）
cross_project: false
related_incidents:
  - incident-20260324-landscape-photo-slide
lessons:
  - publish_queue投入前にスライドレイアウトの視覚的検証（thumbnail_frame.png存在チェック）を行うべき
---

# Incident: 旧式レイアウト（v2 landscape）の動画がYouTubeに公開された

**日付**: 2026-03-28
**影響**: YouTube Shorts 1本（19:00投稿）が旧式レイアウトで公開。チャンネルの統一感を損なう
**深刻度**: medium

## 事象

3/28 19:00に自動投稿されたYouTube Short（フォルダ `20260305_122524`、タイトル「暴落が怖い。でもバフェットはそこで買っていた」）が、旧式の「横長写真上半分＋テキスト下半分＋赤線セパレータ」レイアウト（v2 landscape）で公開された。

- YouTube URL: https://youtube.com/shorts/S-0OzXmSU0Q
- Video ID: S-0OzXmSU0Q
- スライド生成日: 2026-03-13 12:55（v2導入直後）
- `thumbnail_frame.png` が存在しない（v2 portrait再生成がされていない証拠）

## 直接原因

フォルダ `20260305_122524` のスライドが 3/13 12:55 に生成されており、v2レイアウト導入直後の初期バッチで**横長写真が割り当てられた**。この時点では縦型写真限定フィルタ（h/w >= 0.6 → 縦型のみ、3/24修正）が未実装だったため、横長写真による split layout（写真55%＋テキスト45%）が適用された。

その後の一括再生成（`_regen_v2_portrait.py`）でこのフォルダが**再生成対象から漏れた**。

## 間接原因

1. **レイアウト品質ゲートの不在**: `publish_queue.json` への投入時・投稿時にスライドレイアウトの視覚的検証がない
2. **`thumbnail_frame.png` 存在チェックの不在**: v2 portrait再生成済みの動画は必ず `thumbnail_frame.png` を持つが、これをpreflight checkで検証していなかった
3. **再生成スクリプトの対象管理が手動**: `_regen_v2_portrait.py` はpublish_queue.jsonベースで処理するが、キューから外れたり後から追加された動画は漏れる

## 暫定対応

1. YouTube から該当動画（S-0OzXmSU0Q）を削除
2. スライド+サムネイル+動画を v2 portrait で再生成
3. 再投稿

## 恒久対応

1. `auto_publish.py` の preflight check に `thumbnail_frame.png` 存在チェックを追加
2. `thumbnail_frame.png` がないフォルダは投稿をスキップしログに警告を出す

## 再発防止策

| 間接原因 | 対策 |
|---|---|
| thumbnail_frame.png チェック不在 | auto_publish.py preflight に存在チェック追加 |
| キュー内の旧式レイアウト残存 | 今回の全数調査で残り62本は全て正常を確認済み |
| 再生成対象の手動管理 | 今後のバッチ生成は全て use_photo=True + 縦型限定で生成されるため再発しない |
