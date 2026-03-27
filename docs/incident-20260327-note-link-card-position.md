---
id: incident-2026-03-27-note-link-card-position
date: 2026-03-27
project: youtube-auto
severity: high
status: reference
tags:
  - note
  - playwright
  - insertHTML
services:
  - note.com
components:
  - note_publish.py
  - note_publish_additional.py
root_causes:
  - insertHTML後のカーソル位置不定
  - 本文全体を1つのHTMLブロックとして挿入する設計
cross_project: true
related_incidents:
  - incident-2026-03-23-bold-marker-relapse
  - incident-2026-03-20-note-link-cards
lessons:
  - insertHTMLで大きなHTMLを一括挿入するとProseMirrorのカーソル位置が不定になる
  - 小ブロック分割方式（_split_body_into_blocks）を使うべき
  - UI操作のショートカットを「保証」として扱わず、挿入後の順序検証で正しさを担保する
  - 修正の段階実施（3→5→10→残り）で事故半径を抑える
---

# Incident: noteリンクカードが本文途中に表示される

**日付**: 2026-03-27
**影響**: note_add_13「商品数を減らすと気持ちが整う話」(n89e9fc715f94) でリンクカードが本文冒頭付近に割り込み。横展開調査で24記事に同様の問題を確認
**深刻度**: high（読者の動線に悪影響）
**対応完了**: 2026-03-27（コード修正 + 24記事再投入）

## 事象

note記事「商品数を減らすと気持ちが整う話」で、「あわせて読みたい」のリンクカード（勉強するほど迷う投資脳を、シンプルに戻す方法）が本文の途中に表示されている。本来は記事末尾に配置されるべき。

## 直接原因

`note_publish.py::_insert_body_with_cards()` が本文HTML全体を1つの大きなブロックとして `insertHTML` で挿入した後、ProseMirrorのカーソル位置が本文途中に残る。その状態で後続のカードURLが入力されるため、カードが本文途中に配置される。

```python
# 問題のあるコード（修正前）
blocks = [
    {"type": "html", "html": "...本文全体の巨大HTML..."},
    {"type": "card", "url": "https://note.com/..."},
]
# insertHTML → カーソル位置不定 → card URLが途中に入力される
```

## 間接原因

1. `_split_body_for_note()` がHTML部分とURL行を分離するが、HTMLは1つの巨大文字列のまま
2. `_split_body_into_blocks()` は空行区切りで小ブロック分割する正しい関数だが、未使用だった
3. `document.execCommand('insertHTML')` はProseMirrorエディタでカーソル位置が保証されない

## 横展開調査

URL行を含む96記事中、「URL行の後にテキストが続く」構造の24記事でリンクカードの位置ずれが発生していた。

対象:
- note_01〜note_15のうち14本（初期記事）: URL後に「YouTube Shorts案内文」あり
- note_add_07, note_add_15, note_add_22（追加記事3本）
- note_ai_03〜note_ai_09（AI記事7本）: URL後に「投資で気持ちが揺れやすい日に〜」テキストあり

## 恒久対応

### 修正1: 小ブロック分割方式への切替

`post_article()`・`note_publish_additional.py`・`_repair_single_article()` で `_split_body_into_blocks()` を使用。本文を空行区切りの小ブロックに分割し、テキストとカードを正しい順序で交互に挿入する。

```python
# Before: 1つの巨大HTMLブロック
body_html, url_lines = _split_body_for_note(body)
_insert_body_with_cards(page, body_html, url_lines)

# After: 空行区切りの小ブロック（テキスト/カード交互）
blocks = _split_body_into_blocks(body)
_insert_body_blocks(page, blocks)
```

### 修正2: 末尾フォーカスヘルパー（ChatGPTレビュー指摘反映）

Meta+ArrowDown単発ではなく `_focus_body_end()` ヘルパーを新設。3段階で末尾移動を保証:
1. body再クリック（フォーカスをbodyに確定）
2. Meta+ArrowDown（macOS末尾移動）
3. JS fallback（最終段落にSelection.rangeを設定）

### 修正3: 挿入後の順序検証（ChatGPTレビュー指摘反映）

`_verify_card_order()` を新設。`_insert_body_blocks()` の末尾で自動実行:
- エディタDOM内の埋め込みカードURLを抽出
- 期待するURL順序と比較
- カード数不一致・順序ずれを警告出力

### 修正4: 境界の空白規則を明示化

html→html / html→card / card→html / card→card の4パターンのEnter制御をコメントで固定。

### 修正5: _repair_single_article() の引数変更

`(body_html, url_lines)` → `(body)` に変更。生Markdown本文を受け取り、内部で `_split_body_into_blocks()` を呼ぶ方式に統一。呼び出し元の `do_repair()` / `do_repair_add()` も合わせて修正。

## 既投稿記事の修正

`repair_link_cards.py` で24記事を段階的に再投入:

| 段階 | 件数 | 結果 | 備考 |
|------|------|------|------|
| 1 | 3本 | 3/3成功 | ブロック挿入正常 |
| 2 | 5本 | 5/5成功 | ブロック挿入正常 |
| 3 | 10本 | 10/10成功 | AI記事1本でカード検証警告（DOM遅延） |
| 4 | 6本 | 6/6成功 | AI記事全般でカード変換未確認警告 |

**合計: 24本全て成功、失敗0本**

カード検証警告について: AI記事（note_ai系）でリンクカードのDOM検出が0件になる警告が出た。noteのカード変換がiframe以外の方式（遅延レンダリング等）を使っている可能性がある。「カード変換成功」ログは出ているため、投入自体は正常と判断。公開ページでの目視確認を推奨。

## 再発防止策

| 間接原因 | 対策 |
|---|---|
| insertHTMLでカーソル位置が不定 | _focus_body_end() ヘルパーで3段階末尾移動 |
| カーソル移動の成功が未検証だった | _verify_card_order() で挿入後に順序検証 |
| 大きなHTMLを1ブロックで挿入 | _split_body_into_blocks()で小ブロック分割に統一 |
| _split_body_into_blocks()が未使用だった | post_article / note_publish_additional / repair を切替済み |
| 境界の空白規則が暗黙的だった | 4パターンの明示ルールをコメント化 |
| 修正の爆発半径が大きかった | 段階実施（3→5→10→残り）をデフォルト手順に |

## 残課題

- AI記事のカードDOM検証精度の改善（`_verify_card_order` のセレクタ拡充）
- 公開ページでの24記事の目視確認
