# 新テーマ追加スキル

新しいトピック・テーマを追加するワークフロー。

## 手順

1. テーマの妥当性を確認
   - AGENTS.md の Product Rules に反していないか
   - CHANNEL_STRATEGY.md のチャンネルコンセプトに合致するか
   - 投資助言に該当しないか

2. hooks.json にテーマ対応の hook を追加（必要な場合）
   - 5 タイプ（単語型 / 痛み型 / 逆説型 / データ型 / 真実型）のいずれかに分類
   - theme_recommendations にマッピングを追加

3. Google Sheets の「投稿管理」シートに行を追加
   - A: 通番、B: Type（shorts / long）、C: Topic、D: Keyword、E: Purpose、F: 未生成

4. topics.json を更新（使用している場合）

5. テスト生成
   ```bash
   python main.py --theme 新テーマ名 --dry-run
   ```

## テーマ設計の指針
- 「恐怖 → 歴史データ → 安心」の構造が最も強い
- 感情が弱いテーマ（分散投資の説明、複利の仕組み）は伸びにくい
- タイトルに具体的な数字（1800万円、3年等）を入れると再生数 2〜3 倍
