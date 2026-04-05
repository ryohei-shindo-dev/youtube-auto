"""長期投資チャンネル向け競合動画テーマ判定ツール."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# パス解決
# ---------------------------------------------------------------------------
TOOL_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TOOL_DIR.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

OUTPUTS_DIR = PROJECT_ROOT / "outputs" / "checks"
BATCHES_DIR = PROJECT_ROOT / "outputs" / "batches"
DISCOVERIES_DIR = PROJECT_ROOT / "outputs" / "discoveries"
STOCK_DIR = PROJECT_ROOT / "outputs" / "stock"

AGENTS_MD_PATH = PROJECT_ROOT / "AGENTS.md"
CHANNEL_STRATEGY_PATH = PROJECT_ROOT / "CHANNEL_STRATEGY.md"
TOPICS_PATH = PROJECT_ROOT / "data" / "content" / "topics.json"


def extract_video_id(url: str) -> str:
    """YouTube URL から video_id を抽出する。"""
    patterns = [
        r"(?:youtu\.be/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/watch\?v=)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/embed/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/shorts/)([A-Za-z0-9_-]{11})",
    ]
    for pat in patterns:
        match = re.search(pat, url)
        if match:
            return match.group(1)
    raise ValueError(f"YouTube URLからvideo_idを抽出できません: {url}")


def fetch_transcript(video_id: str) -> str | None:
    """youtube-transcript-api で字幕テキストを取得する。"""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        ytt_api = YouTubeTranscriptApi()
        transcript = ytt_api.fetch(video_id, languages=["ja", "en"])
        lines = [snippet.text for snippet in transcript.snippets]
        return "\n".join(lines)
    except Exception as err:
        print(f"[WARN] 字幕取得失敗: {err}", file=sys.stderr)
        return None


def fetch_video_metadata(video_id: str) -> dict[str, object]:
    """YouTube Data API から説明文などの動画メタデータを取得する。"""
    import sheets

    youtube = sheets.get_youtube_service()
    response = youtube.videos().list(part="snippet", id=video_id, maxResults=1).execute()
    items = response.get("items", [])
    if not items:
        return {}

    snippet = items[0].get("snippet", {})
    return {
        "title": snippet.get("title", ""),
        "description": snippet.get("description", ""),
        "channel_title": snippet.get("channelTitle", ""),
        "tags": snippet.get("tags", []),
        "published_at": snippet.get("publishedAt", ""),
    }


def build_fallback_content(video_id: str, title: str) -> tuple[str | None, str]:
    """字幕が取れない場合に snippet ベースの判定材料を組み立てる。"""
    metadata = fetch_video_metadata(video_id)
    if not metadata:
        return None, "none"

    lines = [
        f"タイトル: {metadata.get('title') or title}",
        f"チャンネル名: {metadata.get('channel_title', '')}",
    ]

    description = str(metadata.get("description", "")).strip()
    if description:
        description = description[:4000]
        lines.append("説明文:")
        lines.append(description)

    tags = metadata.get("tags", []) or []
    if tags:
        lines.append("タグ:")
        lines.append(", ".join(tags[:30]))

    published_at = metadata.get("published_at", "")
    if published_at:
        lines.append(f"公開日: {published_at}")

    return "\n".join(lines), "metadata"


def fetch_video_title(video_id: str) -> str:
    """oEmbed API で動画タイトルを取得する。"""
    import urllib.parse
    import urllib.request

    url = (
        "https://www.youtube.com/oembed?"
        + urllib.parse.urlencode(
            {"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"}
        )
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())
            return data.get("title", "(タイトル取得失敗)")
    except Exception:
        return "(タイトル取得失敗)"


def _extract_existing_topics() -> str:
    """topics.json から既存テーマの要点だけを抽出する。"""
    if not TOPICS_PATH.exists():
        return "(topics.json が見つかりません)"

    data = json.loads(TOPICS_PATH.read_text(encoding="utf-8"))
    shorts = data.get("shorts", {})

    lines = []
    for section_name, items in shorts.items():
        if not items:
            continue
        lines.append(f"## {section_name}")
        for item in items[:8]:
            topic = item.get("topic", "").strip()
            if topic:
                lines.append(f"- {topic}")
        lines.append("")

    return "\n".join(lines).strip() or "(既存テーマを抽出できませんでした)"


def load_context() -> dict[str, str]:
    """判定に必要なチャンネル方針ファイルを読み込む。"""
    ctx = {}
    for name, path in [
        ("agents", AGENTS_MD_PATH),
        ("strategy", CHANNEL_STRATEGY_PATH),
    ]:
        if path.exists():
            ctx[name] = path.read_text(encoding="utf-8")
        else:
            ctx[name] = f"({path.name} が見つかりません)"

    ctx["existing_topics"] = _extract_existing_topics()
    return ctx


def build_prompt(title: str, transcript: str, ctx: dict[str, str], source_mode: str) -> str:
    """ChatGPT に渡す長期投資チャンネル向け判定プロンプトを構築する。"""
    max_chars = 12000
    if len(transcript) > max_chars:
        transcript = transcript[:max_chars] + "\n\n(...以下省略)"

    return f"""あなたは YouTube チャンネル「ガチホのモチベ」のコンテンツディレクターです。
競合または参考チャンネルの動画が、このチャンネルの動画ネタとして採用可能かを厳しめに判定してください。

# チャンネル方針（正本）
{ctx['agents']}

# チャンネル戦略
{ctx['strategy']}

# 既存テーマの例
{ctx['existing_topics']}

# 判定の前提

- このチャンネルは投資ノウハウ解説チャンネルではなく、長期投資を続けるための共感・思想・モチベーション提供が目的
- 煽らない・助言しない・静かに寄り添うトーンを守る
- 個別株推奨、買い時断定、短期売買煽り、爆益訴求、恐怖サムネ前提のFOMO訴求は避ける
- 競合調査の目的は「伸びている煽り動画を真似る」ことではなく、長期投資チャンネルとして翻訳可能なネタを拾うこと

# 採用しやすいテーマ

- 長期投資の継続
- 暴落時の考え方
- 新NISA
- 積み立てを続けるコツ
- 投資初心者の不安
- 含み損との付き合い方
- ガチホ中のメンタル
- 資産形成の習慣
- 長期目線での指数・資産配分・入金力の考え方
- 生活防衛資金と投資継続の両立

# 距離を取りたいテーマ

- 短期売買煽り
- テンバガー煽り
- 明日上がる株
- 今すぐ買うべき銘柄
- 煽りサムネ前提の恐怖訴求
- 仕手株 / 一発逆転 / 爆益訴求
- 再現性の低いトレード自慢
- 過度なFOMO訴求

# 厳格ルール

1. 判定は厳しめに行うこと。迷ったら unusable 寄りに判定する
2. 動画の表現ではなく「主目的」を見ること
3. タイトルが煽りでも、中身が長期投資の不安整理や継続支援に翻訳できるなら conditional までは許容する
4. ただし、芯が「売買タイミング指南」「個別銘柄煽り」「射幸心刺激」なら unusable
5. conditional は「少し言い換えれば使える」ではなく、「長期投資チャンネルとして翻訳する価値がある」場合のみ
6. 既にうちの既存テーマで自然に語れる内容しかない場合は、参照価値が薄いので unusable でもよい
7. 数字やデータは安心材料として転用できるかを見る。煽り材料に依存する場合は評価を下げる

# 判定対象の動画

タイトル: {title}
判定材料の種類: {source_mode}

## 判定材料
{transcript}

# 判定材料が metadata の場合の注意

- 字幕全文ではなく、タイトル・説明文・タグだけで推定している可能性がある
- その場合は確信度を下げて判定すること
- 材料不足で断定できない場合は unusable ではなく conditional でもよいが、reason_short に「情報不足」を明記すること
- metadata だけで明らかに短期煽り・個別株煽り・FOMO が強い場合は unusable でよい

# 出力指示

以下のJSON形式で出力してください。JSON以外のテキストは出力しないでください。

{{
  "title": "動画タイトル",
  "judgment": {{
    "primary": "usable / conditional / unusable のいずれか",
    "title_only_judgment": "o / triangle / x のいずれか",
    "reason_short": "判定理由（1〜2文）",
    "translation_cost": "low / medium / high / impossible のいずれか",
    "risk_level": "low / medium / high のいずれか"
  }},
  "analysis": {{
    "focus": "long_term_mindset / beginner_support / system_explainer / short_term_trading / stock_picking / fear_marketing / other のいずれか",
    "core_claims": ["主張の骨子を3〜5個"],
    "compatible_frames": ["うちの文脈に接続できる要素"],
    "danger_frames": ["うちの方針と衝突する要素"],
    "emotional_angle": "pain / empathy / reassurance / greed / fear / mixed のいずれか"
  }},
  "connections": {{
    "candidate_existing_topics": ["接続可能な既存テーマを2〜4個"],
    "recommended_action": "independent / integrate_existing / use_as_material / reject のいずれか",
    "action_detail": "どう翻訳して使うか、または棄却理由（1〜2文）"
  }},
  "translation_keys": {{
    "元の表現": "長期投資チャンネルでの言い換え"
  }},
  "title_suggestions": ["うちの文脈に合うタイトル案を2〜3本。unusable の場合は空配列"]
}}"""


def judge_video(prompt: str) -> dict:
    """ChatGPT API で判定を実行する。"""
    from ops_shared.chatgpt import ask_chatgpt

    raw = ask_chatgpt(prompt)
    return _parse_judge_response(raw, ask_chatgpt=ask_chatgpt)


def _extract_json_block(raw: str) -> str:
    """応答文字列から JSON らしき部分を抽出する。"""
    start = raw.find("{")
    if start == -1:
        raise RuntimeError(f"ChatGPT の応答からJSONを抽出できません:\n{raw[:500]}")

    depth = 0
    end = start
    for index, ch in enumerate(raw[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    return raw[start:end]


def _parse_json_candidate(raw_json: str) -> dict:
    """候補文字列を JSON としてパースする。"""
    json_str = re.sub(r"//[^\n]*", "", raw_json)
    return json.loads(json_str)


def _repair_json_response(raw: str, err: Exception, ask_chatgpt) -> str:
    """不正な JSON を strict JSON に整形し直させる。"""
    repair_prompt = f"""以下は別のモデルが返した出力です。
内容はなるべく保持したまま、strict JSON として正しい形に修復してください。

要件:
- JSON以外は出力しない
- キー名や値は元の意味を保つ
- 配列・オブジェクトの閉じ忘れ、余計な読点、引用符の崩れを直す
- 不明な値を勝手に補完しない

元のエラー:
{err}

元の出力:
```text
{raw[:12000]}
```"""
    return ask_chatgpt(repair_prompt)


def _parse_judge_response(raw: str, ask_chatgpt) -> dict:
    """判定レスポンスを頑健に JSON パースする。"""
    json_str = _extract_json_block(raw)

    try:
        return _parse_json_candidate(json_str)
    except json.JSONDecodeError as first_error:
        match = re.search(r"```json?\s*\n(.*?)```", raw, re.DOTALL)
        if match:
            try:
                return _parse_json_candidate(match.group(1))
            except json.JSONDecodeError:
                pass

        repaired_raw = _repair_json_response(raw, first_error, ask_chatgpt)
        try:
            repaired_json = _extract_json_block(repaired_raw)
            return _parse_json_candidate(repaired_json)
        except Exception as second_error:
            raise RuntimeError(
                "ChatGPT の応答JSONをパースできません。"
                f"\n初回エラー: {first_error}"
                f"\n修復後エラー: {second_error}"
                f"\n元の出力冒頭:\n{raw[:500]}"
            ) from second_error


def save_result(video_id: str, url: str, result: dict, source_mode: str) -> Path:
    """JSON ファイルに保存する。"""
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    output = {
        "url": url,
        "video_id": video_id,
        "source_mode": source_mode,
        "checked_at": datetime.now().isoformat(),
        **result,
    }
    path = OUTPUTS_DIR / f"{video_id}.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_existing_result(video_id: str) -> dict | None:
    """保存済みの判定結果を読み込む。"""
    path = OUTPUTS_DIR / f"{video_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def render_markdown(result: dict) -> str:
    """判定結果を Markdown で整形する。"""
    judgment = result.get("judgment", {})
    analysis = result.get("analysis", {})
    connections = result.get("connections", {})
    translation_keys = result.get("translation_keys", {})
    titles = result.get("title_suggestions", [])

    symbol = {
        "usable": "○",
        "conditional": "△",
        "unusable": "×",
    }.get(judgment.get("primary", ""), "?")

    lines = [
        f"## 判定結果: {symbol} {judgment.get('primary', '?')}",
        "",
        f"**タイトル:** {result.get('title', '?')}",
        f"**理由:** {judgment.get('reason_short', '?')}",
        f"**翻訳コスト:** {judgment.get('translation_cost', '?')}",
        f"**リスク:** {judgment.get('risk_level', '?')}",
        f"**タイトルだけの判定:** {judgment.get('title_only_judgment', '?')}",
        "",
        "### 分析",
        f"- フォーカス: {analysis.get('focus', '?')}",
        f"- 感情角度: {analysis.get('emotional_angle', '?')}",
    ]

    if analysis.get("core_claims"):
        lines.append("- 主張骨子:")
        for claim in analysis["core_claims"]:
            lines.append(f"  - {claim}")

    if analysis.get("compatible_frames"):
        lines.append("- 接続可能:")
        for frame in analysis["compatible_frames"]:
            lines.append(f"  - {frame}")

    if analysis.get("danger_frames"):
        lines.append("- 衝突要素:")
        for frame in analysis["danger_frames"]:
            lines.append(f"  - {frame}")

    lines.append("")
    lines.append("### 接続先")
    if connections.get("candidate_existing_topics"):
        for topic in connections["candidate_existing_topics"]:
            lines.append(f"- {topic}")
    lines.append(f"- 推奨アクション: {connections.get('recommended_action', '?')}")
    if connections.get("action_detail"):
        lines.append(f"- 詳細: {connections['action_detail']}")

    if translation_keys:
        lines.append("")
        lines.append("### 翻訳キー")
        for source_text, translated in translation_keys.items():
            lines.append(f"- {source_text} → {translated}")

    if titles:
        lines.append("")
        lines.append("### タイトル案")
        for index, candidate in enumerate(titles, 1):
            lines.append(f"{index}. {candidate}")

    return "\n".join(lines)


def run_video_check(url: str) -> dict:
    """動画 URL 1本を判定し、保存結果を返す。"""
    video_id = extract_video_id(url)
    print(f"[1/4] video_id: {video_id}")

    title = fetch_video_title(video_id)
    print(f"[2/4] タイトル: {title}")

    print("[3/4] 字幕取得中...")
    transcript = fetch_transcript(video_id)
    source_mode = "transcript"
    if transcript:
        print(f"[3/4] 字幕取得完了（{len(transcript)}文字）")
    else:
        print("[3/4] 字幕取得失敗。metadata フォールバックへ切替...")
        transcript, source_mode = build_fallback_content(video_id, title)
        if not transcript:
            raise RuntimeError("字幕・metadata の両方を取得できませんでした。")
        print(f"[3/4] metadata 取得完了（{len(transcript)}文字）")

    print("[4/4] ChatGPT 判定中...")
    prompt = build_prompt(title, transcript, load_context(), source_mode)
    result = judge_video(prompt)

    path = save_result(video_id, url, result, source_mode)
    return {
        "video_id": video_id,
        "title": title,
        "result": result,
        "path": path,
    }


def print_single_result(run_result: dict) -> None:
    """単体動画判定結果を表示する。"""
    print("\n" + "=" * 60)
    print(render_markdown(run_result["result"]))
    print("=" * 60)
    print(f"\nJSON保存先: {run_result['path']}")


def create_parser() -> argparse.ArgumentParser:
    """CLI パーサーを構築する。"""
    parser = argparse.ArgumentParser(description="長期投資向け競合動画テーマ判定ツール")
    subparsers = parser.add_subparsers(dest="command")

    video_parser = subparsers.add_parser("video", help="単体動画URLを判定")
    video_parser.add_argument("url", help="YouTube動画URL")

    channel_parser = subparsers.add_parser("channel", help="チャンネル人気動画を一括判定")
    channel_parser.add_argument("url", help="YouTubeチャンネルURL")
    channel_parser.add_argument("--top", type=int, default=10, help="判定対象の上位本数")

    discover_parser = subparsers.add_parser("discover", help="競合チャンネルを探索して一括判定")
    source_group = discover_parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--query", help="探索クエリ")
    source_group.add_argument("--seed-channel", dest="seed_channel", help="起点チャンネルURL")
    discover_parser.add_argument("--channels", type=int, default=5, help="探索する候補チャンネル数")
    discover_parser.add_argument("--top", type=int, default=5, help="各チャンネルで判定する上位本数")
    discover_parser.add_argument("--dry-run", action="store_true", help="探索だけ行い動画判定はしない")

    return parser


def parse_args(argv: list[str]) -> argparse.Namespace:
    """後方互換込みで CLI 引数を解釈する。"""
    parser = create_parser()
    if len(argv) >= 2 and argv[1] not in {"video", "channel", "discover", "-h", "--help"}:
        return parser.parse_args(["video", *argv[1:]])
    return parser.parse_args(argv[1:])


def main() -> None:
    args = parse_args(sys.argv)

    if args.command == "video":
        print_single_result(run_video_check(args.url))
        return

    if args.command == "channel":
        from batch_runner import run_channel_batch

        batch_result = run_channel_batch(args.url, args.top)
        print(batch_result["markdown"])
        print(f"\nバッチJSON保存先: {batch_result['summary_path']}")
        return

    if args.command == "discover":
        from discover import run_discovery

        discovery_result = run_discovery(
            query=args.query,
            seed_channel_url=args.seed_channel,
            channels_limit=args.channels,
            top_n=args.top,
            dry_run=args.dry_run,
        )
        print(discovery_result["markdown"])
        print(f"\nDiscovery JSON保存先: {discovery_result['discovery_path']}")
        if discovery_result.get("stock_path"):
            print(f"Stock JSON保存先: {discovery_result['stock_path']}")
        return

    create_parser().print_help(sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
