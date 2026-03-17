"""X つぶやき型自動投稿スクリプト

偽装行為ラベル対策として、宣伝感のない静かなつぶやきを
ランダム時刻・ランダム選択で投稿する。

Usage:
    # つぶやき型のみ（デフォルト）
    python x_auto_post.py

    # ドライラン（投稿せず内容確認）
    python x_auto_post.py --dry-run

    # 最大遅延を指定（デフォルト60分）
    python x_auto_post.py --max-delay 30
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import time
from datetime import datetime
from difflib import SequenceMatcher

from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).parent / ".env")

MURMUR_FILE = pathlib.Path(__file__).parent / "x_murmur_posts.json"
HISTORY_FILE = pathlib.Path(__file__).parent / "x_post_history.jsonl"
# 直近N件との類似度チェック
HISTORY_CHECK_COUNT = 20
# 類似度しきい値（これ以上は類似と判定）
SIMILARITY_THRESHOLD = 0.55


def _load_murmurs() -> list[str]:
    """つぶやきストックを読み込む。"""
    with open(MURMUR_FILE, encoding="utf-8") as f:
        return json.load(f)


def _load_recent_history(n: int = HISTORY_CHECK_COUNT) -> list[str]:
    """直近の投稿履歴を読み込む。"""
    if not HISTORY_FILE.exists():
        return []
    lines = HISTORY_FILE.read_text(encoding="utf-8").strip().split("\n")
    recent = []
    for line in lines[-n:]:
        try:
            entry = json.loads(line)
            recent.append(entry.get("text", ""))
        except json.JSONDecodeError:
            continue
    return recent


def _similarity(a: str, b: str) -> float:
    """2つのテキストの類似度を返す（0.0〜1.0）。"""
    return SequenceMatcher(None, a, b).ratio()


def _pick_murmur(murmurs: list[str], history: list[str]) -> str | None:
    """重複チェック付きでつぶやきを選択する。"""
    candidates = list(murmurs)
    random.shuffle(candidates)
    for candidate in candidates:
        # 完全一致チェック
        if candidate in history:
            continue
        # 類似度チェック
        too_similar = False
        for past in history:
            if _similarity(candidate, past) > SIMILARITY_THRESHOLD:
                too_similar = True
                break
        if not too_similar:
            return candidate
    # 全てが類似 → 最も類似度が低いものを選ぶ
    if candidates:
        best = min(candidates, key=lambda c: max(
            (_similarity(c, p) for p in history), default=0.0
        ))
        return best
    return None


def _record_history(text: str, tweet_id: str = ""):
    """投稿履歴を記録する。"""
    entry = {
        "text": text,
        "tweet_id": tweet_id,
        "posted_at": datetime.now().isoformat(),
    }
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _random_delay(max_minutes: int):
    """ランダムな遅延を入れる（0〜max_minutes分）。"""
    delay_sec = random.randint(0, max_minutes * 60)
    delay_min = delay_sec / 60
    print(f"  ランダム遅延: {delay_min:.1f}分")
    time.sleep(delay_sec)


def main():
    parser = argparse.ArgumentParser(description="X つぶやき型自動投稿")
    parser.add_argument("--dry-run", action="store_true", help="投稿せず内容確認")
    parser.add_argument("--max-delay", type=int, default=60, help="最大遅延（分）")
    parser.add_argument("--no-delay", action="store_true", help="遅延なし（テスト用）")
    args = parser.parse_args()

    murmurs = _load_murmurs()
    history = _load_recent_history()
    print(f"ストック: {len(murmurs)}本 / 投稿履歴: {len(history)}件")

    selected = _pick_murmur(murmurs, history)
    if not selected:
        print("  [エラー] 投稿可能なつぶやきがありません。")
        return

    print(f"  選択:\n{selected}")
    print(f"  文字数: {len(selected)}")

    if args.dry_run:
        print("  [ドライラン] 投稿しません。")
        return

    # ランダム遅延
    if not args.no_delay:
        _random_delay(args.max_delay)

    # 投稿
    from x_upload import post_tweet
    tweet_id = post_tweet(selected)
    if tweet_id:
        print(f"  投稿成功: tweet_id={tweet_id}")
        _record_history(selected, tweet_id)
    else:
        print("  [エラー] 投稿に失敗しました。")


if __name__ == "__main__":
    main()
