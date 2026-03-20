---
name: quality-review
description: Review generated Shorts or note articles for quality against ガチホのモチベ brand standards. Use when user wants to check content quality, review scripts, or prepare ChatGPT review prompts.
argument-hint: "[shorts|note|folder-name]"
allowed-tools:
  - Read
  - Bash
  - Grep
  - Glob
---

# 品質レビュー

生成済みコンテンツの品質をチェックするワークフロー。

## レビュー観点（優先順位順）

この順番で確認する。上位の問題があれば下位は後回し:

1. **投資助言NG・事実誤認**: 個別銘柄推奨、買い時断定、誇張表現がないか
2. **hook の止まりやすさ**: 説明ではなく感情を止める痛みワードか。15文字以内か
3. **感情曲線（emotional curve）**: 痛み → 共感 → データ → 安心/希望 の順か
4. **closing の静かな着地**: 煽りCTAではなく余韻型か（「同じ人いる？」「続けてますか」等）
5. **文言重複**: data の使い回し、同じ resolve パターンの繰り返しがないか

## Shorts レビュー手順

1. `review_gen.py` を実行してレビュー用プロンプトを生成
   ```bash
   source venv/bin/activate
   python review_gen.py
   ```
2. クリップボードの内容を ChatGPT に貼り付けてレビュー依頼
3. スコアを Google Sheets の Q-V 列に記録

## note レビュー手順

- 800〜1500字に収まっているか
- 静かで断定しすぎない語り口か（AGENTS.md 準拠）
- 免責表記（投資助言ではない旨）が含まれているか
- SEO: タイトルにキーワードが入っているか、見出し構造が適切か

## 技術チェック

- 音声の読み間違いがないか（voice_gen 読み辞書未登録）
- スライドの文字が切れていないか（禁則処理）
- BGM と音声のバランスが適切か
- サムネイルのテキストがタイトルと被っていないか
