"""
note_publish_additional.py
追加したnote記事29本を投稿・予約投稿するためのスクリプト。

使い方:
    python note_publish_additional.py --login
    python note_publish_additional.py --post-all
"""

from __future__ import annotations

import argparse
import pathlib
import re
import time

from playwright.sync_api import Page

from note_publish import _launch_browser, _close_browser, _markdown_to_note_html

SCRIPT_DIR = pathlib.Path(__file__).parent
ARTICLES_DIR = SCRIPT_DIR / "note_articles"
IMAGES_DIR = SCRIPT_DIR / "note_images"

ARTICLE_SPECS = [
    # --- 投稿済み（add_01〜03） ---
    {
        "id": "add_01",
        "title": "オルカンでいいのか揺れる夜に、思い出したいこと",
        "article_path": ARTICLES_DIR / "note_add_01_オルカンでいいのか揺れる夜.md",
        "image_path": IMAGES_DIR / "note_add_01.png",
        "schedule": None,  # 即時投稿済み（3/14）
    },
    {
        "id": "add_02",
        "title": "S&P500が遅く見えるとき、気持ちが揺れる理由",
        "article_path": ARTICLES_DIR / "note_add_02_S&P500が遅く見えるとき.md",
        "image_path": IMAGES_DIR / "note_add_02.png",
        "schedule": "2026-03-15 21:00",
    },
    {
        "id": "add_03",
        "title": "他人の爆益を見た夜に、軸が揺れるのは自然です",
        "article_path": ARTICLES_DIR / "note_add_03_他人の爆益を見た夜に軸が揺れる.md",
        "image_path": IMAGES_DIR / "note_add_03.png",
        "schedule": "2026-03-16 21:00",
    },
    # --- 予約投稿（add_04〜29: 3/17〜3/29、1日2本 12:30+21:00） ---
    {
        "id": "add_28",
        "title": "画面を見なかった日が、一番いい投資判断だった",
        "article_path": ARTICLES_DIR / "note_add_28_画面を見なかった日が、一番いい.md",
        "image_path": IMAGES_DIR / "note_add_28.png",
        "schedule": "2026-03-17 12:30",
    },
    {
        "id": "add_04",
        "title": "何もしないことが不安になる日に、確認したいこと",
        "article_path": ARTICLES_DIR / "note_add_04_何もしないことが不安になる日.md",
        "image_path": IMAGES_DIR / "note_add_04.png",
        "schedule": "2026-03-17 21:00",
    },
    {
        "id": "add_29",
        "title": "他人の成績表を見ない日が、いちばん崩れにくい",
        "article_path": ARTICLES_DIR / "note_add_29_他人を見ない日が、いちばん崩れ.md",
        "image_path": IMAGES_DIR / "note_add_29.png",
        "schedule": "2026-03-18 12:30",
    },
    {
        "id": "add_05",
        "title": "正しいのに退屈で続かない。その感覚の整理",
        "article_path": ARTICLES_DIR / "note_add_05_正しいのに退屈で続かない.md",
        "image_path": IMAGES_DIR / "note_add_05.png",
        "schedule": "2026-03-18 21:00",
    },
    {
        "id": "add_06",
        "title": "NASDAQ100が目につく夜、実は揺れているのは心",
        "article_path": ARTICLES_DIR / "note_add_06_NASDAQ100に目移りした.md",
        "image_path": IMAGES_DIR / "note_add_06.png",
        "schedule": "2026-03-19 12:30",
    },
    {
        "id": "add_10",
        "title": "積み立て額を減らしたくなった夜に、まず確認したい「3ヶ月前の自分の気持ち」",
        "article_path": ARTICLES_DIR / "note_add_10_積み立て設定を変えたくなる夜に.md",
        "image_path": IMAGES_DIR / "note_add_10.png",
        "schedule": "2026-03-19 21:00",
    },
    {
        "id": "add_07",
        "title": "配当利回り5%の誘いに、過去データを確認してから返事する",
        "article_path": ARTICLES_DIR / "note_add_07_高配当に乗り換えたくなる日に、.md",
        "image_path": IMAGES_DIR / "note_add_07.png",
        "schedule": "2026-03-20 12:30",
    },
    {
        "id": "add_12",
        "title": "投資信託を増やしすぎると、迷いが深くなることがあります",
        "article_path": ARTICLES_DIR / "note_add_12_投資信託を増やしすぎると、安心.md",
        "image_path": IMAGES_DIR / "note_add_12.png",
        "schedule": "2026-03-20 21:00",
    },
    {
        "id": "add_09",
        "title": "勉強するほど迷う投資脳を、シンプルに戻す方法",
        "article_path": ARTICLES_DIR / "note_add_09_投資の勉強をするほど、軸がぶれ.md",
        "image_path": IMAGES_DIR / "note_add_09.png",
        "schedule": "2026-03-21 12:30",
    },
    {
        "id": "add_16",
        "title": "取り崩しまで20年あるのに、夜眠れなくなるのはなぜ",
        "article_path": ARTICLES_DIR / "note_add_16_取り崩しがまだ先なのに、不安に.md",
        "image_path": IMAGES_DIR / "note_add_16.png",
        "schedule": "2026-03-21 21:00",
    },
    {
        "id": "add_08",
        "title": "オルカンを持っているのに、置いていかれる気がするとき",
        "article_path": ARTICLES_DIR / "note_add_08_オルカンを持っているのに、置い.md",
        "image_path": IMAGES_DIR / "note_add_08.png",
        "schedule": "2026-03-22 12:30",
    },
    {
        "id": "add_13",
        "title": "投資商品を減らしたら、なぜか心が落ち着いた話",
        "article_path": ARTICLES_DIR / "note_add_13_商品を減らした方が落ち着く人が.md",
        "image_path": IMAGES_DIR / "note_add_13.png",
        "schedule": "2026-03-22 21:00",
    },
    {
        "id": "add_11",
        "title": "SNSで正解を見すぎた日に、心が疲れる理由",
        "article_path": ARTICLES_DIR / "note_add_11_SNSで誰かの正解を見すぎた日.md",
        "image_path": IMAGES_DIR / "note_add_11.png",
        "schedule": "2026-03-23 12:30",
    },
    {
        "id": "add_17",
        "title": "40代で始めたのに、もう遅い気がする理由",
        "article_path": ARTICLES_DIR / "note_add_17_老後まで遠いのに、もう間に合わ.md",
        "image_path": IMAGES_DIR / "note_add_17.png",
        "schedule": "2026-03-23 21:00",
    },
    {
        "id": "add_14",
        "title": "他人の資産額に見えた自分の積み立ての小ささ",
        "article_path": ARTICLES_DIR / "note_add_14_他人の資産額を見た夜に、自分の.md",
        "image_path": IMAGES_DIR / "note_add_14.png",
        "schedule": "2026-03-24 12:30",
    },
    {
        "id": "add_18",
        "title": "積み立て20年、ゴールが見えない焦燥感への向き合い方",
        "article_path": ARTICLES_DIR / "note_add_18_積み立てを続けているのに、いつ.md",
        "image_path": IMAGES_DIR / "note_add_18.png",
        "schedule": "2026-03-24 21:00",
    },
    {
        "id": "add_15",
        "title": "「他の投資の方が伸びてる」という夜の不安が、実は当たり前の理由",
        "article_path": ARTICLES_DIR / "note_add_15_「もっと伸びるものがある」と思.md",
        "image_path": IMAGES_DIR / "note_add_15.png",
        "schedule": "2026-03-25 12:30",
    },
    {
        "id": "add_19",
        "title": "増減に一喜一憂する前に、まず「目的」を思い出すこと",
        "article_path": ARTICLES_DIR / "note_add_19_増えても減っても落ち着かない人.md",
        "image_path": IMAGES_DIR / "note_add_19.png",
        "schedule": "2026-03-25 21:00",
    },
    {
        "id": "add_22",
        "title": "何も起きない日が、いちばん長期投資らしい",
        "article_path": ARTICLES_DIR / "note_add_22_何も起きない日が、いちばん長期.md",
        "image_path": IMAGES_DIR / "note_add_22.png",
        "schedule": "2026-03-26 12:30",
    },
    {
        "id": "add_20",
        "title": "「自分だけ遅い」と感じる夜に、比較を少し静かにする考え方",
        "article_path": ARTICLES_DIR / "note_add_20_「自分だけ遅い」と感じる夜に、.md",
        "image_path": IMAGES_DIR / "note_add_20.png",
        "schedule": "2026-03-26 21:00",
    },
    {
        "id": "add_23",
        "title": "引き落とされた。それで十分です",
        "article_path": ARTICLES_DIR / "note_add_23_今日も引き落とされた。それで十.md",
        "image_path": IMAGES_DIR / "note_add_23.png",
        "schedule": "2026-03-27 12:30",
    },
    {
        "id": "add_21",
        "title": "新NISAで何を買うか迷った時、つい変えてしまう心理",
        "article_path": ARTICLES_DIR / "note_add_21_新NISAで何を買うかより、変.md",
        "image_path": IMAGES_DIR / "note_add_21.png",
        "schedule": "2026-03-27 21:00",
    },
    {
        "id": "add_24",
        "title": "増えてる実感がない日ほど、積み立ては効いている",
        "article_path": ARTICLES_DIR / "note_add_24_増えてる実感がない日ほど、積み.md",
        "image_path": IMAGES_DIR / "note_add_24.png",
        "schedule": "2026-03-28 12:30",
    },
    {
        "id": "add_25",
        "title": "相場が冷え込む時こそ、積み立ては本当の出番です",
        "article_path": ARTICLES_DIR / "note_add_25_積み立ては、盛り上がらない日ほ.md",
        "image_path": IMAGES_DIR / "note_add_25.png",
        "schedule": "2026-03-28 21:00",
    },
    {
        "id": "add_26",
        "title": "気づいたら続いていた。それが長期投資の正体",
        "article_path": ARTICLES_DIR / "note_add_26_気づいたら続いていた。それが長.md",
        "image_path": IMAGES_DIR / "note_add_26.png",
        "schedule": "2026-03-29 12:30",
    },
    {
        "id": "add_27",
        "title": "派手さゼロ。でも20年後、それが最強になる",
        "article_path": ARTICLES_DIR / "note_add_27_地味すぎる。でもそれが一番強い.md",
        "image_path": IMAGES_DIR / "note_add_27.png",
        "schedule": "2026-03-29 21:00",
    },
]


def _load_article(spec: dict) -> tuple[str, str, pathlib.Path]:
    text = spec["article_path"].read_text(encoding="utf-8")
    title = ""
    body_lines = []
    for line in text.split("\n"):
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        else:
            body_lines.append(line)
    body = "\n".join(body_lines).strip()
    return title, _markdown_to_note_html(body), spec["image_path"]


def _upload_header_image(page: Page, image_path: pathlib.Path):
    if not image_path.exists():
        return

    img_btn = page.wait_for_selector('button[aria-label="画像を追加"]', timeout=5000)
    img_btn.click()
    time.sleep(1)

    with page.expect_file_chooser() as fc_info:
        page.click('button:has-text("画像をアップロード")')
    fc_info.value.set_files(str(image_path))
    time.sleep(3)

    save_btn = page.wait_for_selector('.ReactModal__Content button:has-text("保存")', timeout=5000)
    save_btn.click()
    time.sleep(2)


_URL_LINE_RE = re.compile(r"^https?://\S+$")

# noteエディタ内の埋め込みカード検出用セレクタ
_EMBED_SELECTORS = [
    'div.ProseMirror iframe',
    'div.ProseMirror [data-embed-card]',
    'div.ProseMirror .embed-card',
    'div.ProseMirror [class*="embed"]',
]


def _wait_for_embed_card(page: Page, before_count: int, timeout: int = 5000) -> bool:
    """埋め込みカードが新たに出現したかを判定する。"""
    import time as _time
    deadline = _time.time() + timeout / 1000
    while _time.time() < deadline:
        for sel in _EMBED_SELECTORS:
            count = page.locator(sel).count()
            if count > before_count:
                return True
        _time.sleep(0.3)
    return False


def _count_embed_cards(page: Page) -> int:
    """現在の埋め込みカード数を返す。"""
    for sel in _EMBED_SELECTORS:
        count = page.locator(sel).count()
        if count > 0:
            return count
    return 0


def _fill_editor(page: Page, title: str, body_text: str):
    title_el = page.wait_for_selector('textarea[placeholder="記事タイトル"]', timeout=10000)
    title_el.click()
    page.keyboard.type(title, delay=10)
    time.sleep(1)
    current_title = title_el.input_value().strip()
    if current_title != title:
        raise RuntimeError(f"タイトル入力未反映: {current_title!r}")

    body = page.locator('div.ProseMirror[role="textbox"]')
    body.click()

    # 全行を1行ずつ入力。URL行は press_sequentially + Enter でカード変換。
    # insert_text は使わない（noteのProseMirrorで改行・カード変換が不安定になるため）。
    for line in body_text.splitlines():
        stripped = line.strip()

        if _URL_LINE_RE.match(stripped):
            # URL行: タイプ → Enter → カードDOM出現待ち
            before = _count_embed_cards(page)
            body.press_sequentially(stripped, delay=15)
            body.press("Enter")

            embedded = _wait_for_embed_card(page, before, timeout=5000)
            if embedded:
                print(f"    カード変換成功: {stripped[:50]}")
            else:
                print(f"    [警告] カード変換未確認: {stripped[:50]}")
                # 失敗時もう1回 Enter を試す
                body.press("Enter")
                time.sleep(1)
        else:
            if line:
                body.press_sequentially(line, delay=3)
            body.press("Enter")

    time.sleep(1)
    current_body = body.inner_text().strip()
    if len(current_body) < 50:
        raise RuntimeError("本文入力がnote側で確定していません")
    body.press("Escape")
    time.sleep(0.5)


def _go_publish(page: Page):
    save_btn = page.wait_for_selector(
        'button:has-text("下書き保存"), button:has-text("一時保存")',
        timeout=10000,
    )
    save_btn.click()
    time.sleep(3)
    publish_nav = page.wait_for_selector('button:has-text("公開に進む")', timeout=10000)
    publish_nav.click()
    page.wait_for_load_state("networkidle")
    time.sleep(2)


def _set_schedule(page: Page, schedule_str: str):
    from datetime import datetime

    dt = datetime.strptime(schedule_str, "%Y-%m-%d %H:%M")
    schedule_btn = page.wait_for_selector('button:has-text("日時の設定")', timeout=5000)
    schedule_btn.scroll_into_view_if_needed()
    schedule_btn.click()
    time.sleep(1)

    day = dt.day
    date_cell = page.wait_for_selector(
        f'.react-datepicker__day--0{day:02d}:not(.react-datepicker__day--outside-month)',
        timeout=5000,
    )
    date_cell.click()
    time.sleep(0.5)

    time_str = dt.strftime("%H:%M")
    time_item = page.wait_for_selector(
        f'li.react-datepicker__time-list-item:text-is("{time_str}")',
        timeout=5000,
    )
    time_item.scroll_into_view_if_needed()
    time_item.click()
    time.sleep(1)


def _finalize(page: Page):
    final_btn = page.wait_for_selector(
        'button:has-text("予約投稿"), button:has-text("投稿"), button:has-text("公開")',
        timeout=5000,
    )
    final_btn.click()
    time.sleep(5)


def post_spec(page: Page, spec: dict):
    title, body_text, image_path = _load_article(spec)
    print(f"\n=== {spec['id']} {title} ===")

    page.goto("https://note.com/new")
    page.wait_for_load_state("networkidle")
    time.sleep(2)

    _upload_header_image(page, image_path)
    _fill_editor(page, title, body_text)
    _go_publish(page)

    if spec["schedule"]:
        _set_schedule(page, spec["schedule"])
        print(f"  予約設定: {spec['schedule']}")
    else:
        print("  即時投稿")

    _finalize(page)
    print(f"  完了: {page.url}")


def do_login():
    print("ブラウザを起動します。noteにログインしてください。")
    print("ログイン完了後、ブラウザを閉じてください。")
    pw, context, page = _launch_browser(headless=False)
    try:
        page.goto("https://note.com/login")
        _close_browser(pw, context, wait_for_user=True)
    except Exception:
        _close_browser(pw, context, wait_for_user=False)
        raise


def do_post_all():
    pw, context, page = _launch_browser(headless=False)
    try:
        for spec in ARTICLE_SPECS:
            post_spec(page, spec)
    finally:
        _close_browser(pw, context, wait_for_user=False)


def main():
    parser = argparse.ArgumentParser(description="追加note記事の投稿")
    parser.add_argument("--login", action="store_true", help="noteログイン用にブラウザを開く")
    parser.add_argument("--post-all", action="store_true", help="5本を投稿・予約投稿する")
    args = parser.parse_args()

    if args.login:
        do_login()
    elif args.post_all:
        do_post_all()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
