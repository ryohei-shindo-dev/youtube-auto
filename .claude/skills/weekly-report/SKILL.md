---
name: weekly-report
description: Run weekly analytics collection and analysis for ガチホのモチベ. Use when user wants performance summary, weekly review, or content strategy feedback.
allowed-tools:
  - Read
  - Bash
  - Grep
  - Glob
model: sonnet
---

# 週次レポート

分析データの収集 → 分析 → 次週アクション提案までを一括実行する。

## 手順

1. **データ収集**（まだ今週分を集めていない場合）:
   ```bash
   source venv/bin/activate
   python analytics_collect.py
   ```

2. **週次分析**:
   ```bash
   python analytics_analyze.py
   ```

3. **結果の要約**: `analytics_insights.json` を読み、以下を報告:
   - 今週の再生数トップ3とその要因
   - 伸びなかった動画とその要因
   - カテゴリ別パフォーマンス
   - 登録者数の推移

4. **次週アクション提案**:
   - キューのテーマバランスに問題はないか
   - 勝ち筋（数字+損失差 / 増えない感覚 / 普通の自分系）との整合
   - 補充が必要なテーマの方向性
   - A/Bテスト中の項目があればその判定状況

## 出力形式

簡潔な日本語で、数字を中心に報告する。
感想より事実とアクションを優先。
