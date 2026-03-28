---
date: 2026-03-28
severity: medium
category: note-prosemirror
affected: youtube-auto
cross_project: true
status: resolved
---

# note 記事冒頭にカードリンクが誤挿入される

## 概要

`_append_card_links()` で記事末尾にカードリンクを差分追加する際、ProseMirror エディタにフォーカスを与えずに `Meta+End` を実行したため、カーソルがデフォルトの冒頭位置のまま URL がペーストされ、関連リンクカードが記事冒頭に挿入された。

末尾の正規カードはそのまま残っているため、冒頭と末尾に同じカードが二重に存在する状態。

## 影響範囲

- **3/27 21:30**: 24記事に合計38カード（冒頭に誤挿入）
- **3/28 13:00**: 1記事に2カード（冒頭に誤挿入）
- **合計**: 25記事

3/25-3/26 は別のエラー（TypeError: sheet_no が None）で実行されておらず影響なし。

## 根本原因

`note_article_updater.py` の `_append_card_links()` 関数（534行目）:

```python
# 問題のコード
page.wait_for_selector(body_sel, timeout=10000)  # 存在を待つだけ
page.keyboard.press("Meta+End")  # フォーカスなしで発行 → カーソルは冒頭のまま
```

1. `wait_for_selector` はエディタの存在確認のみで、**クリックしてフォーカスを得ていない**
2. フォーカスなしで `Meta+End` を押しても ProseMirror 内のカーソルは移動しない
3. カーソルがデフォルトの冒頭位置のまま `_paste_url_card()` が実行される

## 背景

- 3/27 の commit `8758aae` で `note_publish.py`（新規投稿フロー）に `_focus_body_end()` ヘルパーを追加したが、`note_article_updater.py`（差分追加フロー）には未適用だった
- `_append_card_links` はカード挿入位置の検証がなく、ログに「OK」と出ていても位置ずれを検知できなかった

## 暫定対応

`repair_top_cards.py` で冒頭の誤カードを自動削除:

```bash
python repair_top_cards.py --dry-run    # 確認
python repair_top_cards.py              # 実行
```

## 恒久対応

`_append_card_links()` を修正:
1. `handle_draft_dialog()` / `handle_multi_edit_dialog()` の呼び出し追加
2. `body.click()` でフォーカスを取得してから `Meta+ArrowDown` で末尾移動

## 教訓

- **エディタ操作前は必ず `click()` でフォーカスを取得する** — `wait_for_selector` は存在確認であり、フォーカス取得ではない
- **カード挿入後は位置の検証を入れる** — 「挿入成功」と「正しい位置に挿入」は別
- **同じエディタ操作の修正を入れたら、全呼び出し元に適用されているか確認する** — note_publish.py の修正が note_article_updater.py に未適用だった（active-lessons #15 の再発）
