---
name: theme-intake
description: Evaluate and register new theme candidates for ガチホのモチベ Shorts. Use when user proposes a new topic, theme, or content direction.
argument-hint: "[theme description]"
allowed-tools:
  - Read
  - Bash
  - Grep
  - Glob
---

# テーマ審査・登録

新しいテーマを評価し、採用なら登録するワークフロー。
**まず審査、通ったら登録** の二段構え。

## ステップ1: 審査（ここで止まる場合あり）

以下を全て確認し、結果をユーザーに報告する:

### 必須チェック
- [ ] AGENTS.md の Product Rules に反していないか（投資助言NG、煽りNG）
- [ ] CHANNEL_STRATEGY.md のブランドコンセプトに合致するか（「揺れた気持ちを整える」）
- [ ] 既存テーマとの重複がないか（topics.json、直近キュー）

### 戦略チェック
- [ ] 勝ち筋3本柱への適合（①数字+損失差 ②増えない感覚 ③普通の自分系）
- [ ] 強すぎる恐怖ワードの有無（「暴落」「売りたい」系は増やさない方針）
- [ ] note 記事化しやすさ（記事展開できるテーマか）
- [ ] 感情曲線が成立するか（「恐怖→歴史データ→安心」の骨格があるか）

### 数字チェック
- [ ] タイトルに具体的数字を入れられるか（再生数2〜3倍の実績あり）

## ステップ2: 登録（審査を通過した場合のみ）

1. hooks.json にテーマ対応の hook を追加
   - 6型（単語/痛み/逆説/違和感/データ/真実）のいずれかに分類
   - hook は最大15文字、初見で意味が通じること最優先
2. topics.json を更新
3. Google Sheets の投稿管理シートに行を追加
   - B: フォルダ名、C: 種別、D: トピック、E: 検索KW、F: 狙い、G: 未生成
4. テスト生成（dry-run）
   ```bash
   source venv/bin/activate
   python main.py --theme <テーマ名> --dry-run
   ```

## 判断に迷ったら

ユーザーに「このテーマは○○の理由で微妙だが、△△に寄せれば成立する」のように代替案を提示する。
