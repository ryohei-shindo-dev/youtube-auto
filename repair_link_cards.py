"""リンクカード位置ずれ記事の修正スクリプト。

incident-20260327-note-link-card-position の恒久対応。
URL行を含む記事のみを対象に、小ブロック分割方式で本文を再投入する。
ChatGPTレビューに基づき段階的に実施（3→5→10→残り）。
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import time

SCRIPT_DIR = pathlib.Path(__file__).parent
ARTICLES_DIR = SCRIPT_DIR / "note_articles"
MANIFEST_PATH = SCRIPT_DIR / "data" / "manifests" / "note_manifest.json"

_URL_RE = re.compile(r"^https?://\S+$")


def _has_text_after_url(md_path: pathlib.Path) -> bool:
    """URL行の後にテキスト行が続く記事か判定する。

    URL後にテキストがある場合、insertHTMLのカーソル位置ずれで
    カードが本文途中に入る問題が発生する。
    """
    if not md_path.exists():
        return False
    lines = md_path.read_text(encoding="utf-8").splitlines()
    found_url = False
    for line in lines:
        stripped = line.strip()
        if _URL_RE.match(stripped):
            found_url = True
        elif found_url and stripped and not stripped.startswith("#"):
            # URL行の後に空行でもURL行でもない通常テキストがある
            return True
    return False


def _body_from_file(md_path: pathlib.Path) -> str:
    """タイトル行以降の生Markdown本文を返す。"""
    text = md_path.read_text(encoding="utf-8")
    body_lines = []
    past_title = False
    for line in text.split("\n"):
        if line.startswith("# ") and not past_title:
            past_title = True
        else:
            body_lines.append(line)
    return "\n".join(body_lines).strip()


def find_targets() -> list[dict]:
    """修正対象の記事リストを返す。"""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    targets = []
    for entry in manifest:
        md_rel = entry.get("md_path")
        note_key = entry.get("note_key")
        if not md_rel or not note_key:
            continue
        md_path = SCRIPT_DIR / md_rel
        if _has_text_after_url(md_path):
            targets.append({
                "note_key": note_key,
                "md_path": md_path,
                "title": entry.get("sheet_title", md_path.stem)[:50],
            })
    return targets


def repair_batch(targets: list[dict], batch_size: int | None = None):
    """指定件数の記事を修正する。"""
    from note_publish import (
        _launch_browser, _close_browser, _repair_single_article,
    )

    batch = targets[:batch_size] if batch_size else targets
    print(f"\n修正対象: {len(batch)}本（全{len(targets)}本中）\n")
    for i, t in enumerate(batch):
        print(f"  {i+1}. {t['note_key']} — {t['title']}")

    print()
    pw, context, page = _launch_browser(headless=False)
    try:
        repaired = 0
        failed = 0
        for i, target in enumerate(batch):
            body = _body_from_file(target["md_path"])
            if not body:
                print(f"  [{i+1}] スキップ（本文空）: {target['title']}")
                continue

            print(f"  [{i+1}/{len(batch)}] 修正中: {target['title'][:40]}...",
                  end="", flush=True)
            try:
                _repair_single_article(page, target["note_key"], body)
                repaired += 1
                print(" OK")
            except Exception as e:
                failed += 1
                print(f" [エラー] {e}")

            time.sleep(2)

        print(f"\n完了: {repaired}本成功, {failed}本失敗")
        if batch_size and batch_size < len(targets):
            remaining = len(targets) - batch_size
            print(f"残り: {remaining}本（次回 --batch-size で指定）")

    finally:
        _close_browser(pw, context, wait_for_user=False)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="リンクカード位置ずれ記事の修正")
    parser.add_argument("--list", action="store_true", help="対象記事の一覧表示のみ")
    parser.add_argument("--batch-size", type=int, default=None,
                        help="一度に修正する件数（段階実施用）")
    parser.add_argument("--offset", type=int, default=0,
                        help="修正開始位置（前回の続きから）")
    args = parser.parse_args()

    targets = find_targets()
    if not targets:
        print("修正対象の記事がありません。")
        return

    if args.list:
        print(f"修正対象: {len(targets)}本\n")
        for i, t in enumerate(targets):
            print(f"  {i+1:2d}. {t['note_key']} — {t['title']}")
        return

    # offset適用
    if args.offset > 0:
        targets = targets[args.offset:]
        print(f"（offset={args.offset}、残り{len(targets)}本から開始）")

    repair_batch(targets, args.batch_size)


if __name__ == "__main__":
    main()
