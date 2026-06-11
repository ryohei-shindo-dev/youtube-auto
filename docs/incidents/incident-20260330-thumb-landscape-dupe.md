---
date: 2026-03-30
severity: minor
status: resolved
affected: サムネイル品質（横型写真クロップ + サムネテキスト重複）
root_cause: _pick_thumbnail_photo に縦型フィルタ未実装 / サムネテキスト近接チェック未実装
---

# 障害報告: サムネイル横型写真クロップ + テキスト重複（2026-03-30）

## 症状

YouTube チャンネルページで2つの問題をユーザーが目視確認:

1. **「向いてない」のサムネイル画像が横型写真を縦にクロップしており、被写体が切れている**
2. **「市場に残る人だけが勝ちます」のサムネテキストが近い時期に2本並んでいる**

## 原因

### 問題1: 横型写真のクロップ

- `slide_gen.py` の `_pick_thumbnail_photo()` にアスペクト比フィルタがなかった
- `assets/photos/thumbnail/` に横型写真24枚（全165枚の14.5%）が残存
- スライド生成側の `_get_photo()` には3/24に縦型フィルタを実装済みだったが、サムネフレーム側には未適用だった

### 問題2: サムネテキスト重複

- `auto_publish.py` の公開候補選択にはhookテキストの近接チェックがあったが、サムネテキスト（resolve slide_text）のチェックがなかった
- 「市場に残る人だけが勝ちます」が17フォルダのresolve slide_textに存在
- `thumbnail_registry.json` にはタイトルから生成されたテキストのみ記録され、resolveフォールバックで生成されたサムネテキストは記録されないため、生成時の重複チェックも効かなかった

## 対応

1. ✅ `slide_gen.py` `_pick_thumbnail_photo()`: 縦型写真のみ選択するフィルタ追加（`img.height >= img.width`）
2. ✅ `auto_publish.py`: サムネテキスト近接チェック追加
   - `_read_thumbnail_text()`: フォルダからresolve slide_textを取得する関数を新設
   - `_build_recent_hook_context()`: 直近公開済みのサムネテキストを収集（`thumb_texts`）
   - `_check_hook_conflict()`: サムネテキスト衝突を返り値に追加
   - 投稿候補選択ループ: サムネテキスト一致時はスキップしてログ出力

## 動作確認

- 横型フィルタ: 10回ランダム選択で全て縦型（PORTRAIT）を確認
- サムネ近接: dry-runで「市場に残る人だけが勝ちます」3本+「退場しない人が勝つ」系3本がスキップされ、重複のない候補が選択されることを確認
