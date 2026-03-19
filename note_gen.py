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
- 表記は `積み立て` に統一し、`積立` は固有名詞以外で使わない
- 「夜」という語に依存しない。時間帯ではなく感情や状況で表現する。「夜」は孤独・眠れなさ・不安の持続を描く場合のみ許可。比較・目移り・退屈系では「夜」を使わない

## フォーマット制約
- 見出し（##）は2〜4個まで
- 箇条書きは最大5行まで
- 見出しは自然な問いかけや短いフレーズにする（「データ」「解釈」などの構成名は使わない）

## タイトルの型（30字以内。以下5型からテーマに合うものを選ぶ。毎回同じ型を使わない）
- 型A 状態言い切り: 「正しいのに退屈で続かない」「増えているのに安心できない」
- 型B 原因を切る: 「勉強するほど軸がぶれやすくなる理由」「商品を増やすほど落ち着かなくなる理由」
- 型C 行動を絞る: 「設定を変えたくなったら先に見ること」「乗り換えたくなった日に増やさないもの」
- 型D 逆説で引く: 「何も起きない日の方が本番」「画面を見なかった日が一番いい判断だった」
- 型E 小さい結論: 「今日も引き落とされた。それで十分です」「気づいたら続いていた」
※「〜の夜」「〜夜に」は3本に1本以下。noteは「読んだら整理できそう」と思わせるタイトルにする

## 記事の構成（テーマに合う型を選ぶ。毎回同じ構成にしない）

【構成1: 共感→分解→小さい結論】比較疲れ・目移り系向き
1. フック（1行、50字以内）
2. 何が揺れているのか（共感、2〜3行）
3. その感情の正体（分解、100〜200字）
4. 今日の結論（小さい結論、50〜100字）

【構成2: 状態→誤解→見方の修正】こつこつ系向き
1. フック（1行、50字以内）
2. うまくいっていないように見える理由（100〜200字）
3. 本当は何が起きているか（データ1つ+解釈、200〜300字）
4. その日の終わり方（1〜2行）

【構成3: 問い→2つの見方→自分の軸】商品比較系向き
1. フック（1行、50字以内）
2. 片方がよく見える理由（100〜200字）
3. それでも決めきれない理由（100〜200字）
4. 何を基準に戻るか（100〜200字）

【構成4: 体験の流れ→解釈】不安・確認癖系向き
1. フック（1行、50字以内）
2. こういう流れで崩れる（具体的な流れ、100〜200字）
3. どこで苦しくなるか・その感情は何か（100〜200字）
4. 1つだけ戻す行動（具体的で小さな提案、100〜200字）

## Q&A（任意）
- Q&Aは毎回入れない。制度不安・商品比較・出口不安のテーマでは1〜2問入れてよい
- 共感系・こつこつ系・感情整理系では入れない
- 入れる場合も最大2問まで。回答は各1〜2行。断定・確約表現は使わない

## 末尾（以下3パターンから選ぶ。毎回同じにしない）
- パターンA: 記事の最後の一文で自然に閉じる（導線なし）
- パターンB: 「このテーマの短い動画版もYouTube Shorts「ガチホのモチベ」で配信しています。」
- パターンC: 関連テーマへの一文（「比較で揺れるときは、選んだ理由を一行だけ思い出すと戻りやすいです。」等）

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
- 「夜」という語に依存しない。時間帯ではなく感情や状況で表現する。「夜」は孤独・眠れなさ・不安の持続を描く場合のみ許可。比較・目移り・退屈系では「夜」を使わない

## フォーマット制約
- 見出し（##）は2〜4個まで
- 箇条書きは最大5行まで
- 見出しは自然な問いかけや短いフレーズにする（「データ」「解釈」などの構成名は使わない）

## タイトルの型（30字以内。以下5型からテーマに合うものを選ぶ。毎回同じ型を使わない）
- 型A 状態言い切り: 「正しいのに退屈で続かない」「増えているのに安心できない」
- 型B 原因を切る: 「勉強するほど軸がぶれやすくなる理由」「商品を増やすほど落ち着かなくなる理由」
- 型C 行動を絞る: 「設定を変えたくなったら先に見ること」「乗り換えたくなった日に増やさないもの」
- 型D 逆説で引く: 「何も起きない日の方が本番」「画面を見なかった日が一番いい判断だった」
- 型E 小さい結論: 「今日も引き落とされた。それで十分です」「気づいたら続いていた」
※「〜の夜」「〜夜に」は3本に1本以下。noteは「読んだら整理できそう」と思わせるタイトルにする

## 記事の構成（テーマに合う型を選ぶ。毎回同じ構成にしない）

【構成1: 共感→分解→小さい結論】比較疲れ・目移り系向き
1. フック（1行、50字以内）
2. 何が揺れているのか（共感、2〜3行）
3. その感情の正体（分解、100〜200字）
4. 今日の結論（小さい結論、50〜100字）

【構成2: 状態→誤解→見方の修正】こつこつ系向き
1. フック（1行、50字以内）
2. うまくいっていないように見える理由（100〜200字）
3. 本当は何が起きているか（データ1つ+解釈、200〜300字）
4. その日の終わり方（1〜2行）

【構成3: 問い→2つの見方→自分の軸】商品比較系向き
1. フック（1行、50字以内）
2. 片方がよく見える理由（100〜200字）
3. それでも決めきれない理由（100〜200字）
4. 何を基準に戻るか（100〜200字）

【構成4: 体験の流れ→解釈】不安・確認癖系向き
1. フック（1行、50字以内）
2. こういう流れで崩れる（具体的な流れ、100〜200字）
3. どこで苦しくなるか・その感情は何か（100〜200字）
4. 1つだけ戻す行動（具体的で小さな提案、100〜200字）

## Q&A（任意）
- Q&Aは毎回入れない。制度不安・商品比較・出口不安のテーマでは1〜2問入れてよい
- 共感系・こつこつ系・感情整理系では入れない
- 入れる場合も最大2問まで。回答は各1〜2行。断定・確約表現は使わない

## 末尾（以下3パターンから選ぶ。毎回同じにしない）
- パターンA: 記事の最後の一文で自然に閉じる（導線なし）
- パターンB: 「このテーマの短い動画版もYouTube Shorts「ガチホのモチベ」で配信しています。」
- パターンC: 関連テーマへの一文（「比較で揺れるときは、選んだ理由を一行だけ思い出すと戻りやすいです。」等）

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
        model = script_gen._MODEL_HAIKU
        message = client.messages.create(
            model=model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        api_usage_log.log_usage(
            message, model=model,
            endpoint="note_gen",
        )
        return message.content[0].text.strip()
    except Exception as e:
        print(f"  [note_gen] Claude API エラー: {e}")
        return None


def _save_article(article: str, output_dir: pathlib.Path, filename: str) -> pathlib.Path:
    """記事をファイルに保存する。"""
    article = script_gen.normalize_preferred_spelling(article)
    body_text = article.replace("#", "").replace("*", "").replace("-", "").strip()
    char_count = len(body_text)
    print(f"  note記事生成完了（{char_count}字）")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / filename
    output_path.write_text(article, encoding="utf-8")
    print(f"  保存先: {output_path}")

    return output_path
