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
MANIFEST_PATH = SCRIPT_DIR / "note_manifest.json"


# ── リンク可否判定（一元化） ──

def load_manifest() -> list[dict]:
    """note_manifest.json を読み込む。"""
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        return json.load(f)


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


def verify_and_report(page: Page, note_id: str) -> bool:
    """検証して結果を表示。問題なければTrue。"""
    result = verify_article(page, note_id)
    if result["ok"]:
        print(f"  ✅ 検証OK: {result['title'][:30]} (カード{len(result['cards'])}本)")
        return True
    else:
        print(f"  ❌ 検証NG: {result['title'][:30]}")
        for issue in result["issues"]:
            print(f"    - {issue}")
        return False
