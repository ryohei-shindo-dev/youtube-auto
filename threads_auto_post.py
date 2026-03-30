"""Threads 自動投稿スクリプト（MVP: 1日1本・テキストのみ）

ChatGPT運用設計（2026-03-19）に基づく2週間テスト:
- 1日1本、11:30〜14:00でランダム遅延
- リンクなし、ハッシュタグなし、CTAなし
- X在庫を元にThreads版に変形した14本のキューを使用
- 直近7日重複禁止、類似度チェック

Usage:
    # 通常実行（キューから1本投稿）
    python threads_auto_post.py

    # ドライラン（投稿せずに内容確認）
    python threads_auto_post.py --dry-run

    # ランダム遅延なしで即時投稿
    python threads_auto_post.py --no-delay
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import random
import time
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from dotenv import load_dotenv

SCRIPT_DIR = pathlib.Path(__file__).parent
load_dotenv(SCRIPT_DIR / ".env")

CANDIDATES_FILE = SCRIPT_DIR / "data" / "content" / "threads_candidates.json"
HISTORY_FILE = SCRIPT_DIR / "threads_post_history.jsonl"

# 安全策の定数
HISTORY_CHECK_COUNT = 30        # 直近N件との類似度チェック
SIMILARITY_THRESHOLD = 0.55     # これ以上は類似と判定
DUPLICATE_DAYS = 7              # 同一テキスト再投稿禁止日数
MAX_DELAY_MINUTES = 60          # ランダム遅延の最大（分）


def _load_candidates() -> list[dict]:
    """投稿候補を読み込む。"""
    if not CANDIDATES_FILE.exists():
        raise FileNotFoundError(f"候補ファイルが見つかりません: {CANDIDATES_FILE}")
    return json.loads(CANDIDATES_FILE.read_text(encoding="utf-8"))


def _load_history() -> list[dict]:
    """投稿履歴を読み込む。"""
    if not HISTORY_FILE.exists():
        return []
    entries = []
    for line in HISTORY_FILE.read_text(encoding="utf-8").strip().split("\n"):
        if line.strip():
            entries.append(json.loads(line))
    return entries


def _record_history(text: str, post_id: str = "", permalink: str = ""):
    """投稿履歴を記録する。"""
    entry = {
        "text": text,
        "post_id": post_id,
        "permalink": permalink,
        "posted_at": datetime.now().isoformat(),
    }
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _similarity(a: str, b: str) -> float:
    """2つのテキストの類似度を返す。"""
    return SequenceMatcher(None, a, b).ratio()


def _pick_candidate(candidates: list[dict], history: list[dict]) -> dict | None:
    """重複チェック・類似度チェック付きで候補を選択する。"""
    # 直近の投稿テキスト
    recent_texts = [h["text"] for h in history[-HISTORY_CHECK_COUNT:]]

    # 直近 DUPLICATE_DAYS 日の投稿テキスト（完全一致チェック用）
    cutoff = datetime.now() - timedelta(days=DUPLICATE_DAYS)
    recent_exact = set()
    for h in history:
        posted_at = datetime.fromisoformat(h["posted_at"])
        if posted_at >= cutoff:
            recent_exact.add(h["text"])

    # 候補をシャッフル
    shuffled = list(candidates)
    random.shuffle(shuffled)

    best = None
    best_sim = float("inf")

    for c in shuffled:
        text = c["threads_text"]

        # 完全一致チェック
        if text in recent_exact:
            continue

        # 類似度チェック
        if recent_texts:
            max_sim = max(_similarity(text, p) for p in recent_texts)
        else:
            max_sim = 0.0

        if max_sim <= SIMILARITY_THRESHOLD:
            return c  # 十分に異なる候補

        if max_sim < best_sim:
            best_sim = max_sim
            best = c

    return best  # 全て類似の場合、最も類似度が低いものを返す


def _is_enabled() -> bool:
    """緊急停止フラグを確認する。"""
    return os.getenv("THREADS_ENABLED", "true").lower() != "false"


def main():
    parser = argparse.ArgumentParser(description="Threads自動投稿")
    parser.add_argument("--dry-run", action="store_true",
                        help="投稿せずに内容確認")
    parser.add_argument("--no-delay", action="store_true",
                        help="ランダム遅延なしで即時実行")
    args = parser.parse_args()

    # 緊急停止チェック
    if not _is_enabled():
        print("Threads自動投稿は停止中です（THREADS_ENABLED=false）")
        return

    # ランダム遅延（11:30〜14:00の間で投稿するため）
    if not args.no_delay and not args.dry_run:
        delay = random.randint(0, MAX_DELAY_MINUTES * 60)
        delay_min = delay // 60
        print(f"ランダム遅延: {delay_min}分")
        time.sleep(delay)

    # 候補と履歴を読み込み
    candidates = _load_candidates()
    history = _load_history()

    print(f"候補: {len(candidates)}本 / 投稿履歴: {len(history)}件")

    # 候補を選択
    selected = _pick_candidate(candidates, history)
    if not selected:
        print("投稿可能な候補がありません（全て直近で投稿済み）")
        return

    text = selected["threads_text"]
    print(f"\n選択: [{selected['type']}] id={selected['id']}")
    print(f"テキスト:\n{text}\n")

    if args.dry_run:
        print("（ドライラン: 投稿しません）")
        return

    # 投稿
    from threads_upload import post_text
    result = post_text(text)

    if result:
        _record_history(
            text=text,
            post_id=result.get("id", ""),
            permalink=result.get("permalink", ""),
        )
        print("\n投稿完了")
    else:
        print("\n投稿失敗")


if __name__ == "__main__":
    main()
