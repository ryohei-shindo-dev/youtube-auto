"""note記事の高レベルワークフロー。

note_ops.py の低レベル操作を組み合わせて、
投稿・更新・リンク修正などの業務手順を提供する。

使い方:
    from note_workflows import publish_article, rewrite_body, replace_links, verify_article
    from note_workflows import is_linkable, get_linkable_keys, load_manifest
"""
from __future__ import annotations

import json
import pathlib
import re
import time
from playwright.sync_api import Page

SCRIPT_DIR = pathlib.Path(__file__).parent
MANIFEST_PATH = SCRIPT_DIR / "data" / "manifests" / "note_manifest.json"


# ── リンク可否判定（一元化） ──

def load_manifest() -> list[dict]:
    """note_manifest.json を読み込む。note_ops.load_manifest に委譲。"""
    import note_ops
    return note_ops.load_manifest(MANIFEST_PATH)


def is_linkable(article: dict) -> bool:
    """この記事へのリンクカードを挿入してよいか判定する。

    条件: linkable==True（明示的にセットされている場合）、
    または linkable キーがない場合は以下を全て満たすこと:
      - content_type が 'paid' でない
      - md_path に 'paid' を含まない
      - scheduled_at がない（予約投稿中でない）
    """
    # 明示的な linkable フラグがあればそれを使う
    if "linkable" in article:
        return bool(article["linkable"])
    # フラグがなければ推定
    if article.get("content_type") == "paid":
        return False
    if "paid" in (article.get("md_path") or ""):
        return False
    if article.get("scheduled_at"):
        return False
    return True


def get_linkable_keys() -> set[str]:
    """リンクカードとして挿入可能な note_key の集合を返す。"""
    manifest = load_manifest()
    return {a["note_key"] for a in manifest if a.get("note_key") and is_linkable(a)}


def validate_body_urls(body_text: str) -> tuple[str, list[str]]:
    """本文中のnote URLをチェックし、非linkableなURLを除去して返す。

    Returns:
        (cleaned_body, removed_urls)
    """
    linkable_keys = get_linkable_keys()
    url_pattern = re.compile(r"^(https://note\.com/gachiho_motive/n/(n[a-f0-9]+))\s*$")

    cleaned_lines = []
    removed = []
    for line in body_text.splitlines():
        m = url_pattern.match(line.strip())
        if m:
            note_key = m.group(2)
            if note_key not in linkable_keys:
                removed.append(m.group(1))
                continue  # この行を除去
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines), removed


# ── 検証 ──

def verify_article(page: Page, note_id: str) -> dict:
    """公開ページを検証して問題を検出する。

    Returns:
        {"ok": bool, "issues": list[str], "cards": list[str], "title": str}
    """
    page.goto(f"https://note.com/gachiho_motive/n/{note_id}")
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    issues = []

    # 1回のevaluateでカードURL・DOM構造・テキスト内容を一括取得
    data = page.evaluate("""
        () => {
            const article = document.querySelector('.note-common-styles__textnote-body') || document.body;

            // カードURL一覧
            const cards = [];
            article.querySelectorAll('figure').forEach(fig => {
                const iframe = fig.querySelector('iframe');
                if (iframe && iframe.src) {
                    const m = iframe.src.match(/notes\\/(n[a-f0-9]+)/);
                    if (m) cards.push(m[1]);
                }
            });

            // DOM構造（カード前後の空段落チェック用）
            const elements = [];
            const walk = (node) => {
                for (const child of node.children) {
                    if (child.tagName === 'FIGURE') {
                        elements.push({type: 'CARD'});
                    } else if (child.tagName === 'P') {
                        elements.push({type: child.textContent.trim() ? 'P' : 'EMPTY'});
                    } else if (child.children && child.children.length > 0) {
                        walk(child);
                    }
                }
            };
            walk(article);

            // 「閲覧できません」チェック
            const blocked = document.querySelectorAll('*').length > 0
                ? Array.from(document.querySelectorAll('*')).filter(
                    el => el.children.length === 0 && el.textContent.trim() === 'この記事は閲覧できません'
                ).length
                : 0;

            return {
                cards,
                elements,
                blocked,
                bodyText: document.body.innerText,
            };
        }
    """)

    cards = data["cards"]
    dom_elements = data["elements"]
    body_text = data["bodyText"]

    if data["blocked"] > 0:
        issues.append(f"「閲覧できません」カード: {data['blocked']}個")

    # 有料記事リンクチェック
    try:
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            manifest = json.load(f)
        paid_keys = [
            a.get("note_key") for a in manifest
            if (a.get("content_type") == "paid" or "paid" in (a.get("md_path") or ""))
            and a.get("note_key")
        ]
        for pk in paid_keys:
            if pk in body_text:
                issues.append(f"有料記事URL残存: {pk}")
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    # カード前後の空段落チェック
    for i, el in enumerate(dom_elements):
        if el["type"] == "CARD":
            if i > 0 and dom_elements[i - 1]["type"] == "EMPTY":
                issues.append("カード前に空段落")
                break
            if i < len(dom_elements) - 1 and dom_elements[i + 1]["type"] == "EMPTY":
                if i + 1 < len(dom_elements) - 1 and dom_elements[i + 2].get("type") != "CARD":
                    issues.append("カード後に空段落")
                    break

    title = page.title().split("｜")[0].strip()

    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "cards": cards,
        "title": title,
    }


def verify_as_reader(pw, note_id: str, browser=None) -> dict:
    """読者視点（ログアウト状態）で公開ページを検証する。

    著者にだけ見える記事（下書き・限定公開）や、
    ログイン時のみ閲覧可能なリンクカードを検出するため、
    クッキーなしの新しいブラウザコンテキストで検証する。

    Args:
        pw: Playwright インスタンス（launch済み）
        note_id: 検証対象の note_key
        browser: 既存ブラウザインスタンス（バッチ時に使い回すと高速）

    Returns:
        verify_article と同じ形式の dict
    """
    owned_browser = browser is None
    if owned_browser:
        browser = pw.chromium.launch(headless=True)
    context = browser.new_context()  # クッキーなし = ログアウト状態
    page = context.new_page()
    try:
        result = verify_article(page, note_id)
        # 読者視点での追加チェック
        body_text = page.evaluate("() => document.body.innerText")
        if "ログイン" in body_text and "この記事" in body_text:
            result["issues"].append("読者からアクセス不可（ログイン要求）")
            result["ok"] = False
        if "お探しのページは見つかりませんでした" in body_text:
            result["issues"].append("記事が存在しない（404）")
            result["ok"] = False
        page_title = page.title()
        if "ご指定のページが見つかりません" in page_title:
            result["issues"].append("記事が存在しない（404: ご指定のページが見つかりません）")
            result["ok"] = False
    finally:
        context.close()
        if owned_browser:
            browser.close()
    return result


def verify_and_report(page: Page, note_id: str, pw=None) -> bool:
    """検証して結果を表示。問題なければTrue。

    pw を渡すと読者視点（ログアウト状態）でも追加検証する。
    """
    # 著者視点の検証
    result = verify_article(page, note_id)
    if result["ok"]:
        print(f"  ✅ 著者検証OK: {result['title'][:30]} (カード{len(result['cards'])}本)")
    else:
        print(f"  ❌ 著者検証NG: {result['title'][:30]}")
        for issue in result["issues"]:
            print(f"    - {issue}")
        return False

    # 読者視点の検証（pwが渡された場合のみ）
    if pw:
        reader_result = verify_as_reader(pw, note_id)
        if reader_result["ok"]:
            print(f"  ✅ 読者検証OK")
        else:
            print(f"  ❌ 読者検証NG:")
            for issue in reader_result["issues"]:
                print(f"    - {issue}")
            return False

    return True
