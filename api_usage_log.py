"""
api_usage_log.py — Claude API の使用量・コストを記録する。

1リクエストごとに api_usage_log.jsonl に追記する。
日次・テーマ別・モデル別のコスト集計が可能。

使い方:
    from api_usage_log import log_usage
    log_usage(message, model="claude-haiku-4-5-20251001",
              endpoint="script_gen", topic="含み損が続いて眠れない")

    # 集計表示
    python api_usage_log.py
"""

from __future__ import annotations

import json
import pathlib
from datetime import datetime

LOG_FILE = pathlib.Path(__file__).parent / "api_usage_log.jsonl"

# Anthropic 公式価格（2026-03時点、$/MTok）
_PRICING = {
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "cache_read": 0.3},
    "claude-haiku-4-5-20251001": {"input": 1.0, "output": 5.0, "cache_read": 0.1},
}
_DEFAULT_PRICING = {"input": 3.0, "output": 15.0, "cache_read": 0.3}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int,
                   cache_read_tokens: int = 0) -> float:
    """推定コスト（USD）を計算する。"""
    p = _PRICING.get(model, _DEFAULT_PRICING)
    cost = (
        (input_tokens - cache_read_tokens) * p["input"] / 1_000_000
        + cache_read_tokens * p["cache_read"] / 1_000_000
        + output_tokens * p["output"] / 1_000_000
    )
    return round(cost, 6)


def log_usage(
    message,
    model: str,
    endpoint: str,
    topic: str = "",
    theme: str = "",
    num_candidates: int = 1,
) -> dict:
    """APIレスポンスからusage情報を抽出してログファイルに追記する。

    Args:
        message: anthropic.types.Message オブジェクト
        model: 使用モデル名
        endpoint: 呼び出し元（"script_gen", "note_gen" 等）
        topic: トピック文字列
        theme: テーマ名
        num_candidates: 候補数（3候補一括生成の場合は3）

    Returns:
        記録したログエントリ（dict）
    """
    usage = message.usage
    input_tokens = getattr(usage, "input_tokens", 0)
    output_tokens = getattr(usage, "output_tokens", 0)
    cache_read = getattr(usage, "cache_read_input_tokens", 0)
    cache_creation = getattr(usage, "cache_creation_input_tokens", 0)

    cost = _estimate_cost(model, input_tokens, output_tokens, cache_read)

    entry = {
        "timestamp": datetime.now().isoformat(),
        "model": model,
        "endpoint": endpoint,
        "topic": topic[:50],
        "theme": theme,
        "num_candidates": num_candidates,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read,
        "cache_creation_tokens": cache_creation,
        "estimated_cost_usd": cost,
        "request_id": message.id,
    }

    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass

    print(f"  [usage] {model.split('-')[1]}: in={input_tokens} out={output_tokens}"
          f" cache={cache_read} cost=${cost:.4f}")

    return entry


def summarize():
    """ログを集計して表示する。"""
    if not LOG_FILE.exists():
        print("ログファイルがありません。")
        return

    entries = []
    for line in LOG_FILE.read_text(encoding="utf-8").strip().split("\n"):
        if line:
            entries.append(json.loads(line))

    if not entries:
        print("ログエントリがありません。")
        return

    total_cost = sum(e["estimated_cost_usd"] for e in entries)
    total_input = sum(e["input_tokens"] for e in entries)
    total_output = sum(e["output_tokens"] for e in entries)
    total_cache = sum(e["cache_read_tokens"] for e in entries)

    print(f"\n{'='*50}")
    print(f"  API Usage Summary ({len(entries)} requests)")
    print(f"{'='*50}")
    print(f"  合計コスト: ${total_cost:.4f}")
    print(f"  入力トークン: {total_input:,}")
    print(f"  出力トークン: {total_output:,}")
    print(f"  キャッシュ読取: {total_cache:,}")

    # モデル別
    by_model = {}
    for e in entries:
        m = e["model"]
        if m not in by_model:
            by_model[m] = {"count": 0, "cost": 0.0}
        by_model[m]["count"] += 1
        by_model[m]["cost"] += e["estimated_cost_usd"]

    print(f"\n  [モデル別]")
    for m, v in sorted(by_model.items()):
        print(f"    {m}: {v['count']}回, ${v['cost']:.4f}")

    # エンドポイント別
    by_ep = {}
    for e in entries:
        ep = e["endpoint"]
        if ep not in by_ep:
            by_ep[ep] = {"count": 0, "cost": 0.0}
        by_ep[ep]["count"] += 1
        by_ep[ep]["cost"] += e["estimated_cost_usd"]

    print(f"\n  [エンドポイント別]")
    for ep, v in sorted(by_ep.items()):
        print(f"    {ep}: {v['count']}回, ${v['cost']:.4f}")

    # 日別
    by_date = {}
    for e in entries:
        d = e["timestamp"][:10]
        if d not in by_date:
            by_date[d] = {"count": 0, "cost": 0.0}
        by_date[d]["count"] += 1
        by_date[d]["cost"] += e["estimated_cost_usd"]

    print(f"\n  [日別]")
    for d, v in sorted(by_date.items()):
        print(f"    {d}: {v['count']}回, ${v['cost']:.4f}")

    print()


if __name__ == "__main__":
    summarize()
