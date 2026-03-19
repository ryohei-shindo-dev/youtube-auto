"""note記事をシートと同期し、未登録記事を登録 + タイトル変更を行うスクリプト。

Step 1: note.comの記事管理ページから全記事のキー・タイトルを取得
Step 2: シートに未登録の記事を追加登録
Step 3: 指定されたタイトル変更を実行
"""
from __future__ import annotations

import os
import re
import time

from dotenv import load_dotenv
load_dotenv()

from note_image_replace import _get_articles_from_sheet
from note_publish import _launch_browser, _close_browser


# ── タイトル変更対象: {現タイトル(完全一致): 新タイトル} ──
TITLE_CHANGES: dict[str, str] = {
    "オルカンでいいのか揺れる夜に、思い出したいこと": "オルカンでいいのか迷ったら、最初の理由を一行書く",
    "NASDAQ100が目につく夜、実は揺れているのは心": "NASDAQ100が気になるとき、揺れているのは数字より心",
    "「他の投資の方が伸びてる」という夜の不安が、実は当たり前の理由": "他の投資が伸びて見えるのは、仕組みの問題",
    "取り崩しまで20年あるのに、夜眠れなくなるのはなぜ": "取り崩しまで20年あるのに不安になる理由",
    "「自分だけ遅い」と感じる夜に、比較を少し静かにする考え方": "「自分だけ遅い」と感じたら、比較を静かにする",
}


def _get_all_articles_from_note(page) -> list[dict]:
    """note.comの記事管理ページから全記事のキー・タイトル・URLを取得する。"""
    # PENDING_TASKS.md で確認済みのURL・セレクタ
    page.goto("https://note.com/notes")
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    # スクロールして全記事を読み込む（遅延ロード対応）
    prev_count = 0
    for _ in range(20):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1.5)
        links = page.query_selector_all("a.o-articleList__link")
        if len(links) == prev_count:
            break
        prev_count = len(links)

    links = page.query_selector_all("a.o-articleList__link")
    articles = []
    seen_keys = set()
    for link in links:
        href = link.get_attribute("href") or ""
        m = re.search(r"/n/(n[a-zA-Z0-9]+)", href)
        if not m:
            continue
        key = m.group(1)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        title = link.evaluate("""el => {
            const h3 = el.querySelector('h3');
            if (h3) return h3.textContent.trim();
            const titleEl = el.querySelector('[class*="title"]');
            if (titleEl) return titleEl.textContent.trim();
            return '';
        }""")
        url = f"https://note.com/gachiho_motive/n/{key}"
        articles.append({"key": key, "title": title, "url": url})

    return articles


def _register_missing_articles(note_articles: list[dict], sheet_articles: list[dict]):
    """シートに未登録の記事を追加登録する。"""
    import sheets

    sheet_keys = {a["key"] for a in sheet_articles}
    missing = [a for a in note_articles if a["key"] not in sheet_keys]

    if not missing:
        print("未登録の記事はありません。")
        return

    print(f"\n=== シートに未登録: {len(missing)}件 ===")
    for a in missing:
        print(f"  {a['key']} | {a['title'][:50]}")

    # シートに追加
    sheet_id = os.getenv("YOUTUBE_SHEET_ID", "")
    service = sheets.get_service()

    # 現在の最終No.を取得
    max_no = max((a["no"] for a in sheet_articles), default=0)

    rows = []
    for i, a in enumerate(missing, start=max_no + 1):
        # A:No, B:テーマ, C:トピック, D:元Shorts, E:ステータス, F:タイトル, G:生成日, H:公開日, I:note URL
        rows.append([
            i, "追加", a["title"][:50], "add系", "公開済み",
            a["title"], "", "", a["url"],
        ])

    start_row = len(sheet_articles) + 2  # ヘッダー + 既存行 + 1
    range_str = f"{sheets.NOTE_SHEET_NAME}!A{start_row}:I{start_row + len(rows) - 1}"

    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=range_str,
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()

    print(f"\n  → {len(missing)}件をシートに登録しました（No.{max_no + 1}〜{max_no + len(missing)}）")


def _update_title(page, key: str, new_title: str) -> str:
    """1記事のタイトルを変更して下書き保存する。"""
    edit_url = f"https://editor.note.com/notes/{key}/edit/"
    page.goto(edit_url)
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    try:
        title_el = page.wait_for_selector(
            'textarea[placeholder="記事タイトル"]', timeout=10000
        )
        current = title_el.evaluate("el => el.value")
        print(f"  キー: {key}")
        print(f"  旧: {current[:55]}")
        print(f"  新: {new_title[:55]}")

        if current == new_title:
            print(f"  → スキップ（変更不要）")
            return "skip"

        title_el.click()
        title_el.evaluate("el => el.select()")
        time.sleep(0.5)
        page.keyboard.press("Backspace")
        time.sleep(0.5)
        title_el.fill(new_title)
        time.sleep(1)

        save_btn = page.wait_for_selector(
            'button:has-text("下書き保存"), button:has-text("一時保存")',
            timeout=10000,
        )
        save_btn.click()
        time.sleep(3)

        print(f"  → OK（下書き保存）")
        return "ok"

    except Exception as e:
        print(f"  → FAIL: {e}")
        return "fail"


def main():
    # Step 1: ブラウザ起動 → note.comから全記事取得
    pw, context, page = _launch_browser(headless=False)

    print("=== Step 1: note.comから記事一覧を取得 ===")
    note_articles = _get_all_articles_from_note(page)
    print(f"  note.com上の記事: {len(note_articles)}件")

    if not note_articles:
        print("  記事を取得できませんでした。ブラウザでログイン状態を確認してください。")
        _close_browser(pw, context)
        return

    # Step 2: シートと照合 → 未登録記事を登録
    print("\n=== Step 2: シートとの照合・未登録記事の登録 ===")
    sheet_articles = _get_articles_from_sheet()
    print(f"  シート登録済み: {len(sheet_articles)}件")

    _register_missing_articles(note_articles, sheet_articles)

    # Step 3: タイトル変更
    print("\n=== Step 3: タイトル変更 ===")
    # note.comから取得した記事のうち、変更対象をキーで特定
    targets = []
    for na in note_articles:
        if na["title"] in TITLE_CHANGES:
            targets.append((na["key"], na["title"], TITLE_CHANGES[na["title"]]))

    if not targets:
        print("  タイトル変更対象はありません。")
    else:
        print(f"  変更対象: {len(targets)}件\n")
        ok = fail = skip = 0
        for key, old_title, new_title in targets:
            result = _update_title(page, key, new_title)
            if result == "ok":
                ok += 1
            elif result == "skip":
                skip += 1
            else:
                fail += 1
        print(f"\n  タイトル変更完了: OK={ok}, SKIP={skip}, FAIL={fail}")

    print("\n=== 全工程完了 ===")
    _close_browser(pw, context)


if __name__ == "__main__":
    main()
