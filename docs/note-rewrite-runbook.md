# note記事リライト運用手順書

## 1. 概要

この手順書は、**noteで公開済み・予約投稿中の記事のタイトルと本文を、Playwrightで一括更新する**ための運用手順をまとめたものです。

### できること
- 公開済み記事のタイトル更新
- 公開済み記事の本文更新
- 予約投稿中の記事のタイトル更新
- 予約投稿中の記事の本文更新
- Markdownファイルを元にした一括反映

### 使う場面
- SEOリライト
- 誤字脱字の一括修正
- 見出し構成の変更
- 冒頭文の差し替え
- 定型文の一括変更

### 前提
- noteにはブラウザでログイン済み
- Chromiumの永続化コンテキストを使う
- 記事の特定には **note key** を使う
- 保存は必ず **「公開に進む」→「更新する」または「予約投稿」**

---

## 2. 事前準備

### 2-1. 環境

- Python 3.9
- Playwright（sync API）
- macOS
- Chromium
- 永続化コンテキスト保存先: `.note_browser/`

### 2-2. note key の取得方法

#### 重要
**記事の特定はタイトル文字列でやらない。必ず note key を使う。**

タイトルで照合すると、以下の事故が起きる。
- シート上のタイトルと実際のタイトルがずれる
- 旧タイトルと新タイトルが混在する
- 類似タイトルで別記事を誤更新する

#### 取得元
Googleシートの note 管理シート I列（URL）

#### URL例
```
https://note.com/gachiho_motive/n/nab06c9c68ffa
```

抽出される key: `nab06c9c68ffa`

#### 使用する既存関数
```python
# note_image_replace.py
_get_articles_from_sheet()
```

#### エディタURL
```
https://editor.note.com/notes/{note_key}/edit/
```

---

### 2-3. ローカルファイルの準備

更新内容は Markdown ファイルで管理する。

#### 推奨形式

```markdown
# 新タイトル

**冒頭文**

---

## 見出し1

本文...

---

## 見出し2

本文...

---

## よくある質問

**Q. ...**
A. ...

---
もし今つらい夜なら、この内容の12秒版もYouTube Shorts「ガチホのモチベ」で配信しています。
```

#### ルール
- 1行目の `#` 付き行を新タイトルとして使う
- 2行目以降を本文として使う
- 本文は Markdown → note用HTML に変換して挿入する

#### HTML変換

`note_publish.py` の `_markdown_to_note_html()` を使う

変換ルール:
- `## 見出し` → `<h3>`
- `**太字**` → `<b>`
- `---` → `<hr>`
- 通常行 → `<p>`
- 空行 → `<p><br></p>`

---

## 3. 実行手順

### 3-1. ログイン確認

最初に、noteにログイン済みのブラウザ状態を確認する。

```bash
python update_note_seo.py --login
```

確認すること:
- noteの編集画面が開ける
- ログイン画面に飛ばされない
- `.note_browser/` にログイン状態が保存されている

---

### 3-2. ドライラン

本更新の前に、対象記事と更新内容の対応が正しいか確認する。

```bash
python update_note_seo.py --dry-run
```

確認すること:
- 更新対象の記事数
- 各記事の note key
- 新タイトル
- 使用する Markdown ファイル名

---

### 3-3. 本実行

```bash
python update_note_seo.py
```

更新処理の流れ:
1. ローカル Markdown から新タイトルと本文を読み込む
2. `editor.note.com/notes/{note_key}/edit/` を開く
3. タイトルを差し替える
4. 本文を全選択 → 削除 → HTML再入力
5. 変更検知用のダミー入力を入れる
6. Escape
7. 「公開に進む」
8. 「更新する」または「予約投稿」
9. 次の記事へ進む

---

## 4. 更新処理の実装ルール

### 4-1. タイトル更新

```python
title_el = page.wait_for_selector('textarea[placeholder="記事タイトル"]', timeout=10000)
title_el.click()
title_el.evaluate("el => el.select()")
time.sleep(0.5)
page.keyboard.press("Backspace")
time.sleep(0.5)
title_el.fill(new_title)
time.sleep(1)
```

ポイント:
- `fill()` の前に必ず全選択して消す
- 置換ではなく「入れ直す」前提で扱う

---

### 4-2. 本文更新

```python
body_el = page.wait_for_selector('div.ProseMirror[role="textbox"]', timeout=10000)
body_el.click()
time.sleep(0.5)
page.keyboard.press("Meta+a")
time.sleep(0.3)
page.keyboard.press("Backspace")
time.sleep(0.5)
page.evaluate(
    """html => { document.execCommand('insertHTML', false, html); }""",
    body_html,
)
time.sleep(1)
```

ポイント:
- 本文は手打ちではなくHTML挿入で置き換える
- 置換前に必ず `Meta+a` → `Backspace`

---

### 4-3. 変更検知を確実にする

**重要:** 本文挿入だけでは、note側が変更を検知せず、保存画面で「更新する」が出ないことがある。

必須のダミー入力:

```python
page.keyboard.press("End")
time.sleep(0.2)
page.keyboard.type(" ")
time.sleep(0.2)
page.keyboard.press("Backspace")
time.sleep(0.5)
```

---

### 4-4. 保存

```python
page.keyboard.press("Escape")
time.sleep(1)

publish_nav = page.wait_for_selector('button:has-text("公開に進む")', timeout=20000)
publish_nav.click()
time.sleep(2)

try:
    page.wait_for_load_state("networkidle", timeout=10000)
except Exception:
    pass

time.sleep(2)

# 公開済みは「更新する」、予約投稿は「予約投稿」
update_btn = page.wait_for_selector(
    'button:has-text("更新する"), button:has-text("予約投稿")',
    timeout=10000,
)
update_btn.click()
time.sleep(5)
```

**「下書き保存」は絶対に使わない。** 過去に「下書き保存」→「予約投稿」で20記事が404になる事故があった。

---

## 5. 連続実行の安全策

10本以上を連続処理すると、ページ状態やセッションが不安定になることがある。

ルール:
- 各記事の更新後に **8秒待つ**
- **2〜3本ごと** に `page.close()` → `context.new_page()` でページ再生成
- 失敗時は **30秒待って** page を作り直す

---

## 6. トラブルシューティング

### 6-1. 「更新する」ボタンが見つからない

主な原因:
- 「公開に進む」の先に本当に遷移していない
- note側が本文変更を検知していない
- 予約投稿記事で「更新する」ではなく「予約投稿」が出ている
- セッションやページ状態が劣化している

対処:
1. ダミー入力が入っているか確認
2. 失敗時にデバッグ情報を採取
3. 「更新する」と「予約投稿」の両方を待つ
4. 30秒待機して page を再生成して再実行

### 6-2. タイムアウトしたので timeout を延ばしたくなる

**先に「その要素が本当に存在するか」を確認する。**

---

## 7. デバッグ手順

失敗時は必ず以下を採取する。

```python
print(page.url)
print(page.title())
print(page.locator("button").all_text_contents())
page.screenshot(path="debug.png", full_page=True)
html = page.content()
Path("debug.html").write_text(html, encoding="utf-8")
```

---

## 8. やってはいけないこと

| 禁止事項 | 理由 |
|---------|------|
| 「下書き保存」で保存する | 20記事が404になる事故が起きた |
| タイトル文字列で記事を照合する | シートと実際のタイトルがずれる |
| noteの記事一覧ページをスクレイピングする | URL構造が変わって使えなくなる |
| タイムアウト延長だけで解決しようとする | 存在しない要素を待っている可能性がある |
| デバッグ情報なしでリトライする | 原因が分からなくなる |

---

## 9. 技術リファレンス

### セレクタ一覧（2026-03-19 動作確認済み）

| 要素 | セレクタ |
|------|---------|
| タイトル入力欄 | `textarea[placeholder="記事タイトル"]` |
| 本文エディタ | `div.ProseMirror[role="textbox"]` |
| 公開設定へ | `button:has-text("公開に進む")` |
| 保存（公開済み記事） | `button:has-text("更新する")` |
| 保存（予約投稿記事） | `button:has-text("予約投稿")` |

### 使用する既存関数

```python
from note_publish import _launch_browser, _close_browser, _markdown_to_note_html
from note_image_replace import _get_articles_from_sheet
```

---

## 10. 運用の核（3つだけ覚える）

1. **記事の識別は note key**
2. **本文更新後にダミー入力で変更検知を起こす**
3. **保存は「公開に進む」→「更新する/予約投稿」**
