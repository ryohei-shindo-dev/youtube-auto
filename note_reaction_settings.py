#!/usr/bin/env python3
"""
note リアクション設定を一括変更するスクリプト。

使い方:
    # 1. まず --discover で設定項目とURLを確認
    python note_reaction_settings.py --discover

    # 2. --dry-run で変更内容を確認（実際には保存しない）
    python note_reaction_settings.py --apply --dry-run

    # 3. 本番実行
    python note_reaction_settings.py --apply
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

# ── note_publish.py と同じブラウザプロファイル ──
USER_DATA_DIR = Path(".note_browser")
OVERVIEW_URL = "https://note.com/settings/reactions"

# ── 設定するメッセージ ──
# キー = URL パス末尾（--discover で確認済み）
REACTION_MESSAGES: dict[str, tuple[str, str]] = {
    # URL末尾: (表示ラベル, メッセージ)
    "/like/note": ("記事にスキ", "ありがとうございます。明日も一緒にガチホしましょう！"),
    "/like/comment": ("コメントにスキ", "コメントうれしいです。ガチホ仲間がいると思うと心強いです"),
    # "/like/membership": スキップ（メンバーシップ未開設）
    "/follow": ("フォローのお礼", "フォローありがとうございます。一緒にガチホ、続けていきましょう"),
    "/magazine_add": ("マガジン追加のお礼", "マガジン追加ありがとうございます。積み上げる投資家の読み物として、書き続けます"),
    "/share": ("シェアのお礼", "シェアありがとうございます。ガチホ仲間がまたひとり増えますように"),
    "/support/description": ("チップエリアの説明文", "「売らずに持ち続ける」を一緒に続けてくれるだけで十分です。もし応援いただけたら、記事を書く力になります"),
    "/support": ("チップのお礼", "応援ありがとうございます。長期投資も、この発信も、コツコツ続けていきます"),
    "/purchase/note": ("記事購入時のお礼", "ご購入ありがとうございます。ガチホの道、一緒に歩きましょう"),
    "/purchase/magazine": ("マガジン購入・購読時のお礼", "ご購読ありがとうございます。長期投資家のための読み物として、書き続けます"),
}


# ── ブラウザ操作 ──


def _launch_browser():
    """永続化されたブラウザコンテキストを起動する。"""
    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        user_data_dir=str(USER_DATA_DIR),
        headless=False,
        viewport={"width": 1280, "height": 900},
        locale="ja-JP",
    )
    page = context.pages[0] if context.pages else context.new_page()
    return pw, context, page


def _find_change_links(page: Page) -> list[dict]:
    """overview ページから全「変更」リンクとその周辺テキスト・hrefを収集する。"""
    return page.evaluate("""() => {
        const links = document.querySelectorAll('a');
        const results = [];
        for (const a of links) {
            if (!a.textContent.includes('変更')) continue;
            // 親要素を辿ってセクションのラベルテキストを取得
            let ctx = '';
            let el = a;
            for (let i = 0; i < 8; i++) {
                el = el.parentElement;
                if (!el) break;
                const text = el.textContent.trim();
                if (text.length > 10 && text.length < 300) {
                    ctx = text;
                    break;
                }
            }
            results.push({
                href: a.href,
                context: ctx.slice(0, 150),
            });
        }
        return results;
    }""")


def _match_message(href: str) -> tuple[str, str, str] | None:
    """URLパスから対応する (ラベル, メッセージ, URLキー) を探す。"""
    # 長いパスから先にマッチ（/support/description を /support より先に）
    for url_key in sorted(REACTION_MESSAGES, key=len, reverse=True):
        if href.endswith(url_key):
            label, msg = REACTION_MESSAGES[url_key]
            return label, msg, url_key
    return None


def _fill_and_save(page: Page, message: str, dry_run: bool) -> bool:
    """個別設定ページでメッセージを入力して保存する。"""
    time.sleep(1)

    # メッセージ入力欄を探す
    input_el = None
    for selector in [
        'input[type="text"]',
        "textarea",
    ]:
        el = page.query_selector(selector)
        if el and el.is_visible():
            input_el = el
            break

    if not input_el:
        print("    ⚠ メッセージ入力欄が見つかりません")
        # デバッグ用: ページ上のinput/textareaを表示
        fields = page.evaluate("""() => {
            const els = document.querySelectorAll('input, textarea');
            return Array.from(els).map(e => ({
                tag: e.tagName, type: e.type, placeholder: e.placeholder,
                visible: e.offsetParent !== null
            }));
        }""")
        print(f"    フィールド一覧: {fields}")
        return False

    current = input_el.input_value()
    print(f"    現在: {current or '(未設定)'}")
    print(f"    → 変更後: {message}")

    if dry_run:
        print("    (dry-run: スキップ)")
        return True

    # 入力欄をクリア → 新しいメッセージを入力
    input_el.click()
    input_el.fill("")
    input_el.fill(message)
    time.sleep(0.5)

    # 保存ボタンを探してクリック
    save_btn = None
    for selector in [
        'button:has-text("保存")',
        'button:has-text("設定する")',
        'button:has-text("変更を保存")',
        'button[type="submit"]',
    ]:
        btn = page.query_selector(selector)
        if btn and btn.is_visible():
            save_btn = btn
            break

    if not save_btn:
        print("    ⚠ 保存ボタンが見つかりません")
        buttons = page.evaluate("""() =>
            Array.from(document.querySelectorAll('button'))
                .map(b => b.textContent.trim())
                .filter(t => t.length > 0)
        """)
        print(f"    ボタン一覧: {buttons}")
        return False

    save_btn.click()
    time.sleep(2)
    print("    ✓ 保存完了")
    return True


# ── コマンド ──


def cmd_discover(page: Page):
    """設定ページの構造を確認して表示する。"""
    page.goto(OVERVIEW_URL)
    page.wait_for_load_state("networkidle")
    time.sleep(1)

    links = _find_change_links(page)
    print(f"\n「変更」リンク {len(links)} 件:\n")

    for i, link in enumerate(links, 1):
        match = _match_message(link["href"])
        if match:
            label, msg, _key = match
            status = f"✓ {label} → 「{msg[:30]}…」"
        else:
            status = "⏭ スキップ（対象外）"
        ctx_clean = link["context"].replace("\n", " ")[:80]
        print(f"  {i}. [{ctx_clean}]")
        print(f"     URL: {link['href']}")
        print(f"     {status}")
        print()


def cmd_apply(page: Page, dry_run: bool):
    """全設定を一括で変更する。"""
    page.goto(OVERVIEW_URL)
    page.wait_for_load_state("networkidle")
    time.sleep(1)

    links = _find_change_links(page)

    # マッチする設定項目を収集
    targets: list[dict] = []
    for link in links:
        m = _match_message(link["href"])
        if m:
            label, msg, _key = m
            targets.append({"label": label, "message": msg, "href": link["href"]})

    print(f"\n設定対象: {len(targets)} 件\n")
    for t in targets:
        print(f"  - {t['label']}: 「{t['message']}」")

    if not dry_run:
        ans = input("\n実行しますか？ (y/N) → ")
        if ans.lower() != "y":
            print("キャンセルしました")
            return

    succeeded = 0
    failed = 0

    for t in targets:
        print(f"\n[{t['label']}]")
        page.goto(t["href"])
        page.wait_for_load_state("networkidle")

        ok = _fill_and_save(page, t["message"], dry_run)
        if ok:
            succeeded += 1
        else:
            failed += 1

        # overview に戻る
        page.goto(OVERVIEW_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(1)

    print(f"\n=== 完了: 成功 {succeeded} / 失敗 {failed} ===")


def main():
    parser = argparse.ArgumentParser(description="note リアクション設定の一括変更")
    parser.add_argument("--discover", action="store_true",
                        help="設定ページの構造を確認")
    parser.add_argument("--apply", action="store_true",
                        help="メッセージを一括設定")
    parser.add_argument("--dry-run", action="store_true",
                        help="実際には保存しない")
    args = parser.parse_args()

    if not args.discover and not args.apply:
        parser.print_help()
        sys.exit(1)

    pw, context, page = _launch_browser()

    try:
        if args.discover:
            cmd_discover(page)
        elif args.apply:
            cmd_apply(page, dry_run=args.dry_run)
    finally:
        context.close()
        pw.stop()


if __name__ == "__main__":
    main()
