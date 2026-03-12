"""
note_gen.py
note記事（800〜1500字）を自動生成するモジュール。

2つのモード:
  1. Shorts台本ベース: generate_note_article(script_data, output_dir)
  2. トピック直接指定: generate_note_from_topic(topic, theme, output_dir)
"""

from __future__ import annotations

import os
import pathlib
from typing import Optional

import anthropic

import api_usage_log
import script_gen

# note記事生成プロンプト
# 構成はChatGPT戦略レビュー(2026-03)のフィードバックを反映:
# - Shortsの断言をそのまま引っ張らず「解釈」→「小さな行動」を挟む
# - noteは「安心置き場」（煽りではなく落ち着かせる）
# - データは1つだけ、出典っぽさを出しつつ言い切りすぎない
# - 「傾向」「過去のデータでは」などの柔らかい表現を使う
NOTE_TEMPLATE = """\
あなたはnote（ブログプラットフォーム）向けの記事ライターです。

以下のYouTube Shorts台本を元に、noteの記事を書いてください。

## チャンネルコンセプト
{concept}

## Shorts台本の内容
- タイトル: {title}
- テーマ: {theme}
- hook（掴み）: {hook}
- empathy（共感）: {empathy}
- data（データ）: {data}
- resolve（結論）: {resolve}

## noteの役割
noteは「Shortsで刺された痛みの、安心置き場」です。
煽るのではなく、落ち着かせる。読み終わった後に「大丈夫だ」と思える記事にしてください。

## 記事の要件
- 文字数: 800〜1500字（厳守）
- 文体: 「です・ます」調。落ち着いた語り口で、読者に寄り添うトーン
- 投資助言・個別銘柄推奨・特定銘柄の売買指図は絶対にしない
- 1記事で伝えることは1つだけ（焦点がぼけるので言いたいことを3つ以上入れない）
- データは1つだけ使い、説明は最大3行まで。出典っぽさを出しつつ言い切りすぎない
- 断定・推奨は避ける（「〜しよう」より「〜すると落ち着きやすい」）
- 確約表現は禁止（「必ず儲かる」「勝てる」「損しない」「今買うべき」等）
- 代わりに使う表現: 「傾向がある」「過去のデータでは」「一般に〜とされる」「〜と整理できる」
- 確率や結果を表す文章では「可能性があります」「傾向があります」を使用する（「可能性が高い」は避ける）
- 抽象・ポエム表現は使わない（「未来」「景色が変わる」「遠くを見る」「あなたの味方」等は禁止）
- 記事の最後の一文も抽象表現を避け、データや傾向に基づく文にする（NG:「時間があなたの味方です」→ OK:「長期投資では、時間が結果に影響してきた傾向があります」）
- 共感パートは3行以内（Shorts流入の読者はテンポ重視）
- 1段落は最大4行まで（テンポを保つ）

## フォーマット制約
- 見出し（##）は2〜4個まで
- 箇条書きは最大5行まで
- 見出しは自然な問いかけや短いフレーズにする（「データ」「解釈」などの構成名は使わない）

## 記事の構成（この順番で書くこと）
1. **タイトル**（30字以内。「痛みワード＋数字」の型を優先。例:「含み損で眠れない夜に思い出したい『20年』の数字」）
2. **フック**（Shortsの痛みワードをそのまま1行で。記事の1行目に置く。50字以内）
3. **共感**（"よくある状況"を短く2〜4行。「あなただけじゃない」という安心感。100〜200字）
4. **データ**（Shorts台本のデータを1つだけ紹介。出典っぽさを出す。言い切りすぎない。説明は最大3行。100〜200字）
5. **解釈**（データが示す意味を1つだけ。なぜそうなるのか、読者が腑に落ちる理由を書く。100〜200字）
6. **行動**（具体的で小さな行動提案。「見る頻度を減らす」「積立を切らない」等。100〜200字）
7. **まとめ**（1行で締める。50字以内）
8. **Q&A**（「よくある質問」として2〜3個。トピックに関連する検索されやすい疑問を選ぶ。回答は各1〜2行で短く。断定・確約表現は使わない）

## 締め（Q&Aの後に、以下を最終行としてそのまま付けること）
---
もし今つらい夜なら、この内容の12秒版もYouTube Shorts「ガチホのモチベ」で配信しています。

## 出力フォーマット
マークダウン形式で出力してください。タイトルは `#` で始めてください。
"""


def generate_note_article(script_data: dict, output_dir: pathlib.Path) -> Optional[pathlib.Path]:
    """Shorts台本からnote記事を生成し、note_article.md として保存する。

    Args:
        script_data: script_gen が返す台本データ
        output_dir: 出力先ディレクトリ

    Returns:
        生成した記事ファイルのパス。失敗時は None。
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("  [note_gen] ANTHROPIC_API_KEY が未設定です。スキップします。")
        return None

    # 台本からシーンテキストを抽出
    scenes_by_role = {}
    for scene in script_data.get("scenes", []):
        role = scene.get("role", "")
        scenes_by_role[role] = scene.get("text", "")

    prompt = NOTE_TEMPLATE.format(
        concept=script_gen.CHANNEL_CONCEPT,
        title=script_data.get("title", ""),
        theme=script_data.get("theme", ""),
        hook=scenes_by_role.get("hook", ""),
        empathy=scenes_by_role.get("empathy", ""),
        data=scenes_by_role.get("data", ""),
        resolve=scenes_by_role.get("resolve", ""),
    )

    article = _call_claude(api_key, prompt)
    if not article:
        return None

    return _save_article(article, output_dir, "note_article.md")


# ── トピック直接指定モード ──

NOTE_TOPIC_TEMPLATE = """\
あなたはnote（ブログプラットフォーム）向けの記事ライターです。

以下のトピックについて、noteの記事を書いてください。

## チャンネルコンセプト
{concept}

## 記事のトピック
{topic}

## テーマカテゴリ
{theme}

## noteの役割
noteは「Shortsで刺された痛みの、安心置き場」です。
煽るのではなく、落ち着かせる。読み終わった後に「大丈夫だ」と思える記事にしてください。

## 記事の要件
- 文字数: 800〜1500字（厳守）
- 文体: 「です・ます」調。落ち着いた語り口で、読者に寄り添うトーン
- 投資助言・個別銘柄推奨・特定銘柄の売買指図は絶対にしない
- 1記事で伝えることは1つだけ（焦点がぼけるので言いたいことを3つ以上入れない）
- データは1つだけ使い、説明は最大3行まで。出典っぽさを出しつつ言い切りすぎない
- 断定・推奨は避ける（「〜しよう」より「〜すると落ち着きやすい」）
- 確約表現は禁止（「必ず儲かる」「勝てる」「損しない」「今買うべき」等）
- 代わりに使う表現: 「傾向がある」「過去のデータでは」「一般に〜とされる」「〜と整理できる」
- 確率や結果を表す文章では「可能性があります」「傾向があります」を使用する（「可能性が高い」は避ける）
- 抽象・ポエム表現は使わない（「未来」「景色が変わる」「遠くを見る」「あなたの味方」等は禁止）
- 記事の最後の一文も抽象表現を避け、データや傾向に基づく文にする
- 共感パートは3行以内
- 1段落は最大4行まで（テンポを保つ）

## フォーマット制約
- 見出し（##）は2〜4個まで
- 箇条書きは最大5行まで
- 見出しは自然な問いかけや短いフレーズにする（「データ」「解釈」などの構成名は使わない）

## 記事の構成（この順番で書くこと）
1. **タイトル**（30字以内。「痛みワード＋数字」の型を優先。例:「含み損で眠れない夜に思い出したい『20年』の数字」）
2. **フック**（トピックの痛みを1行で。記事の1行目に置く。50字以内）
3. **共感**（"よくある状況"を短く2〜3行。「あなただけじゃない」という安心感。100〜200字）
4. **データ**（トピックに関連するデータを1つだけ紹介。出典っぽさを出す。説明は最大3行。100〜200字）
5. **解釈**（データが示す意味を1つだけ。読者が腑に落ちる理由を書く。100〜200字）
6. **行動**（具体的で小さな行動提案。「見る頻度を減らす」「積立を切らない」等。100〜200字）
7. **まとめ**（1行で締める。50字以内）
8. **Q&A**（「よくある質問」として2〜3個。トピックに関連する検索されやすい疑問を選ぶ。回答は各1〜2行で短く。断定・確約表現は使わない）

## 締め（Q&Aの後に、以下を最終行としてそのまま付けること）
---
もし今つらい夜なら、この内容の12秒版もYouTube Shorts「ガチホのモチベ」で配信しています。

## 出力フォーマット
マークダウン形式で出力してください。タイトルは `#` で始めてください。
"""


def generate_note_from_topic(
    topic: str, theme: str, output_dir: pathlib.Path, filename: str = "note_article.md"
) -> Optional[pathlib.Path]:
    """トピックから直接note記事を生成する。

    Args:
        topic: 記事のトピック文字列
        theme: テーマカテゴリ（あるある/歴史データ/心理 等）
        output_dir: 出力先ディレクトリ
        filename: 出力ファイル名

    Returns:
        生成した記事ファイルのパス。失敗時は None。
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("  [note_gen] ANTHROPIC_API_KEY が未設定です。スキップします。")
        return None

    prompt = NOTE_TOPIC_TEMPLATE.format(
        concept=script_gen.CHANNEL_CONCEPT,
        topic=topic,
        theme=theme,
    )

    article = _call_claude(api_key, prompt)
    if not article:
        return None

    return _save_article(article, output_dir, filename)


# ── 共通関数 ──

def _call_claude(api_key: str, prompt: str) -> Optional[str]:
    """Claude APIを呼び出して記事テキストを返す。

    note記事はShortsほど感情曲線の精度が不要なため、
    コスト削減のためHaikuを使用（Sonnetの約1/12のコスト）。
    """
    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        api_usage_log.log_usage(
            message, model="claude-haiku-4-5-20251001",
            endpoint="note_gen",
        )
        return message.content[0].text.strip()
    except Exception as e:
        print(f"  [note_gen] Claude API エラー: {e}")
        return None


def _save_article(article: str, output_dir: pathlib.Path, filename: str) -> pathlib.Path:
    """記事をファイルに保存する。"""
    body_text = article.replace("#", "").replace("*", "").replace("-", "").strip()
    char_count = len(body_text)
    print(f"  note記事生成完了（{char_count}字）")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / filename
    output_path.write_text(article, encoding="utf-8")
    print(f"  保存先: {output_path}")

    return output_path
