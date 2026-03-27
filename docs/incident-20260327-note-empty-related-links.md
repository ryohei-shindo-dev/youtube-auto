---
id: incident-2026-03-27-note-empty-related-links
date: 2026-03-27
project: youtube-auto
severity: low
status: reference
tags:
  - note
  - related-links
  - orphaned-heading
services:
  - note
components:
  - note_article_updater.py
  - note_articles
root_causes:
  - 3/23の全量調査でリンクURL除去時に「あわせて読みたい」見出しの除去が漏れた
cross_project: false
related_incidents:
  - incident-20260323-note-404-mass
lessons:
  - リンク除去時は関連する見出し・セクション構造も一緒に除去する
  - 公開済み記事のセクション構造チェックを自動化すべき
---

# Incident: note記事の「あわせて読みたい」見出しだけ残りリンクなし

**日付**: 2026-03-27
**影響**: note記事6本で「あわせて読みたい」の見出しだけ表示され、リンクが空。読者体験を損なう。
**深刻度**: low（表示上の問題のみ、機能的な障害ではない）

## 事象

note記事（n0a93c27a5888 等）で末尾に「あわせて読みたい」とだけ表示され、その下にリンクカードがない状態が発見された。

該当6本:
- note_add_09（投資の勉強をするほど、軸がぶれ）
- note_add_23（今日も引き落とされた。それで十分）
- note_add_26（気づいたら続いていた。それが長）
- note_add_29（他人を見ない日が、いちばん崩れ）
- note_seo_04（月1万円意味ある）
- note_seo_09（つみたて投資枠成長投資枠）

## 直接原因

commit `64cfe09`（2026-03-23）の全量調査で、404記事へのリンクURL行を記事Markdownから除去した際、「あわせて読みたい」の見出し行の除去を忘れた。

## 間接原因

- リンクURL除去のスクリプト/手作業が「URLの行だけ」を対象としており、関連するセクション見出しの有無を確認していなかった
- `_md_to_segments()` にも「URLが後続しない見出しを除去する」ガードがなかった

## 暫定対応

6本のMarkdownファイルから空の「あわせて読みたい」見出しを手動除去。

## 恒久対応

`note_article_updater.py` の `_md_to_segments()` に孤立見出しガードを追加:
- 「あわせて読みたい」(h3)の直後にURLセグメントがない場合、見出しを自動除去
- リンクが非linkableでスキップされた場合でも、見出しだけ残ることを防ぐ

## 再発防止策

| 間接原因 | 対策 |
|---|---|
| URL除去時に見出し除去を忘れた | `_md_to_segments()` に孤立見出しガードを追加（実装済み） |
| セクション構造の整合性チェックがない | 将来的にnote記事のlint（空セクション検出）を追加検討 |
