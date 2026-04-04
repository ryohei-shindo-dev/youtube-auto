"""noteダッシュボードから日次アクセスデータを収集してJSONLに記録する。

使い方:
    python note_analytics_collect.py

出力:
    note_analytics_log.jsonl に1行追加（日付・全体数値・記事別ビュー/スキ）
"""
from __future__ import annotations

import json
import pathlib
import time
from datetime import datetime

from note.browser import _launch_browser, _close_browser
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent.parent
LOG_PATH = SCRIPT_DIR / "note_analytics_log.jsonl"

# 毎週固定で追跡する記事（ハブ+有料+注目）
WATCH_LIST = [
    "オルカンでいいのか迷ったら",
    "S&P500が遅く見えるとき",
    "積み立て3年目がしんどい",
    "含み損で眠れない夜、確認回数",
    "売ったら上がった",
    "AI整理テンプレ集",
    "後悔の6パターン",
    "新NISAの比較疲れを整理したいとき",
    "投資で迷った日に、AIで",
    "NASDAQ100が気になるとき",
    "勉強するほど迷う投資脳",
    "配当利回り5%",
]


def _dismiss_blocking_dialogs(page) -> None:
    """分析画面上で前面に出るモーダルを閉じる。"""
    close_selectors = [
        'div[role="dialog"] button[aria-label="閉じる"]',
        'div[role="dialog"] button:has-text("閉じる")',
        'button:has-text("あとで")',
        '[role="dialog"] [aria-label="close"]',
    ]
    for sel in close_selectors:
        try:
            locator = page.locator(sel)
            if locator.count() > 0 and locator.first.is_visible():
                locator.first.click(force=True, timeout=2000)
                time.sleep(0.5)
        except Exception:
            pass


def _get_active_period(page) -> str:
    """現在選択中の期間タブ名を返す。取得できなければ空文字。"""
    selectors = [
        'button[aria-selected="true"]',
        'button[aria-pressed="true"]',
        '[role="tab"][aria-selected="true"]',
    ]
    for sel in selectors:
        try:
            locator = page.locator(sel)
            if locator.count() > 0:
                text = locator.first.inner_text().strip()
                if text in {"週", "月", "全期間"}:
                    return text
        except Exception:
            pass
    return ""


def _select_period(page, period_name: str) -> str:
    """期間タブを安全に切り替え、確認できた期間名を返す。"""
    btn = page.locator(f'button:has-text("{period_name}")').first
    if btn.count() == 0:
        raise RuntimeError(f"period tab not found: {period_name}")

    for _ in range(4):
        _dismiss_blocking_dialogs(page)
        try:
            active = _get_active_period(page)
            if active == period_name:
                return active
            if btn.get_attribute("disabled") is not None:
                time.sleep(1)
                continue
            btn.scroll_into_view_if_needed(timeout=2000)
            btn.click(timeout=5000)
            time.sleep(1)
            active = _get_active_period(page)
            if active == period_name:
                time.sleep(2)
                return active
        except PlaywrightTimeoutError:
            _dismiss_blocking_dialogs(page)
            time.sleep(1)
        except Exception:
            _dismiss_blocking_dialogs(page)
            time.sleep(1)

    _dismiss_blocking_dialogs(page)
    btn.click(force=True, timeout=5000)
    time.sleep(3)
    active = _get_active_period(page)
    if active != period_name:
        raise RuntimeError(f"period mismatch: expected={period_name}, actual={active or 'unknown'}")
    return active


def collect_period(page, period_name: str) -> dict:
    """指定期間（週/月/全期間）のデータを取得"""
    confirmed_period = _select_period(page, period_name)

    body = page.inner_text("body")
    lines = [l.strip() for l in body.split('\n') if l.strip()]

    result = {
        "period": period_name,
        "confirmed_period": confirmed_period,
        "views": 0,
        "comments": 0,
        "likes": 0,
        "articles": [],
    }

    # 全体数値を抽出
    for i, line in enumerate(lines):
        if "全体ビュー" in line and i > 0 and lines[i - 1].replace(",", "").isdigit():
            result["views"] = int(lines[i - 1].replace(",", ""))
        elif line == "コメント" and i > 0 and lines[i - 1].replace(",", "").isdigit():
            result["comments"] = int(lines[i - 1].replace(",", ""))
        elif line == "スキ" and i > 0 and lines[i - 1].replace(",", "").isdigit():
            result["likes"] = int(lines[i - 1].replace(",", ""))

    # 記事別データを抽出
    found_header = False
    for i, line in enumerate(lines):
        if line == "記事" and i + 1 < len(lines) and lines[i + 1] == "ビュー":
            found_header = True
            continue
        if found_header and line == "もっとみる":
            break
        if found_header and not line.isdigit() and line not in [
            "ビュー", "コメント", "スキ", "ビュー数順に並び替えられました"
        ]:
            if i + 1 < len(lines):
                nums = lines[i + 1].split('\t')
                if len(nums) >= 3:
                    try:
                        result["articles"].append({
                            "title": line,
                            "views": int(nums[0]),
                            "comments": int(nums[1]),
                            "likes": int(nums[2]),
                        })
                    except ValueError:
                        pass

    return result


def collect() -> dict:
    """ダッシュボードから週・月・全期間のデータを収集"""
    pw, context, page = _launch_browser(headless=False)
    try:
        page.goto("https://note.com/sitesettings/stats")
        page.wait_for_load_state("networkidle")
        time.sleep(5)
        _dismiss_blocking_dialogs(page)

        data = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "timestamp": datetime.now().isoformat(),
        }

        for period in ["週", "月", "全期間"]:
            result = collect_period(page, period)
            key = {"週": "weekly", "月": "monthly", "全期間": "all_time"}[period]
            data[key] = result

        # ウォッチリスト記事の週次ビュー/スキを抽出
        weekly_articles = data.get("weekly", {}).get("articles", [])
        watch_data = []
        for watch in WATCH_LIST:
            found = False
            for art in weekly_articles:
                if watch in art["title"]:
                    watch_data.append({
                        "keyword": watch,
                        "title": art["title"],
                        "views": art["views"],
                        "likes": art["likes"],
                    })
                    found = True
                    break
            if not found:
                watch_data.append({
                    "keyword": watch,
                    "title": None,
                    "views": 0,
                    "likes": 0,
                })
        data["watch_list"] = watch_data

        return data

    finally:
        try:
            context.close()
        except Exception:
            pass
        try:
            pw.stop()
        except Exception:
            pass


def save(data: dict):
    """JSONLに追記"""
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def print_summary(data: dict):
    """収集結果を表示"""
    w = data.get("weekly", {})
    m = data.get("monthly", {})
    a = data.get("all_time", {})

    print(f"\n=== note アクセス収集 ({data['date']}) ===")
    print(f"  週次:   {w.get('views', 0)}ビュー / {w.get('likes', 0)}スキ / {w.get('comments', 0)}コメント")
    print(f"  月次:   {m.get('views', 0)}ビュー / {m.get('likes', 0)}スキ")
    print(f"  全期間: {a.get('views', 0)}ビュー / {a.get('likes', 0)}スキ")

    like_rate = (w["likes"] / w["views"] * 100) if w.get("views", 0) > 0 else 0
    print(f"  週次スキ率: {like_rate:.1f}%")

    print(f"\n  ウォッチリスト（週次）:")
    for item in data.get("watch_list", []):
        marker = "📌" if item.get("keyword") in ["AI整理テンプレ集", "後悔の6パターン"] else "  "
        print(f"  {marker} {item['keyword'][:25]:25s} → {item['views']:3d}ビュー / {item['likes']}スキ")

    print(f"\n  週次上位12記事:")
    for i, art in enumerate(w.get("articles", [])[:12], 1):
        print(f"  {i:2d}. {art['title'][:45]:45s} {art['views']:3d}ビュー / {art['likes']}スキ")


if __name__ == "__main__":
    data = collect()
    save(data)
    print_summary(data)
    print(f"\n✅ {LOG_PATH} に記録しました")
