"""予約公開されたnote記事のカードリンクを差分追加する定期実行スクリプト。

毎日 13:00 / 21:30 に実行される想定。
1. 全記事の公開状態をチェック
2. 前回実行時に未公開だった記事で、今回公開済みになったものを検出
3. 新規公開記事自体に、投稿時に未公開だった関連記事のカードを差分追加
4. 既存記事のうち、新規公開記事へのリンクをmdに持つ記事にカードを差分追加
※ 本文全体の上書きはしない。末尾にカードを追加するだけ。
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
import urllib.error
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
MANIFEST_PATH = SCRIPT_DIR / "note_manifest.json"
STATE_FILE = SCRIPT_DIR / "note_body_update_state.json"

NOTE_KEY_RE = re.compile(r"https://note\.com/gachiho_motive/n/([a-z0-9]+)")
NOTE_URL_FMT = "https://note.com/gachiho_motive/n/{key}"


def load_manifest():
    rows = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {int(r["sheet_no"]): r for r in rows}


def check_published(manifest):
    """全記事の公開状態をチェックし、公開済みの note_key セットを返す。"""
    published_keys: set[str] = set()
    published_sns: set[int] = set()
    for sn in sorted(manifest.keys()):
        row = manifest[sn]
        url = row["url"]
        try:
            req = urllib.request.Request(url, method="HEAD")
            req.add_header("User-Agent", "Mozilla/5.0")
            resp = urllib.request.urlopen(req, timeout=10)
            if resp.getcode() == 200:
                published_keys.add(row["note_key"])
                published_sns.add(sn)
        except Exception:
            pass
        time.sleep(0.2)
    return published_sns, published_keys


def load_state():
    """前回の状態を読み込む。"""
    if STATE_FILE.exists():
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return (
            set(data.get("published", [])),
            data.get("cards", {}),
        )
    return set(), {}


def save_state(published_sns, cards):
    """状態を保存する。"""
    STATE_FILE.write_text(
        json.dumps(
            {
                "published": sorted(published_sns),
                "cards": cards,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def get_md_link_keys(manifest, sn):
    """mdファイルから内部リンクの note_key 一覧を返す。"""
    art = manifest[sn]
    md_path = SCRIPT_DIR / art.get("md_path", "")
    if not md_path.exists():
        return []
    text = md_path.read_text(encoding="utf-8")
    return [m.group(1) for m in NOTE_KEY_RE.finditer(text)]


def main():
    manifest = load_manifest()
    key_to_sn = {r["note_key"]: int(r["sheet_no"]) for r in manifest.values()}
    prev_published_sns, cards_state = load_state()

    print("公開状態チェック中...")
    current_published_sns, current_published_keys = check_published(manifest)
    print(f"  公開済み: {len(current_published_sns)}/{len(manifest)}本")

    # 新しく公開された記事を検出
    newly_published = current_published_sns - prev_published_sns
    if not newly_published:
        print("新しく公開された記事はありません。")
        save_state(current_published_sns, cards_state)
        return

    print(f"\n新規公開: {len(newly_published)}本")
    for sn in sorted(newly_published):
        print(f"  #{sn} {manifest[sn]['sheet_title'][:50]}")

    new_keys = {manifest[sn]["note_key"] for sn in newly_published}

    # 差分追加が必要な記事を収集
    # { sheet_no: [追加すべきURL, ...] }
    append_tasks: dict[int, list[str]] = {}

    # (1) 新規公開記事自体: mdに書かれたリンク先のうち、
    #     投稿時に未公開だったが今は公開済みのもの
    for sn in newly_published:
        sn_str = str(sn)
        already_embedded = set(cards_state.get(sn_str, []))
        md_keys = get_md_link_keys(manifest, sn)
        new_urls = []
        for k in md_keys:
            if k in current_published_keys and k not in already_embedded:
                new_urls.append(NOTE_URL_FMT.format(key=k))
                already_embedded.add(k)
        if new_urls:
            append_tasks[sn] = new_urls
        cards_state[sn_str] = sorted(already_embedded)

    # (2) 既存公開記事: mdに新規公開記事へのリンクがあるもの
    for sn in current_published_sns - newly_published:
        sn_str = str(sn)
        already_embedded = set(cards_state.get(sn_str, []))
        md_keys = get_md_link_keys(manifest, sn)
        new_urls = []
        for k in md_keys:
            if k in new_keys and k not in already_embedded:
                new_urls.append(NOTE_URL_FMT.format(key=k))
                already_embedded.add(k)
        if new_urls:
            append_tasks[sn] = new_urls
        cards_state[sn_str] = sorted(already_embedded)

    if not append_tasks:
        print("\nカード追加の必要はありません。")
        save_state(current_published_sns, cards_state)
        return

    total_cards = sum(len(v) for v in append_tasks.values())
    print(f"\n差分追加: {len(append_tasks)}記事、合計{total_cards}カード\n")

    # Playwright でカード追加
    from note_publish import _launch_browser, _close_browser
    from note_article_updater import _append_card_links

    pw, context, page = _launch_browser(headless=False)
    try:
        ok = fail = 0
        for i, (sn, urls) in enumerate(sorted(append_tasks.items())):
            art = manifest[sn]
            print(f"[{i+1}/{len(append_tasks)}] #{sn} {art['sheet_title'][:40]}… (+{len(urls)}カード)")
            result = _append_card_links(page, art, urls)
            if result == "ok":
                ok += 1
            else:
                fail += 1
                # 失敗した場合、state から追加済みフラグを戻す
                sn_str = str(sn)
                embedded = set(cards_state.get(sn_str, []))
                for url in urls:
                    m = NOTE_KEY_RE.match(url)
                    if m and m.group(1) in embedded:
                        embedded.discard(m.group(1))
                cards_state[sn_str] = sorted(embedded)

            if i < len(append_tasks) - 1:
                time.sleep(5)
            if (i + 1) % 5 == 0 and i < len(append_tasks) - 1:
                page.close()
                page = context.new_page()
                time.sleep(2)

        print(f"\n完了: 成功 {ok} / 失敗 {fail}")
        _close_browser(pw, context, wait_for_user=False)
    except Exception:
        _close_browser(pw, context, wait_for_user=False)
        raise

    save_state(current_published_sns, cards_state)
    print("状態を保存しました。")


if __name__ == "__main__":
    main()
