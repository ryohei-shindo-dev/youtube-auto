---
id: incident-2026-03-27-note-link-card-position
date: 2026-03-27
project: youtube-auto
severity: high
status: active
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
cross_project: false
related_incidents:
  - incident-2026-03-23-bold-marker-relapse
  - incident-2026-03-20-note-link-cards
lessons:
  - insertHTMLで大きなHTMLを一括挿入するとProseMirrorのカーソル位置が不定になる
  - 小ブロック分割方式（_split_body_into_blocks）を使うべき
---

# Incident: noteリンクカードが本文途中に表示される

**日付**: 2026-03-27
**影響**: note_add_13「商品数を減らすと気持ちが整う話」(n89e9fc715f94) でリンクカードが本文冒頭付近に割り込み。同様の問題が最大25記事に存在する可能性
**深刻度**: high（読者の動線に悪影響）

## 事象

note記事「商品数を減らすと気持ちが整う話」で、「あわせて読みたい」のリンクカード（勉強するほど迷う投資脳を、シンプルに戻す方法）が本文の途中に表示されている。本来は記事末尾に配置されるべき。

## 直接原因

`note_publish.py::_insert_body_with_cards()` が本文HTML全体を1つの大きなブロックとして `insertHTML` で挿入した後、カーソル位置が本文途中に残る。その状態で後続のカードURLが入力されるため、カードが本文途中に配置される。

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

URL行を含む96記事中、25記事で「URL行の後にテキストが続く」構造がある。これらの記事でリンクカードの位置ずれが発生している可能性がある。

対象:
- note_01〜note_15（初期15本）: URL後に「YouTube Shorts案内文」あり
- note_add_07, note_add_15, note_add_22
- note_ai_03〜note_ai_09（AI記事7本）: URL後に「投資で気持ちが揺れやすい日に〜」テキストあり

## 暫定対応

なし（公開済み記事の状態を確認中）

## 恒久対応

### 修正1: カーソル位置の強制移動（全経路の安全策）

`_insert_body_blocks()` のinsertHTML直後に `Meta+ArrowDown` でカーソルを末尾に強制移動:

```python
# note_publish.py _insert_body_blocks() 内
page.evaluate("""html => {
    document.execCommand('insertHTML', false, html);
}""", block["html"])
time.sleep(0.5)
# 追加: カーソルを末尾に強制移動
page.keyboard.press("Meta+ArrowDown")
time.sleep(0.2)
```

### 修正2: 小ブロック分割方式への切替（新規投稿）

`post_article()` と `note_publish_additional.py` で `_split_body_into_blocks()` を使用:

```python
# Before: 1つの巨大HTMLブロック
body_html, url_lines = _split_body_for_note(body)
_insert_body_with_cards(page, body_html, url_lines)

# After: 空行区切りの小ブロック（テキスト/カード交互）
blocks = _split_body_into_blocks(body)
_insert_body_blocks(page, blocks)
```

### 修正3: 末尾フォーカスヘルパー（ChatGPTレビュー指摘反映）

Meta+ArrowDown単発ではなく `_focus_body_end()` ヘルパーを新設。3段階で末尾移動を保証:
1. body再クリック（フォーカスをbodyに確定）
2. Meta+ArrowDown（macOS末尾移動）
3. JS fallback（最終段落にSelection.rangeを設定）

### 修正4: 挿入後の順序検証（ChatGPTレビュー指摘反映）

`_verify_card_order()` を新設。`_insert_body_blocks()` の末尾で自動実行:
- エディタDOM内の埋め込みカードURLを抽出
- 期待するURL順序と比較
- カード数不一致・順序ずれを警告出力

### 修正5: 境界の空白規則を明示化

html→html / html→card / card→html / card→card の4パターンのEnter制御をコメントで固定。

## 再発防止策

| 間接原因 | 対策 |
|---|---|
| insertHTMLでカーソル位置が不定 | _focus_body_end() ヘルパーで3段階末尾移動 |
| カーソル移動の成功が未検証だった | _verify_card_order() で挿入後に順序検証 |
| 大きなHTMLを1ブロックで挿入 | _split_body_into_blocks()で小ブロック分割に統一 |
| _split_body_into_blocks()が未使用だった | post_article / note_publish_additional を切替済み |
| 境界の空白規則が暗黙的だった | 4パターンの明示ルールをコメント化 |
| 既投稿25記事の位置ずれ | 修正後にfix-link-cardsで段階的に再投入（3→5→10→残り） |
