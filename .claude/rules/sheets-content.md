---
description: 投稿管理シートの照合ルール（content_id主キー・A列タイトル検索禁止）
paths:
  - "sheets.py"
  - "analytics_*.py"
  - "auto_publish.py"
  - "batch_*.py"
---

# 投稿管理シートルール

- 管理シートの照合は **content_id（X列）を使う**（A列・タイトル検索は禁止）
- Sheets API は `valueRenderOption: "UNFORMATTED_VALUE"` を明示
