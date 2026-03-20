"""
note_collect_ids.py
note.com/notes の一覧ページを開き、APIレスポンスから予約記事のIDを収集する。

ステップ1: IDを scheduled_notes.json に保存
ステップ2: fix_note_link_cards.py でそのJSONを読んで修正

使い方:
    python note_collect_ids.py
"""
from __future__ import annotations

import json
import pathlib
import time

from note_publish import _launch_browser, _close_browser

SCRIPT_DIR = pathlib.Path(__file__).parent
OUTPUT_FILE = SCRIPT_DIR / "scheduled_notes.json"
NOTES_LIST_URL = "https://note.com/notes"


def main():
    print("note一覧ページを開いてAPIレスポンスを収集します。")
    print("ブラウザが開いたら、モーダルが出たら手動で閉じてください。")
    print()

    collected_responses: list[dict] = []

    pw, context, page = _launch_browser(headless=False)

    # APIレスポンスを監視
    def on_response(response):
        url = response.url
        # note の記事一覧APIっぽいレスポンスを捕まえる
        if "/api/" in url and response.status == 200:
            try:
                content_type = response.headers.get("content-type", "")
                if "json" in content_type:
                    data = response.json()
                    collected_responses.append({"url": url, "data": data})
                    print(f"  [API] {url[:80]}")
            except Exception:
                pass

    page.on("response", on_response)

    try:
        page.goto(NOTES_LIST_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(5)

        # スクロールして追加データを読み込む
        for i in range(5):
            page.keyboard.press("End")
            time.sleep(2)

        print(f"\n収集したAPIレスポンス: {len(collected_responses)}件")

        # レスポンスからnote IDを抽出
        all_notes: list[dict] = []
        for resp in collected_responses:
            data = resp["data"]
            # レスポンスの構造を探索
            notes_list = _extract_notes(data)
            for note in notes_list:
                if note["id"] not in [n["id"] for n in all_notes]:
                    all_notes.append(note)

        if not all_notes:
            # APIレスポンスから取れなかった場合、収集したデータをダンプ
            dump_path = SCRIPT_DIR / "debug" / "note_api_dump.json"
            dump_path.parent.mkdir(exist_ok=True)
            with open(dump_path, "w", encoding="utf-8") as f:
                json.dump(collected_responses, f, ensure_ascii=False, indent=2)
            print(f"\nAPIレスポンスのダンプを保存: {dump_path}")
            print("このファイルを確認して、記事データの構造を特定してください。")
        else:
            # 予約記事だけフィルタ
            scheduled = [n for n in all_notes if n.get("status") in ("scheduled", "reserved", "draft_reserved")]
            if not scheduled:
                # ステータスでフィルタできない場合は全件保存
                print(f"\n全記事: {len(all_notes)}本（ステータスフィルタ未適用）")
                scheduled = all_notes

            print(f"\n予約記事候補: {len(scheduled)}本")
            for n in scheduled:
                print(f"  {n.get('id', '?')} | {n.get('status', '?')} | {n.get('title', '?')[:40]}")

            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump({"notes": scheduled, "all_notes": all_notes}, f, ensure_ascii=False, indent=2)
            print(f"\n保存先: {OUTPUT_FILE}")

    finally:
        print("\nブラウザを閉じてください。")
        try:
            context.pages[0].wait_for_event("close", timeout=0)
        except Exception:
            pass
        context.close()
        pw.stop()


def _extract_notes(data, depth=0) -> list[dict]:
    """APIレスポンスからnote記事データを再帰的に探す。"""
    results = []
    if depth > 5:
        return results

    if isinstance(data, dict):
        # noteデータっぽい構造を検出
        if "key" in data and "publish_at" in data:
            results.append({
                "id": data.get("key", ""),
                "title": data.get("name", data.get("title", "")),
                "status": data.get("status", ""),
                "publish_at": data.get("publish_at", ""),
                "edit_url": f"https://editor.note.com/notes/{data.get('key', '')}/edit/",
            })
        elif "id" in data and ("name" in data or "title" in data):
            note_id = str(data.get("id", ""))
            key = data.get("key", data.get("note_url", ""))
            if key and len(key) > 5:
                results.append({
                    "id": key,
                    "title": data.get("name", data.get("title", "")),
                    "status": data.get("status", ""),
                    "publish_at": data.get("publish_at", data.get("published_at", "")),
                    "edit_url": f"https://editor.note.com/notes/{key}/edit/",
                })

        for v in data.values():
            results.extend(_extract_notes(v, depth + 1))

    elif isinstance(data, list):
        for item in data:
            results.extend(_extract_notes(item, depth + 1))

    return results


if __name__ == "__main__":
    main()
