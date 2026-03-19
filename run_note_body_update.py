"""予約公開されたnote記事の本文を更新する定期実行スクリプト。

毎日 13:00 / 21:30 に実行される想定。
1. 全記事の公開状態をチェック
2. 前回実行時に未公開だった記事で、今回公開済みになったものを検出
3. 新しく公開された記事 + それにリンクしている既存公開記事を --update-body で更新
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
import urllib.error
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
MANIFEST_PATH = SCRIPT_DIR / "note_manifest.json"
STATE_FILE = SCRIPT_DIR / "note_body_update_state.json"

NOTE_KEY_RE = re.compile(r"https://note\.com/gachiho_motive/n/([a-z0-9]+)")


def load_manifest():
    rows = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {int(r["sheet_no"]): r for r in rows}


def check_published(manifest):
    """全記事の公開状態をチェックし、公開済みの sheet_no セットを返す。"""
    published = set()
    for sn in sorted(manifest.keys()):
        url = manifest[sn]["url"]
        try:
            req = urllib.request.Request(url, method="HEAD")
            req.add_header("User-Agent", "Mozilla/5.0")
            resp = urllib.request.urlopen(req, timeout=10)
            if resp.getcode() == 200:
                published.add(sn)
        except Exception:
            pass
        time.sleep(0.2)
    return published


def load_state():
    """前回の公開済みセットを読み込む。"""
    if STATE_FILE.exists():
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return set(data.get("published", []))
    return set()


def save_state(published):
    """公開済みセットを保存する。"""
    STATE_FILE.write_text(
        json.dumps({"published": sorted(published)}, ensure_ascii=False),
        encoding="utf-8",
    )


def find_articles_linking_to(manifest, target_keys, published_sns):
    """target_keys にリンクしている公開済み記事の sheet_no を返す。"""
    linking = set()
    for sn in published_sns:
        art = manifest[sn]
        md_path = SCRIPT_DIR / art.get("md_path", "")
        if not md_path.exists():
            continue
        text = md_path.read_text(encoding="utf-8")
        for m in NOTE_KEY_RE.finditer(text):
            if m.group(1) in target_keys:
                linking.add(sn)
                break
    return linking


def main():
    manifest = load_manifest()
    prev_published = load_state()

    print("公開状態チェック中...")
    current_published = check_published(manifest)
    print(f"  公開済み: {len(current_published)}/{len(manifest)}本")

    # 新しく公開された記事を検出
    newly_published = current_published - prev_published
    if not newly_published:
        print("新しく公開された記事はありません。")
        save_state(current_published)
        return

    print(f"\n新規公開: {len(newly_published)}本")
    for sn in sorted(newly_published):
        print(f"  #{sn} {manifest[sn]['sheet_title'][:50]}")

    # 新しく公開された記事の note_key
    new_keys = {manifest[sn]["note_key"] for sn in newly_published}

    # それにリンクしている既存公開記事を探す
    linking = find_articles_linking_to(manifest, new_keys, current_published - newly_published)

    # 更新対象 = 新規公開 + リンク元
    update_targets = sorted(newly_published | linking)
    print(f"\n更新対象: {len(update_targets)}本（新規{len(newly_published)} + リンク元{len(linking)}）")

    # note_article_updater の update_body を呼び出す
    from note_article_updater import update_body
    update_body(update_targets)

    # 状態を保存
    save_state(current_published)
    print("\n状態を保存しました。")


if __name__ == "__main__":
    main()
