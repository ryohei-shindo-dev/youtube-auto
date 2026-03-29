---
description: note エディタ操作の安全ルール（press_sequentially必須・insertHTML禁止）
paths:
  - "note_gen.py"
  - "note_image_gen.py"
  - "note_articles/**"
  - "**/note_*.py"
  - "**/ops_note/**"
---

# note エディタ操作ルール

- note エディタ操作は **`press_sequentially` 必須**（insertHTML/fill/innerHTML 禁止）
- LLM生成テキストは `。**。` パターンを後処理で修正
- Markdown記法（`- `, `**`）は入力前に除去
- note エディタを開いたら**下書きダイアログを必ず処理**（公開版を選択）
- note 修正したら **dev-stack-watch にも同じ実装がないか確認**
- 予防原則: `~/ops-hub/docs/incidents/active-lessons.md` の #16-20
- 詳細: `~/ops-hub/docs/incidents/categories/note-prosemirror-pitfalls.md`
- 共通ライブラリ: `~/ops-hub/packages/ops_note/`（pip install -e 済み）
