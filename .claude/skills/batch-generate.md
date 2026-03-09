# バッチ生成スキル

Shorts 動画をまとめて生成するワークフロー。

## 手順

1. 現在の在庫数を確認
   ```bash
   python -c "import json; d=json.load(open('posting_schedule.json')); total=len(d); published=sum(1 for x in d if x.get('published')); print(f'在庫: {total}本 / 投稿済み: {published}本 / 残り: {total-published}本')"
   ```

2. バッチ生成を実行
   ```bash
   source venv/bin/activate
   python batch_gen.py --count <本数>
   ```

3. 生成結果を確認
   - `posting_schedule.json` に新規エントリが追加されているか
   - `pending/` に新しいフォルダが作られているか

4. 品質チェック（任意）
   ```bash
   python review_gen.py
   # クリップボードにコピーされた内容を ChatGPT に貼り付けてレビュー
   ```

## 注意点
- Python 3.9 互換: `from __future__ import annotations` を忘れない
- voice_gen の読み辞書に未登録の単語がないか、音声を抽出確認
- 1 回の生成で失敗しても残りは続行される
