# リポジトリ構造化ガイド（Codex / Claude Code 併用）

> youtube-auto で適用済みの方針。buyma-auto、accounting-auto にも同じ構造を適用する。

## 基本方針

**1つの情報は1箇所だけに書く。** Codex と Claude Code の両方が使うファイルと、片方だけが使うファイルを明確に分ける。

## ファイル役割の定義

| ファイル | 読み手 | 役割 | 内容 |
|----------|--------|------|------|
| `AGENTS.md` | **Codex / Claude Code 共通** | コンテンツ・ビジネスルール（恒常） | Purpose、禁止事項、品質基準、表現ルール |
| `CLAUDE.md` | **Claude Code** | リポジトリの地図 | Repo Map、Pipeline Flow、コマンド、コード規約、情報の階層表 |
| `PENDING_TASKS.md` | **Codex / Claude Code 共通** | 残タスクボード | 各タスクは「状態 → 次のアクション → 関連ファイル」のみ。進捗ログは書かない |
| `docs/` | 両方 | 詳細ドキュメント | architecture.md、runbook.md など。CLAUDE.md からリンク |
| `memory/MEMORY.md` | **Claude Code のみ** | 作業記憶 | リポジトリ内ドキュメントと重複しない知識だけ（バグ修正歴、実装パターン、ユーザー環境） |

## 作成手順

### Step 1: CLAUDE.md を作成

```markdown
# CLAUDE.md

## Purpose
`AGENTS.md` を参照。（※Purpose を二重に書かない）

## Repo Map
（全ファイルの役割をツリー図で。コメント付き）

## Pipeline Flow
（データの流れを簡潔に）

## Rules & Commands
### ビルド・実行（よく使うコマンド）
### コード規約（言語バージョン、依存管理、認証方式）
### 禁止事項（AGENTS.md を参照 + コード固有の禁止事項）
### 情報の階層（どのファイルが何の役割か、読み手は誰か）

### 詳細ドキュメント
（docs/ 内のファイルへのリンク）
```

### Step 2: AGENTS.md を確認・整備

既存の AGENTS.md があればそのまま活用。なければ以下を書く：
- Purpose（このシステムが存在する理由）
- Product Rules（ビジネス上のルール・禁止事項）
- Working Rules（コード変更時の注意点）
- Source Of Truth（どのファイルが一次資料か）

**CLAUDE.md と重複する内容は書かない**（Repo Map、コマンド、コード規約など）。

### Step 3: PENDING_TASKS.md を圧縮

各タスクのフォーマットを統一：

```markdown
## N. タスク名

**状態**: 一文で現状を書く。
**次のアクション**: 番号付きリストで具体的な手順。
**関連ファイル**: ファイル名をカンマ区切り。
```

進捗ログ（「〜日: 〜を実施」の羅列）は削除する。必要なら別ファイルに退避。

### Step 4: docs/ にドキュメント追加

最低限：
- `docs/architecture.md` — システム全体像、データの流れ、外部依存
- `docs/runbook.md` — 日常運用、よくある操作、トラブルシューティング

### Step 5: memory/MEMORY.md を整理

以下を **削除**（リポジトリ内ドキュメントと重複するため）：
- Purpose / チャンネル方針 → AGENTS.md にある
- パイプライン構成 / Repo Map → CLAUDE.md にある
- 定期実行設定（launchd）/ シート列構成 → CLAUDE.md or docs/ にある
- タスク一覧 → PENDING_TASKS.md にある

以下だけ **残す**（Claude Code 固有の作業知識）：
- ユーザー環境・制約（Codex併用、エンジニアではない等）
- 重要な実装パターン（コードを触るときの注意点）
- 過去のバグ修正（再発防止メモ）
- 分析で得られた知見

### Step 6: .claude/settings.json にフック追加（任意）

認証ファイルの編集ブロックなど、自動ガードレールを設定。

## チェックリスト

- [ ] AGENTS.md に Purpose と Rules がある
- [ ] CLAUDE.md に Repo Map と Commands がある
- [ ] CLAUDE.md と AGENTS.md で情報が重複していない
- [ ] PENDING_TASKS.md が「状態 → 次のアクション → 関連ファイル」形式
- [ ] PENDING_TASKS.md に進捗ログの羅列がない
- [ ] docs/architecture.md がある
- [ ] docs/runbook.md がある
- [ ] memory/MEMORY.md がリポジトリ内ドキュメントと重複していない
