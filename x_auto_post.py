"""X 自動投稿スクリプト（つぶやき型 + リンク型）

偽装行為ラベル対策として、宣伝感のない静かなつぶやきを主軸に、
YouTube/noteリンク付きポストを低頻度で混ぜる。

Usage:
    # 通常実行（つぶやき or リンクを自動判定）
    python x_auto_post.py

    # つぶやきのみ強制
    python x_auto_post.py --murmur

    # リンク付きのみ強制
    python x_auto_post.py --link

    # ドライラン
    python x_auto_post.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
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
# リンク付きポストの確率（約30%）
LINK_POST_RATIO = 0.30

# リンク付きポストの導入文（宣伝感を抑えた表現）
_LINK_INTROS_YOUTUBE = [
    "今日の整理。",
    "静かに続けている人へ。",
    "揺れた日に見る用。",
    "こういう話を続けています。",
    "短い整理。",
]


def _load_murmurs() -> list[str]:
    """つぶやきストックを読み込む。"""
    with open(MURMUR_FILE, encoding="utf-8") as f:
        return json.load(f)


def _load_recent_history(n: int = HISTORY_CHECK_COUNT) -> tuple[list[str], list[str]]:
    """直近の投稿履歴を読み込む。テキストとタイプを同時に返す。"""
    if not HISTORY_FILE.exists():
        return [], []
    lines = HISTORY_FILE.read_text(encoding="utf-8").strip().split("\n")
    texts = []
    types = []
    for line in lines[-n:]:
        try:
            entry = json.loads(line)
            texts.append(entry.get("text", ""))
            types.append(entry.get("type", "murmur"))
        except json.JSONDecodeError:
            continue
    return texts, types


def _similarity(a: str, b: str) -> float:
    """2つのテキストの類似度を返す（0.0〜1.0）。"""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _pick_murmur(murmurs: list[str], history: list[str]) -> str | None:
    """重複チェック付きでつぶやきを選択する。"""
    candidates = list(murmurs)
    random.shuffle(candidates)
    best_candidate = None
    best_score = float("inf")
    for candidate in candidates:
        if candidate in history:
            continue
        max_sim = max((_similarity(candidate, p) for p in history), default=0.0)
        if max_sim <= SIMILARITY_THRESHOLD:
            return candidate  # 十分に異なる候補が見つかった
        if max_sim < best_score:
            best_score = max_sim
            best_candidate = candidate
    return best_candidate  # 全て類似の場合、最も類似度が低いものを返す


def _get_recent_youtube_url() -> tuple[str, str] | None:
    """シートから直近の公開済みYouTube Shorts URLとタイトルを取得する。"""
    try:
        import sheets
        sheet_id = os.getenv("YOUTUBE_SHEET_ID", "")
        if not sheet_id:
            return None
        svc = sheets.get_service()
        result = svc.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range="投稿管理!A:N",
        ).execute()
        rows = result.get("values", [])
        C = sheets.COL
        # X未告知優先、なければ直近の公開済みを返す
        fallback = None
        for row in reversed(rows[1:]):
            status = sheets.get_cell(row, C["status"])
            yt_url = sheets.get_cell(row, C["youtube_url"])
            title = sheets.get_cell(row, C["title"])
            if status in ("公開済み", "partial") and yt_url:
                x_url = sheets.get_cell(row, C["x_url"])
                if not x_url:
                    return yt_url, title  # X未告知を優先
                if fallback is None:
                    fallback = (yt_url, title)
        return fallback
    except Exception as e:
        print(f"  [警告] YouTube URL取得エラー: {e}")
    return None


def _build_link_post() -> str | None:
    """リンク付きポストを組み立てる。YouTube優先。"""
    yt = _get_recent_youtube_url()
    if yt:
        url, title = yt
        intro = random.choice(_LINK_INTROS_YOUTUBE)
        # タイトルから #Shorts やパイプ以降を除去
        clean_title = title.split("｜")[0].split("|")[0].replace("#Shorts", "").strip()
        return f"{intro}\n\n{clean_title}\n{url}"
    return None


def _should_post_link(force_murmur: bool, force_link: bool, recent_types: list[str]) -> bool:
    """リンク付きポストにするか判定する。"""
    if force_murmur:
        return False
    if force_link:
        return True
    # 直近でリンク連投を避ける
    if recent_types and recent_types[-1] == "link":
        return False
    return random.random() < LINK_POST_RATIO


def _record_history(text: str, tweet_id: str = "", post_type: str = "murmur"):
    """投稿履歴を記録する。"""
    entry = {
        "text": text,
        "tweet_id": tweet_id,
        "type": post_type,
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
    parser = argparse.ArgumentParser(description="X 自動投稿（つぶやき+リンク）")
    parser.add_argument("--dry-run", action="store_true", help="投稿せず内容確認")
    parser.add_argument("--max-delay", type=int, default=60, help="最大遅延（分）")
    parser.add_argument("--no-delay", action="store_true", help="遅延なし（テスト用）")
    parser.add_argument("--murmur", action="store_true", help="つぶやき型を強制")
    parser.add_argument("--link", action="store_true", help="リンク付きを強制")
    args = parser.parse_args()

    # 履歴を1回だけ読み込む
    history_texts, history_types = _load_recent_history()

    # リンク付きにするか判定
    use_link = _should_post_link(args.murmur, args.link, history_types)

    if use_link:
        print("モード: リンク付き")
        selected = _build_link_post()
        post_type = "link"
        if not selected:
            print("  リンク付きポストを組み立てられません。つぶやき型にフォールバック。")
            use_link = False

    if not use_link:
        print("モード: つぶやき型")
        murmurs = _load_murmurs()
        print(f"  ストック: {len(murmurs)}本 / 投稿履歴: {len(history_texts)}件")
        selected = _pick_murmur(murmurs, history_texts)
        post_type = "murmur"

    if not selected:
        print("  [エラー] 投稿可能なテキストがありません。")
        return

    print(f"  投稿内容:\n{selected}")
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
        _record_history(selected, tweet_id, post_type)
    else:
        print("  [エラー] 投稿に失敗しました。")


if __name__ == "__main__":
    main()
