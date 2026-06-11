---
id: incident-20260407-yt-publish-media-missing
date: 2026-04-07
project: youtube-auto
severity: medium
status: resolved
tags:
  - publish
  - media-files
  - disk-cleanup
services:
  - youtube
components:
  - auto_publish.py
  - done/
root_causes:
  - ディスク節約でメディアファイル削除後、キューが削除済みフォルダを参照
cross_project: false
related_incidents:
  - incident-20260331-google-token-expired
lessons:
  - メディアファイル削除前に publish_queue との整合性を確認する仕組みが必要
---

# Incident: YouTube投稿失敗 — done/配下のメディアファイル消失

**日付**: 2026-04-07
**影響**: 当日07:00のYouTube Shorts自動投稿が未実行（1本欠損）
**深刻度**: medium（1日分の投稿遅延、データ損失なし）

## 事象

1. 07:00 の `auto_publish_youtube` launchd ジョブが Google OAuth トークン期限切れでエラー終了
2. トークンを手動 refresh 後、`auto_publish.py --platforms youtube --dry-run` を実行
3. キュー先頭から順に候補を探索:
   - 1本目・2本目: サムネ近接チェックでスキップ（「退場しない人だけが勝つ」が直近と一致）
   - 3本目: `done/20260313_223041` が選択されたが、受け入れテスト失敗
4. 失敗理由: output.mp4、slide_01〜05.png、audio_01〜05 が全て存在しない
5. 調査の結果、`done/` 配下の全フォルダでメディアファイル（動画・スライド・音声）が消失。テキスト系ファイル（transcript.json, social_captions.json, subtitles.srt, note_article.md）のみ残存
6. キュー内34エントリすべてが投稿不能状態

## 直接原因

- OAuthトークン期限切れ（第1障害）
- done/ 配下のメディアファイルが存在しない状態で publish_queue がそれらのフォルダを参照している（第2障害）

## 間接原因

- ディスク節約のためメディアファイルを削除した際、publish_queue.json との整合性チェックが行われなかった
- publish_queue は done/ 内のフォルダ名（文字列）のみを保持しており、実ファイルの存在を投稿直前まで検証しない

## 暫定対応

- トークンは手動 refresh 済み（valid: True, expiry: 2026-04-07 00:37:36 UTC）
- YouTube投稿は未実施（メディアファイル再生成が必要）

## 解決

- publish_queue.json を空配列にリセット
- publish-youtube-0700 を enabled: false + plist unload で完全停止
- 投稿再開はせず、analytics 2件のみ継続運用とする判断

## 再発防止策

| 間接原因 | 対策 |
|---|---|
| メディア削除とキューの不整合 | done/ のメディア削除前に publish_queue との突合チェックを行う運用ルール化 |
| 投稿直前まで実ファイル未検証 | auto_publish.py の受け入れテストは機能しているが、キュー全体の健全性を事前チェックする仕組み（queue-status skill等）にメディア存在チェックを追加 |
