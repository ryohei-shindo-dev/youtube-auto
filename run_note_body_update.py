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
import time
from pathlib import Path

from note_article_updater import (
    load_manifest,
    NOTE_KEY_RE,
    _check_published,
)

SCRIPT_DIR = Path(__file__).parent.resolve()
STATE_FILE = SCRIPT_DIR / "note_body_update_state.json"

NOTE_URL_FMT = "https://note.com/gachiho_motive/n/{key}"


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
    prev_published_sns, cards_state = load_state()

    print("公開状態チェック中...")
    current_published_sns, current_published_keys = _check_published(manifest)
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
    append_tasks: dict[int, list[str]] = {}

    def _collect_missing_cards(sn: int, candidate_keys: set[str]):
        """mdのリンクのうち、candidate_keysに含まれ未追加のものを収集する。"""
        sn_str = str(sn)
        already = set(cards_state.get(sn_str, []))
        md_keys = get_md_link_keys(manifest, sn)
        urls = []
        for k in md_keys:
            if k in candidate_keys and k not in already:
                urls.append(NOTE_URL_FMT.format(key=k))
                already.add(k)
        if urls:
            append_tasks[sn] = urls
        cards_state[sn_str] = sorted(already)

    # (1) 新規公開記事: 今公開済みの関連記事カードを追加
    for sn in newly_published:
        _collect_missing_cards(sn, current_published_keys)

    # (2) 既存公開記事: 新規公開記事へのカードを追加
    for sn in current_published_sns - newly_published:
        _collect_missing_cards(sn, new_keys)

    if not append_tasks:
        print("\nカード追加の必要はありません。")
        save_state(current_published_sns, cards_state)
        return

    total_cards = sum(len(v) for v in append_tasks.values())
    print(f"\n差分検出: {len(append_tasks)}記事、合計{total_cards}カード")
    print("  ※ 自動カード追加は廃止されました（D+E方針: 2026-03-28）")
    print("  ※ 既存記事へのカード追加は手動で行ってください")
    for sn, urls in sorted(append_tasks.items()):
        art = manifest[sn]
        print(f"  #{sn} {art['sheet_title'][:40]}… → {len(urls)}カード未追加")
        for url in urls:
            print(f"    {url}")

    # カード追加は実行しない（検出のみ）
    save_state(current_published_sns, cards_state)
    return

    # === 以下は廃止（2026-03-28 D+E方針） ===
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
