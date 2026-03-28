---
id: incident-2026-03-28-note-card-top-incomplete-repair
date: 2026-03-28
project: youtube-auto
severity: medium
status: active
tags:
  - note
  - prosemirror
  - card-link
  - cursor-position
services:
  - note
components:
  - note_article_updater
root_causes:
  - _append_card_linksのカーソル末尾移動が不確実（Meta+ArrowDownがProseMirrorで信頼できない）
  - repair_top_cardsの修復が不完全（Sheet 78で冒頭カードが残存）
cross_project: true
related_incidents:
  - incident-20260320-note-link-cards
  - incident-20260323-note-404-mass
lessons:
  - ProseMirrorでのカーソル移動はキーボードショートカットに依存せず、JS でSelection APIを使って検証すべき
  - 修復スクリプト実行後は全件の目視確認または自動検証が必要
---

# Incident: noteリンクカード冒頭誤挿入の修復不完全

**日付**: 2026-03-28
**影響**: 25記事中少なくとも1記事（Sheet 78）でリンクカードが記事冒頭に残存。他にも未修復の記事がある可能性
**深刻度**: medium

## 事象

3/28 12:30に公開されたnote記事「投資初心者が怖くて始められない理由」（Sheet 78、`n779de44278ed`）で、関連リンクが記事末尾ではなく本文の冒頭付近に表示されている。

スクリーンショットで確認された状態:
- 記事ヘッダー画像の直後にURLテキスト `https://note.com/gachiho_motive/n/n4962f0177e3a` が表示
- その下にリンクカード「現金のまま10年置いた100万円」が表示
- 本来は記事末尾の「あわせて読みたい」の後にカード化されて表示されるべき

## 直接原因

1. **3/27〜28の `_append_card_links()` 実行**: `Meta+ArrowDown` でカーソル末尾移動を試みるが、ProseMirrorのフォーカス挙動により**カーソルが冒頭のまま** → URLが記事冒頭に挿入された

2. **修復スクリプトの不完全実行**: `repair_top_cards.py` が作成されたが、Sheet 78の修復が完了していない（冒頭のカードが残存）

## 間接原因

1. `_append_card_links()` がカーソル位置を**検証せずに**URLペーストを実行していた。`body.click()` + `Meta+ArrowDown` は「試みる」だけで、成功を確認していない

2. `Meta+ArrowDown` はProseMirrorエディタで信頼できない操作 — エディタの実装によりキーイベントが正しく処理されないことがある

3. 修復スクリプト実行後の自動検証がない — 修復が成功したかどうかを目視に依存

## 暫定対応

- Sheet 78の記事は手動で修正が必要（冒頭のリンクカード/URLテキストを削除し、末尾に正しく配置）
- 他の影響記事24本の状態確認が必要

## 恒久対応

`_append_card_links()` にカーソル位置の検証ロジックを追加:

```python
# カーソルが末尾にあるかJS Selection APIで検証
is_at_end = page.evaluate("""() => {
    const editor = document.querySelector('.ProseMirror[role="textbox"]');
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return false;
    const range = sel.getRangeAt(0);
    const node = range.startContainer;
    const children = editor.children;
    const lastChild = children[children.length - 1];
    return lastChild.contains(node) || node === editor;
}""")

if not is_at_end:
    # 最後の段落要素を直接クリックしてフォーカス → End キーで末尾へ
    last_el = page.locator(f'{body_sel} > :last-child')
    last_el.click()
    page.keyboard.press("End")
```

## 残対応

- [ ] 影響25記事の現状確認（冒頭にカードが残っているか自動チェック）
- [ ] Sheet 78 の手動修正
- [ ] ops-hub の active-lessons / note-prosemirror-pitfalls に反映

## 再発防止策

| 間接原因 | 対策 |
|---|---|
| カーソル末尾移動の検証なし | JS Selection APIで検証 + フォールバック（最終段落click + End）を追加（実装済み） |
| 修復後の自動検証なし | 今後の修復スクリプトには検証ステップを組み込む |
| Meta+ArrowDownの信頼性 | キーボードショートカットは「移動手段」であり正しさは検証で担保する（active-lesson 21と同じ原則） |
