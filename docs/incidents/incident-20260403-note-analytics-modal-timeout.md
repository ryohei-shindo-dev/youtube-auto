---
id: incident-2026-04-03-note-analytics-modal-timeout
date: 2026-04-03
project: youtube-auto
severity: medium
status: resolved
tags:
  - note
  - analytics
  - playwright
  - modal
services:
  - note
components:
  - note_analytics_collect
  - note/analytics.py
root_causes:
  - note分析画面の前面モーダルを閉じずに期間タブをクリックしていた
cross_project: false
related_incidents: []
lessons:
  - noteの読み取り系ジョブでも、編集系と同様に前面モーダルを毎操作前に明示的に処理する
---

# Incident: note analytics collect が前面モーダルでタイムアウト

**日付**: 2026-04-03
**影響**: 定期実行タスク `note_analytics_collect` が失敗し、`2026-04-03` 分の `note_analytics_log.jsonl` 追記が一時欠落
**深刻度**: medium

## 事象

定期実行 `note_analytics_collect` が以下のエラーで停止した。

```text
playwright._impl._errors.TimeoutError: Locator.click: Timeout 30000ms exceeded.
- waiting for locator("button:has-text(\"月\")").first
- <div role="dialog" aria-hidden="false" class="modal-content-wrapper">...</div> subtree intercepts pointer events
```

note の分析画面で `月` タブを押そうとした際、前面に出ていたモーダルがポインタイベントを奪い、クリックできなかった。

## 直接原因

`note/analytics.py` の `collect_period()` は `button:has-text("月")` を直接クリックしており、前面モーダルの存在を考慮していなかった。

分析ジョブは note 編集系で共通化済みの `dismiss_modals()` 相当処理を持っておらず、モーダル出現時に復旧できなかった。

## 間接原因

1. note 自動化のモーダル対策が `note/ops.py` 側に寄っており、分析ジョブに横展開されていなかった
2. `note_analytics_collect` は通常ジョブ経路でしか動かしておらず、分析画面固有の予期しないモーダルを吸収する再試行設計がなかった
3. ローカル確認時は sandbox 内の headed Playwright 起動が止まるため、手元検証がそのままでは成立しなかった

## 暫定対応

- [x] `note_analytics_collect.py` を sandbox 外で手動再実行
- [x] `2026-04-03T23:23:18` の新規行が `note_analytics_log.jsonl` に追記されたことを確認

## 恒久対応

`note/analytics.py` に以下を追加した。

1. `_dismiss_blocking_dialogs()` で分析画面上の前面モーダルを閉じる
2. `_select_period()` で `週` / `月` / `全期間` のクリック前後にモーダル除去と再試行を入れる
3. 初回 `page.goto("https://note.com/sitesettings/stats")` 後にもモーダル除去を実行する

## 経緯

| 日時 | 事象 |
|------|------|
| 2026-04-03 22:50頃 | `note_analytics_collect` が `月` ボタンクリックの Timeout で失敗 |
| 2026-04-03 23:00頃 | エラーログ確認。`modal-content-wrapper` がクリックを遮っていることを特定 |
| 2026-04-03 23:05頃 | `note/analytics.py` にモーダル除去 + 期間切替再試行を実装 |
| 2026-04-03 23:10頃 | sandbox 内で再実行を試すが、headed Playwright 起動待ちで確認不能 |
| 2026-04-03 23:23 | sandbox 外で `venv/bin/python note_analytics_collect.py` を再実行し成功 |
| 2026-04-03 23:23 | `note_analytics_log.jsonl` へ `2026-04-03` 分の記録追加を確認 |

## 再発防止策

| 間接原因 | 対策 | 状態 |
|---|---|---|
| 分析ジョブにモーダル対策がなかった | 分析画面にも前面モーダル除去処理を追加 | ✅ 実装済み |
| 期間切替が単発クリック依存だった | クリック前後にモーダル除去と再試行を入れる | ✅ 実装済み |
| sandbox 内の headed 検証がそのままでは成立しない | Playwright 実画面確認が必要なときは sandbox 外で再実行する | ✅ 運用確認済み |
