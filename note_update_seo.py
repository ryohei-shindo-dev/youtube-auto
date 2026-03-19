"""
note_update_seo.py
公開済みnote記事のタイトル変更 + ハッシュタグ再設定を行うスクリプト。

使い方:
    # 1. タイトル変更のみ（5本）
    python note_update_seo.py --titles

    # 2. タグのセレクタ調査（1本だけ開いて確認）
    python note_update_seo.py --check-tags

    # 3. ハッシュタグ再設定（全56本）
    python note_update_seo.py --tags

    # 4. 両方（タイトル変更 → タグ設定）
    python note_update_seo.py --titles --tags
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
import time

from dotenv import load_dotenv
from playwright.sync_api import Page

from note_publish import _launch_browser, _close_browser
from note_selectors import JS_DUMP_SELECTORS

load_dotenv(pathlib.Path(__file__).parent / ".env")

SCRIPT_DIR = pathlib.Path(__file__).parent
DEBUG_DIR = SCRIPT_DIR / "debug"
DEBUG_DIR.mkdir(exist_ok=True)

# ========== タイトル変更対象（5本） ==========
# note key → 新タイトル のマッピング
# note key はシートから取得するので、ここでは No. → 新タイトル で定義し、
# 実行時にシートから note key を解決する
TITLE_CHANGES: dict[int, str] = {
    # 記事23 (note_12): 何もしなかった日が〜 → 新タイトル
    23: "何もしない日は投資で意味がある｜積み立てを続ける日の考え方",
    # 記事30 (note_add_03): 他人の爆益を見た夜に〜 → 新タイトル
    30: "SNSで他人の爆益を見ると軸が揺れる理由｜比較で不安なときの整理",
    # 記事49 (note_add_22): 何も起きない日が〜 → 新タイトル
    49: "何も起きない日が長期投資で大切な理由",
    # 記事50 (note_add_23): 引き落とされた〜 → 新タイトル
    50: "積み立て投資は引き落とされた日が大切｜続ける意味を整理する",
    # 記事53 (note_add_26): 気づいたら続いていた〜 → 新タイトル
    53: "長期投資が続く人の共通点｜気づいたら続いていた状態を作る",
}

# ========== ハッシュタグ設定（全56本） ==========
# 共通タグ（全記事に設定）
COMMON_TAGS = ["新NISA", "積立投資", "長期投資"]

# 記事No. → 追加タグ
EXTRA_TAGS: dict[int, list[str]] = {
    1: ["含み損", "投資の不安"],
    2: ["投資初心者", "投資の不安"],
    3: ["含み損", "投資の不安"],
    4: ["投資の不安"],
    5: ["投資初心者"],
    6: ["暴落", "インデックス投資"],
    7: ["投資の不安"],
    8: ["老後資金", "投資初心者"],
    9: ["投資初心者", "投資の不安"],
    10: ["投資の不安"],
    11: ["投資の不安"],
    12: ["投資初心者", "投資の不安"],
    13: ["投資の不安"],
    14: ["投資の不安"],
    15: ["含み損", "インデックス投資"],
    16: ["暴落", "インデックス投資"],
    17: ["インデックス投資"],
    18: ["投資初心者"],
    19: ["投資初心者"],
    20: ["暴落", "投資初心者"],
    21: ["ドルコスト平均法", "インデックス投資"],
    22: ["ドルコスト平均法"],
    23: ["投資の不安"],
    24: ["インデックス投資"],
    25: ["投資の不安"],
    26: ["投資の不安"],
    27: ["暴落"],
    28: ["オルカン", "インデックス投資"],
    29: ["SP500", "インデックス投資"],
    30: ["投資の不安"],
    31: ["投資の不安"],
    32: ["投資の不安"],
    33: ["インデックス投資"],
    34: ["配当", "インデックス投資"],
    35: ["オルカン", "投資の不安"],
    36: ["投資初心者", "投資の不安"],
    37: ["投資の不安"],
    38: ["投資の不安"],
    39: ["投資初心者", "インデックス投資"],
    40: ["インデックス投資"],
    41: ["投資の不安"],
    42: ["インデックス投資"],
    43: ["老後資金", "投資の不安"],
    44: ["老後資金", "投資初心者"],
    45: ["投資の不安"],
    46: ["投資の不安"],
    47: ["投資の不安"],
    48: ["投資初心者", "インデックス投資"],
    49: ["投資の不安"],
    50: ["投資の不安"],
    51: ["投資の不安"],
    52: ["投資の不安"],
    53: ["投資の不安"],
    54: ["インデックス投資"],
    55: ["投資の不安"],
    56: ["投資の不安"],
}


def _get_articles_from_sheet() -> list[dict]:
    """note管理シートからNo.・タイトル・URLを取得する。"""
    import sheets

    sheet_id = os.getenv("YOUTUBE_SHEET_ID", "")
    if not sheet_id:
        print("YOUTUBE_SHEET_ID が未設定です。")
        return []

    service = sheets.get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"{sheets.NOTE_SHEET_NAME}!A:I",
    ).execute()

    rows = result.get("values", [])
    articles = []
    for row in rows[1:]:
        if len(row) < 9:
            continue
        no_str = row[0]
        title = row[5] if len(row) > 5 else ""
        url = row[8] if len(row) > 8 else ""
        if not no_str or not url:
            continue

        m = re.search(r"/n/(n[a-zA-Z0-9]+)", url)
        if not m:
            continue

        try:
            no = int(no_str)
        except ValueError:
            continue

        articles.append({
            "no": no,
            "title": title,
            "url": url,
            "key": m.group(1),
        })

    return articles


def _debug_page(page: Page, no: int, label: str):
    """デバッグ情報を採取する。"""
    ss_path = DEBUG_DIR / f"seo_{no:02d}_{label}.png"
    page.screenshot(path=str(ss_path))
    print(f"    スクリーンショット: {ss_path}")
    print(f"    現在のURL: {page.url}")

    # ボタン一覧
    buttons = page.evaluate("""
        () => Array.from(document.querySelectorAll('button'))
            .map(b => b.textContent.trim().substring(0, 60))
            .filter(t => t)
            .slice(0, 20)
    """)
    print(f"    ボタン一覧: {buttons}")


def _update_title(page: Page, article: dict, new_title: str) -> str:
    """1記事のタイトルを更新する。

    Returns: "ok" or "fail"
    """
    no = article["no"]
    key = article["key"]
    old_title = article["title"]

    print(f"  #{no:2d} {old_title[:30]}… → {new_title[:30]}…")

    edit_url = f"https://editor.note.com/notes/{key}/edit/"
    page.goto(edit_url)
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    try:
        # タイトル欄を探す
        title_el = page.wait_for_selector(
            'textarea[placeholder="記事タイトル"]', timeout=10000
        )

        # 全選択して新タイトルを入力
        title_el.click()
        time.sleep(0.5)
        page.keyboard.press("Meta+a")
        time.sleep(0.3)
        title_el.fill(new_title)
        time.sleep(1)

        # 変更検知のためにダミー操作
        page.keyboard.press("End")
        page.keyboard.press(" ")
        page.keyboard.press("Backspace")
        time.sleep(1)

        # 公開設定画面へ
        page.keyboard.press("Escape")
        time.sleep(1)
        publish_nav = page.wait_for_selector(
            'button:has-text("公開に進む")', timeout=10000
        )
        publish_nav.click()
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        # 更新ボタンをクリック
        save_btn = page.wait_for_selector(
            'button:has-text("更新する"), button:has-text("予約投稿")',
            timeout=10000,
        )
        btn_text = save_btn.text_content().strip()
        save_btn.click()
        time.sleep(5)

        print(f"    OK（{btn_text}）")
        return "ok"

    except Exception as e:
        print(f"    失敗: {e}")
        _debug_page(page, no, "title_fail")
        return "fail"


def _check_tag_selectors(page: Page, article: dict):
    """1記事の公開設定画面を開いて、タグ関連のセレクタを調査する。"""
    no = article["no"]
    key = article["key"]

    print(f"\n  #{no:2d} {article['title'][:40]}")
    print(f"  公開設定画面を開きます...")

    # 直接 publish URL へ遷移
    publish_url = f"https://editor.note.com/notes/{key}/publish/"
    page.goto(publish_url)
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    # セレクタ情報を取得（JS_DUMP_SELECTORSはSVG要素でエラーになるため独自版を使う）
    data = page.evaluate("""
        () => {
            const cls = el => (typeof el.className === 'string' ? el.className : '').substring(0, 100);
            const results = {};
            const buttons = document.querySelectorAll('button');
            results['buttons'] = Array.from(buttons).map(b => ({
                text: b.textContent.trim().substring(0, 80),
                ariaLabel: b.getAttribute('aria-label'),
                classes: cls(b),
            })).filter(b => b.text || b.ariaLabel);
            const inputs = document.querySelectorAll('input, textarea');
            results['inputs'] = Array.from(inputs).map(i => ({
                tag: i.tagName.toLowerCase(),
                type: i.type,
                placeholder: i.placeholder,
                name: i.name,
                classes: cls(i),
            }));
            return results;
        }
    """)

    print(f"\n  URL: {page.url}")

    # ハッシュタグ関連の入力欄
    print("\n  --- input/textarea ---")
    for item in data.get("inputs", []):
        print(f"    {json.dumps(item, ensure_ascii=False)}")

    # ボタン
    print("\n  --- buttons ---")
    for item in data.get("buttons", []):
        print(f"    {json.dumps(item, ensure_ascii=False)}")

    # タグ削除ボタンを探す（×マーク等）
    tag_elements = page.evaluate("""
        () => {
            const cls = el => (typeof el.className === 'string' ? el.className : '').substring(0, 150);
            const results = {};

            // 既存タグっぽい要素
            const tags = document.querySelectorAll('[class*="tag"], [class*="Tag"], [class*="hash"]');
            results['tagElements'] = Array.from(tags).map(el => ({
                tag: el.tagName.toLowerCase(),
                text: el.textContent.trim().substring(0, 60),
                classes: cls(el),
                children: Array.from(el.children).map(c => ({
                    tag: c.tagName.toLowerCase(),
                    text: c.textContent.trim().substring(0, 30),
                    role: c.getAttribute('role'),
                    ariaLabel: c.getAttribute('aria-label'),
                })),
            })).slice(0, 20);

            // ×ボタン（削除）を探す
            const closeButtons = document.querySelectorAll('button[aria-label*="削除"], button[aria-label*="remove"], button[aria-label*="close"], span[aria-label*="削除"]');
            results['closeButtons'] = Array.from(closeButtons).map(el => ({
                tag: el.tagName.toLowerCase(),
                ariaLabel: el.getAttribute('aria-label'),
                text: el.textContent.trim().substring(0, 30),
                parentText: el.parentElement?.textContent?.trim()?.substring(0, 60),
            })).slice(0, 20);

            return results;
        }
    """)

    print("\n  --- タグ関連要素 ---")
    for section, items in tag_elements.items():
        print(f"\n  {section}:")
        for item in items:
            print(f"    {json.dumps(item, ensure_ascii=False)}")

    # スクリーンショット
    _debug_page(page, no, "tag_check")

    print("\n  ブラウザを確認してください。閉じるまで待機します。")


def _update_tags(page: Page, article: dict, new_tags: list[str]) -> str:
    """1記事のハッシュタグを再設定する。

    既存タグを全削除 → 新タグを設定。
    Returns: "ok" or "fail"
    """
    no = article["no"]
    key = article["key"]

    print(f"  #{no:2d} {article['title'][:35]}… tags={new_tags}")

    # 直接 publish URL へ遷移
    publish_url = f"https://editor.note.com/notes/{key}/publish/"
    page.goto(publish_url)
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    try:
        # Step 1: 既存タグを全削除
        # タグの×ボタンを探す（aria-label="削除" のボタンまたはspan）
        max_remove = 20  # 安全策: 最大20個まで
        removed = 0
        for _ in range(max_remove):
            # ハッシュタグ削除ボタンを探す
            # noteのタグは span[aria-label="削除"] の親button パターン
            delete_el = page.query_selector(
                'span[aria-label="削除"]'
            )
            if not delete_el:
                # 別パターン: button 内の × テキスト
                delete_el = page.query_selector(
                    '[class*="tag"] button, [class*="Tag"] button'
                )
            if not delete_el:
                break

            try:
                # span の場合は親buttonをクリック
                parent = delete_el.evaluate_handle('el => el.closest("button") || el')
                parent.as_element().click()
                time.sleep(0.5)
                removed += 1
            except Exception:
                break

        if removed:
            print(f"    既存タグ {removed}個 削除")

        # Step 2: 新タグを追加
        tag_input = page.wait_for_selector(
            'input[placeholder="ハッシュタグを追加する"]', timeout=5000
        )
        for tag in new_tags:
            tag_input.fill(tag)
            time.sleep(0.5)
            tag_input.press("Enter")
            time.sleep(0.5)
        print(f"    新タグ {len(new_tags)}個 設定")

        # Step 3: 更新ボタンをクリック
        save_btn = page.wait_for_selector(
            'button:has-text("更新する"), button:has-text("予約投稿")',
            timeout=10000,
        )
        btn_text = save_btn.text_content().strip()
        save_btn.click()
        time.sleep(5)

        print(f"    OK（{btn_text}）")
        return "ok"

    except Exception as e:
        print(f"    失敗: {e}")
        _debug_page(page, no, "tag_fail")
        return "fail"


def do_titles():
    """タイトル変更（5本）を実行する。"""
    print("note管理シートから記事一覧を取得...")
    articles = _get_articles_from_sheet()
    print(f"  {len(articles)}件の記事を検出\n")

    # 対象をフィルタ
    targets = [a for a in articles if a["no"] in TITLE_CHANGES]
    if not targets:
        print("タイトル変更対象が見つかりません。")
        return
    print(f"タイトル変更: {len(targets)}本\n")

    pw, context, page = _launch_browser(headless=False)

    try:
        ok = fail = 0
        for i, article in enumerate(targets):
            print(f"[{i+1}/{len(targets)}]")
            new_title = TITLE_CHANGES[article["no"]]
            result = _update_title(page, article, new_title)
            if result == "ok":
                ok += 1
            else:
                fail += 1

            # 記事間の間隔
            if i < len(targets) - 1:
                time.sleep(8)

            # 3本ごとにページ再生成
            if (i + 1) % 3 == 0 and i < len(targets) - 1:
                page.close()
                page = context.new_page()
                time.sleep(2)

        print(f"\n完了: 成功 {ok} / 失敗 {fail}")
        _close_browser(pw, context, wait_for_user=False)
    except Exception:
        _close_browser(pw, context, wait_for_user=False)
        raise


def do_check_tags():
    """タグセレクタの調査（1本だけ開いて確認）。"""
    print("note管理シートから記事一覧を取得...")
    articles = _get_articles_from_sheet()
    if not articles:
        print("記事が見つかりません。")
        return

    # 最初の1本を使って調査
    article = articles[0]
    pw, context, page = _launch_browser(headless=False)

    try:
        _check_tag_selectors(page, article)
        _close_browser(pw, context, wait_for_user=True)
    except Exception:
        _close_browser(pw, context, wait_for_user=False)
        raise


def do_tags(start_no: int = 0):
    """ハッシュタグ再設定（全56本）を実行する。

    Args:
        start_no: この sheet_no 以降の記事のみ処理する（途中再開用）
    """
    print("note管理シートから記事一覧を取得...")
    articles = _get_articles_from_sheet()
    print(f"  {len(articles)}件の記事を検出")

    if not articles:
        print("記事が見つかりません。")
        return

    # start_no 以降にフィルタ
    if start_no > 0:
        articles = [a for a in articles if a["no"] >= start_no]
        print(f"  #{start_no} 以降: {len(articles)}件\n")
    else:
        print()

    pw, context, page = _launch_browser(headless=False)

    try:
        ok = fail = 0
        for i, article in enumerate(articles):
            no = article["no"]
            extra = EXTRA_TAGS.get(no, [])
            new_tags = COMMON_TAGS + extra

            print(f"[{i+1}/{len(articles)}]")
            result = _update_tags(page, article, new_tags)
            if result == "ok":
                ok += 1
            else:
                fail += 1

            # 記事間の間隔
            if i < len(articles) - 1:
                time.sleep(8)

            # 3本ごとにページ再生成
            if (i + 1) % 3 == 0 and i < len(articles) - 1:
                page.close()
                page = context.new_page()
                time.sleep(2)

        print(f"\n完了: 成功 {ok} / 失敗 {fail}")
        _close_browser(pw, context, wait_for_user=False)
    except Exception:
        _close_browser(pw, context, wait_for_user=False)
        raise


def main():
    parser = argparse.ArgumentParser(description="note SEO最適化ツール")
    parser.add_argument("--titles", action="store_true",
                        help="タイトル変更（5本）")
    parser.add_argument("--check-tags", action="store_true",
                        help="タグセレクタの調査（1本だけ）")
    parser.add_argument("--tags", action="store_true",
                        help="ハッシュタグ再設定（全56本）")
    parser.add_argument("--from", type=int, default=0, dest="start_no",
                        help="--tags の途中再開: この sheet_no 以降を処理")
    args = parser.parse_args()

    if not any([args.titles, args.check_tags, args.tags]):
        parser.print_help()
        return

    if args.titles:
        do_titles()

    if args.check_tags:
        do_check_tags()

    if args.tags:
        do_tags(start_no=args.start_no)


if __name__ == "__main__":
    main()
