---
name: publish
description: Manually publish content to YouTube, Instagram, X, or TikTok for ガチホのモチベ. Use when user wants to post videos or check publishing status.
argument-hint: "[youtube|instagram|x|tiktok|all] [--dry-run] [folder-name]"
allowed-tools:
  - Read
  - Bash
  - Grep
  - Glob
---

# 手動投稿

指定プラットフォームへの投稿を実行する。

## 引数の解釈

- プラットフォーム指定: `youtube`, `instagram`, `x`, `tiktok`, `all`
- `--dry-run`: 実際には投稿せず、対象の確認だけ行う
- フォルダ名指定: 特定の動画だけ投稿する場合

## 手順

1. **投稿対象の確認**: Google Sheets から G列=「生成済み」の動画を取得
   - partial（一部PF未投稿）を generated（完全未投稿）より優先する
   - ユーザーに対象を見せて確認を取る
2. **投稿実行**:
   ```bash
   source venv/bin/activate
   python auto_publish.py --platforms <プラットフォーム>
   ```
3. **結果確認**: Sheets の URL 列（K〜N）に URL が記録されたか確認

## 重要ルール

- **partial を generated より優先する**（逆にすると重複投稿の原因）
- B列（フォルダ名）のみをキーに使う。A列・タイトル検索は禁止
- X の URL は `/{X_HANDLE}/status/` 形式（`/i/status/` は不可）
- 投稿前に必ずユーザーに確認を取る（自動実行しない）
