"""
note_publish.py
Playwrightでnote記事を予約投稿するスクリプト。

使い方:
    # 1. 初回ログイン（ブラウザが開くので手動ログイン → 閉じる）
    python note_publish.py --login

    # 2. セレクタ確認（エディタを開いて一時停止。開発者ツールで確認）
    python note_publish.py --debug

    # 3. 1本だけテスト投稿（下書き保存のみ）
    python note_publish.py --no 16 --draft

    # 4. 全記事を予約投稿（3/21〜3/31）
    python note_publish.py --batch

    # 5. 指定した記事を予約投稿
    python note_publish.py --no 16 --schedule "2026-03-21 21:00"
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys
import time
from datetime import datetime
from html import escape as _html_escape

from playwright.sync_api import sync_playwright, Page, BrowserContext

SCRIPT_DIR = pathlib.Path(__file__).parent
ARTICLES_DIR = SCRIPT_DIR / "note_articles"
IMAGES_DIR = SCRIPT_DIR / "note_images"
USER_DATA_DIR = SCRIPT_DIR / ".note_browser"

# note アカウント情報
NOTE_USER = "gachiho_motive"
NOTE_MAGAZINE = "含み損の夜に読むメモ"

# 固定タグ
NOTE_TAGS = ["長期投資", "積立投資", "資産形成", "投資メンタル", "NISA"]

# 第2弾の投稿スケジュール（No. → 日付）
SCHEDULE = {
    20: "2026-03-21 21:00",
    18: "2026-03-22 21:00",
    23: "2026-03-23 21:00",
    17: "2026-03-24 21:00",
    24: "2026-03-25 21:00",
    19: "2026-03-26 21:00",
    21: "2026-03-27 21:00",
    25: "2026-03-28 21:00",
    22: "2026-03-29 21:00",
    26: "2026-03-30 21:00",
    27: "2026-03-31 21:00",
}

# 記事Noごとの追加タグ（固定タグに加えて使う。未登録はデフォルト空）
EXTRA_TAGS: dict[int, list[str]] = {
    16: ["新NISA"],
    17: ["含み益"],
    19: ["老後資金"],
    20: ["一括投資"],
    22: ["機会損失"],
    23: ["円高"],
    24: ["一括投資"],
    25: ["インフレ"],
}

# 記事No. → ファイル番号のマッピング（第1弾=1-15はシート側、第2弾=16-27）
_ARTICLE_FILE_OFFSET = 15  # note_{no - offset:02d}_*.md


def _find_article(no: int) -> tuple[str, str, pathlib.Path | None]:
    """記事No.に対応するタイトル・本文・画像パスを返す。"""
    # 記事ファイルを探す
    pattern = f"note_{no - _ARTICLE_FILE_OFFSET:02d}_*"
    matches = list(ARTICLES_DIR.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"記事ファイルが見つかりません: {pattern}")

    article_path = matches[0]
    text = article_path.read_text(encoding="utf-8")

    # タイトル抽出（# で始まる行）
    title = ""
    body_lines = []
    for line in text.split("\n"):
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        else:
            body_lines.append(line)

    body = "\n".join(body_lines).strip()

    # 画像ファイル
    image_path = IMAGES_DIR / f"note_{no}.png"
    if not image_path.exists():
        image_path = None

    return title, body, image_path


def _launch_browser(headless: bool = False) -> tuple:
    """永続化されたブラウザコンテキストを起動する。"""
    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        user_data_dir=str(USER_DATA_DIR),
        headless=headless,
        viewport={"width": 1280, "height": 900},
        locale="ja-JP",
    )
    page = context.pages[0] if context.pages else context.new_page()
    return pw, context, page


def _close_browser(pw, context, wait_for_user: bool = True):
    """ブラウザを安全に閉じる。wait_for_user=True ならユーザーが閉じるまで待つ。"""
    if wait_for_user:
        print("\n確認が終わったらブラウザを閉じてください。")
        try:
            context.pages[0].wait_for_event("close", timeout=0)
        except Exception:
            pass
    context.close()
    pw.stop()


def do_login():
    """ブラウザを開いてログインしてもらう。"""
    print("ブラウザを起動します。noteにログインしてください。")
    print("ログイン完了後、ブラウザを閉じてください。")
    pw, context, page = _launch_browser(headless=False)
    try:
        page.goto("https://note.com/login")
        _close_browser(pw, context, wait_for_user=True)
    except Exception:
        _close_browser(pw, context, wait_for_user=False)
        raise
    print("ログイン情報を保存しました。")


def do_debug():
    """エディタを開いて一時停止（セレクタ確認用）。"""
    print("エディタを開きます。開発者ツール（F12）でセレクタを確認してください。")
    print("確認が終わったらブラウザを閉じてください。")
    pw, context, page = _launch_browser(headless=False)
    try:
        page.goto("https://note.com/new")
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        _close_browser(pw, context, wait_for_user=True)
    except Exception:
        _close_browser(pw, context, wait_for_user=False)
        raise


def _markdown_to_note_html(body: str) -> str:
    """Markdown を note エディタの HTML に変換する。

    ## 見出し → <h3>（note のセクション見出し）
    **太字** → <b>
    --- → <hr>（区切り線）
    通常行 → <p>
    空行 → <p><br></p>
    """
    parts: list[str] = []
    for raw_line in body.split("\n"):
        line = raw_line.rstrip()
        # --- → 区切り線
        if re.match(r"^-{3,}$", line.strip()):
            parts.append("<hr>")
            continue
        # ## 見出し → h3
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            heading = re.sub(r"\*\*(.+?)\*\*", r"\1", m.group(1))
            parts.append(f"<h3>{_html_escape(heading)}</h3>")
            continue
        # 空行
        if not line.strip():
            parts.append("<p><br></p>")
            continue
        # 太字 → b タグ、通常行 → p
        escaped = _html_escape(line)
        text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
        parts.append(f"<p>{text}</p>")

    html = "\n".join(parts)
    # 連続する空段落を最大2個に制限
    empty = "<p><br></p>"
    while f"{empty}\n{empty}\n{empty}" in html:
        html = html.replace(f"{empty}\n{empty}\n{empty}", f"{empty}\n{empty}")
    return html.strip()


def post_article(
    page: Page,
    no: int,
    schedule_str: str | None = None,
    draft_only: bool = False,
) -> str | None:
    """1本の記事をnoteに投稿する。

    Returns:
        記事URL（成功時）、None（失敗時）
    """
    title, body, image_path = _find_article(no)
    body_html = _markdown_to_note_html(body)
    tags = NOTE_TAGS + EXTRA_TAGS.get(no, [])

    print(f"\n{'=' * 50}")
    print(f"  #{no} {title[:30]}")
    print(f"  タグ: {', '.join(tags)}")
    if schedule_str:
        print(f"  予約: {schedule_str}")
    print(f"{'=' * 50}")

    # --- エディタを開く ---
    page.goto("https://note.com/new")
    page.wait_for_load_state("networkidle")
    time.sleep(2)

    # --- ヘッダー画像アップロード（タイトル・本文入力前に実行） ---
    if image_path and image_path.exists():
        try:
            img_btn = page.wait_for_selector(
                'button[aria-label="画像を追加"]', timeout=5000
            )
            img_btn.click()
            time.sleep(1)

            with page.expect_file_chooser() as fc_info:
                page.click('button:has-text("画像をアップロード")')
            file_chooser = fc_info.value
            file_chooser.set_files(str(image_path))
            time.sleep(3)

            save_btn = page.wait_for_selector(
                '.ReactModal__Content button:has-text("保存")', timeout=5000
            )
            save_btn.click()
            time.sleep(2)
            print(f"  画像アップロード完了: {image_path.name}")
        except Exception as e:
            print(f"  [警告] 画像アップロード失敗: {e}")

    # --- タイトル入力 ---
    title_sel = 'textarea[placeholder="記事タイトル"]'
    try:
        title_el = page.wait_for_selector(title_sel, timeout=10000)
        title_el.click()
        # type() で1文字ずつ入力（エディタの内部状態を確実に更新）
        page.keyboard.type(title, delay=10)
        time.sleep(0.5)
        print(f"  タイトル入力完了")
    except Exception as e:
        print(f"  [エラー] タイトル入力失敗: {e}")
        print(f"  手動でタイトルを入力してください: {title}")
        page.pause()

    # --- 本文入力 ---
    body_sel = 'div.ProseMirror[role="textbox"]'
    try:
        body_el = page.wait_for_selector(body_sel, timeout=10000)
        body_el.click()
        # insertHTML で ProseMirror に見出し・太字・区切り線を含む HTML を入力
        page.evaluate(
            """html => {
                document.execCommand('insertHTML', false, html);
            }""",
            body_html,
        )
        time.sleep(1)
        print(f"  本文入力完了（HTML）")
    except Exception as e:
        print(f"  [エラー] 本文入力失敗: {e}")
        print("  手動で本文を貼り付けてください。")
        page.pause()

    # --- 公開設定画面へ ---
    try:
        # エディタからフォーカスを外して内部状態を確定させる
        page.keyboard.press("Escape")
        time.sleep(1)

        # noteエディタ右上「公開に進む」ボタン
        publish_nav = page.wait_for_selector(
            'button:has-text("公開に進む")',
            timeout=10000,
        )
        publish_nav.click()
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        print("  公開設定画面へ遷移")
    except Exception as e:
        print(f"  [警告] 公開設定遷移失敗: {e}")
        if draft_only:
            page.pause()
            return None

    # --- タグ設定 ---
    try:
        tag_input = page.wait_for_selector(
            'input[placeholder="ハッシュタグを追加する"]', timeout=5000
        )
        for tag in tags:
            tag_input.fill(tag)
            time.sleep(0.5)
            tag_input.press("Enter")
            time.sleep(0.5)
        print(f"  タグ設定完了（{len(tags)}個）")
    except Exception as e:
        print(f"  [警告] タグ設定失敗: {e}")
        print(f"  手動で設定してください: {', '.join(tags)}")

    # --- マガジン追加 ---
    try:
        magazine_btn = page.wait_for_selector(
            f'button:has-text("追加"):near(:text("{NOTE_MAGAZINE}"))',
            timeout=5000,
        )
        magazine_btn.click()
        time.sleep(1)
        print("  マガジン追加完了")
    except Exception as e:
        print(f"  [警告] マガジン追加失敗: {e}")
        print("  手動で「含み損の夜に読むメモ」に追加してください。")

    # --- 予約投稿設定 ---
    if schedule_str and not draft_only:
        dt = datetime.strptime(schedule_str, "%Y-%m-%d %H:%M")
        try:
            # 「予約投稿」セクションまでスクロールして「日時の設定」をクリック
            schedule_btn = page.wait_for_selector(
                'button:has-text("日時の設定")', timeout=5000
            )
            schedule_btn.scroll_into_view_if_needed()
            schedule_btn.click()
            time.sleep(1)

            # --- カレンダーで日付を選択 ---
            # 日付セルの aria-label で特定（例: "Choose 2026年3月21日金曜日"）
            day = dt.day
            date_cell = page.wait_for_selector(
                f'.react-datepicker__day--0{day:02d}:not(.react-datepicker__day--outside-month)',
                timeout=5000,
            )
            date_cell.click()
            time.sleep(0.5)

            # --- 時刻リストから選択 ---
            time_str = dt.strftime("%H:%M")
            time_item = page.wait_for_selector(
                f'li.react-datepicker__time-list-item:text-is("{time_str}")',
                timeout=5000,
            )
            time_item.scroll_into_view_if_needed()
            time_item.click()
            time.sleep(1)

            print(f"  予約設定完了: {schedule_str}")
        except Exception as e:
            print(f"  [警告] 予約設定失敗: {e}")
            print(f"  手動で予約日時を設定してください: {schedule_str}")

    # --- 下書き / 投稿 ---
    if draft_only:
        print("  下書きモード: タイトル・本文・画像まで入力済みです。")
        print("  公開設定（タグ・予約・マガジン）を確認してから手動で投稿してください。")
        print("  確認が終わったらブラウザを閉じてください。")
        page.pause()
        return None

    # --- 投稿前にエディタURLからnote IDを取得 ---
    # エディタURL例: editor.note.com/notes/n742dabf75dcc/publish/
    editor_url = page.url
    note_id = None
    m = re.search(r"/notes/([a-zA-Z0-9]+)/", editor_url)
    if m:
        note_id = m.group(1)

    # 投稿実行
    try:
        # 右上の投稿ボタン（予約投稿 / 投稿 / 公開）
        final_btn = page.wait_for_selector(
            'button:has-text("予約投稿"), button:has-text("投稿"), '
            'button:has-text("公開")',
            timeout=5000,
        )
        final_btn.click()
        time.sleep(5)
        print("  投稿実行完了")

        # まずリダイレクト先URLを確認
        current_url = page.url
        if "note.com" in current_url and "/n/" in current_url:
            print(f"  URL: {current_url}")
            return current_url

        # リダイレクト先にURLがない場合、エディタURLから組み立てる
        if note_id:
            article_url = f"https://note.com/{NOTE_USER}/n/{note_id}"
            print(f"  URL: {article_url}")
            return article_url

    except Exception as e:
        print(f"  [警告] 投稿実行に失敗: {e}")
        page.pause()

    return None


def do_post_single(no: int, schedule_str: str | None, draft: bool):
    """1本だけ投稿する。"""
    pw, context, page = _launch_browser(headless=False)
    try:
        url = post_article(page, no, schedule_str=schedule_str, draft_only=draft)
        if url:
            _update_sheet(no, url, schedule_str=schedule_str)
    finally:
        _close_browser(pw, context)


def do_batch():
    """スケジュールに従って全記事を投稿する。"""
    pw, context, page = _launch_browser(headless=False)
    results = []

    try:
        for no, schedule_str in SCHEDULE.items():
            try:
                url = post_article(page, no, schedule_str=schedule_str, draft_only=False)
                results.append({"no": no, "url": url, "status": "OK" if url else "要確認"})
                if url:
                    _update_sheet(no, url, schedule_str=schedule_str)
                time.sleep(2)
            except Exception as e:
                print(f"  [エラー] #{no} 投稿失敗: {e}")
                results.append({"no": no, "url": None, "status": f"失敗: {e}"})

        # サマリー
        print(f"\n\n{'#' * 50}")
        print("  投稿結果サマリー")
        print(f"{'#' * 50}")
        for r in results:
            status = r["status"]
            url = r["url"] or "-"
            print(f"  #{r['no']:2d} {status:6s} {url}")

    finally:
        _close_browser(pw, context)


def do_fetch_urls():
    """noteダッシュボードから記事URLを取得し、SCHEDULEのNo.と紐付ける。"""
    # 各記事のタイトルを取得してマッピング用辞書を作る
    title_to_no: dict[str, int] = {}
    all_nos = [16] + list(SCHEDULE.keys())
    for no in all_nos:
        try:
            title, _, _ = _find_article(no)
            title_to_no[title] = no
        except FileNotFoundError:
            pass

    pw, context, page = _launch_browser(headless=False)
    try:
        page.goto("https://note.com/dashboard/contents")
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        # ページのHTML構造をダンプして記事リンクを探す
        articles = page.evaluate("""
        () => {
            const results = [];

            // 方法1: __NEXT_DATA__ からデータ取得
            const nd = document.getElementById('__NEXT_DATA__');
            if (nd) {
                try {
                    const data = JSON.parse(nd.textContent);
                    // pageProps.contentsにnote一覧がある可能性
                    const props = data?.props?.pageProps;
                    if (props) {
                        // contents配列を再帰的に探す
                        const findNotes = (obj, depth) => {
                            if (depth > 5) return;
                            if (Array.isArray(obj)) {
                                for (const item of obj) {
                                    if (item && item.name && item.key) {
                                        results.push({
                                            title: item.name,
                                            key: item.key,
                                            url: 'https://note.com/gachiho_motive/n/' + item.key,
                                        });
                                    }
                                    if (typeof item === 'object') findNotes(item, depth + 1);
                                }
                            } else if (obj && typeof obj === 'object') {
                                for (const v of Object.values(obj)) {
                                    if (typeof v === 'object') findNotes(v, depth + 1);
                                }
                            }
                        };
                        findNotes(props, 0);
                    }
                } catch(e) {}
            }

            // 方法2: DOMからリンク要素を取得
            if (results.length === 0) {
                const links = document.querySelectorAll('a[href*="/n/"], a[href*="/notes/"]');
                for (const a of links) {
                    const href = a.getAttribute('href') || '';
                    const label = a.getAttribute('aria-label') || a.textContent?.trim()?.substring(0, 80) || '';
                    results.push({title: label, url: href, key: '', method: 'dom-link'});
            }

            return results;
        }
        """)

        if not articles:
            # フォールバック: ページ全体のHTMLからnoteキーを正規表現で抽出
            html = page.content()
            keys = re.findall(r'"key":"(n[a-f0-9]{12,})"', html)
            names = re.findall(r'"name":"([^"]{5,80})"', html)
            print(f"  HTMLから抽出: key={len(keys)}件, name={len(names)}件")
            # key と name をペアにする（出現順）
            for i, key in enumerate(keys):
                title = names[i] if i < len(names) else f"(不明 {i})"
                articles.append({
                    "title": title,
                    "key": key,
                    "url": f"https://note.com/{NOTE_USER}/n/{key}",
                })

        print(f"\n取得した記事: {len(articles)}件\n")

        matched = {}
        for art in articles:
            art_title = art.get("title", "")
            art_url = art.get("url", "")
            if not art_url:
                continue
            for known_title, no in title_to_no.items():
                if no in matched:
                    continue
                if known_title[:15] in art_title or art_title[:15] in known_title:
                    matched[no] = art_url
                    print(f"  #{no:2d} {art_url}")
                    break

        unmatched = set(all_nos) - set(matched.keys())
        if unmatched:
            print(f"\n  未マッチ: {sorted(unmatched)}")

        # シートにURL一括記録（ステータスは変えない、URLのみ）
        if matched:
            print(f"\nシートに{len(matched)}件のURLを記録します...")
            try:
                sheet_id, sheets_mod = _get_sheet_env()
                if sheet_id:
                    row_map = _get_note_row_map(sheet_id, sheets_mod)
                    svc = sheets_mod.get_service()
                    for no, url in sorted(matched.items()):
                        target_row = row_map.get(no)
                        if target_row:
                            svc.spreadsheets().values().update(
                                spreadsheetId=sheet_id,
                                range=f"{sheets_mod.NOTE_SHEET_NAME}!I{target_row}",
                                valueInputOption="RAW",
                                body={"values": [[url]]},
                            ).execute()
                            print(f"  #{no:2d} URL記録完了（行{target_row}）")
                        else:
                            print(f"  [警告] #{no} のシート行が見つかりません")
            except Exception as e:
                print(f"  [警告] シート更新失敗: {e}")

        return matched

    finally:
        _close_browser(pw, context, wait_for_user=False)


def _get_sheet_env() -> tuple:
    """シートIDとsheetsモジュールを返す（遅延ロード、1回だけ）。"""
    import os
    from dotenv import load_dotenv
    load_dotenv(SCRIPT_DIR / ".env")
    import sheets
    sheet_id = os.getenv("YOUTUBE_SHEET_ID", "")
    return sheet_id, sheets


def _get_note_row_map(sheet_id, sheets_mod) -> dict[int, int]:
    """note管理シートのA列を読み、{記事No: 行番号} のマップを返す。"""
    svc = sheets_mod.get_service()
    result = svc.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"{sheets_mod.NOTE_SHEET_NAME}!A:A",
    ).execute()
    rows = result.get("values", [])
    return {
        int(row[0]): i + 1
        for i, row in enumerate(rows)
        if row and row[0].isdigit()
    }


def _update_sheet(no: int, url: str, url_only: bool = False, schedule_str: str | None = None):
    """noteシートに記録する。

    url_only=True ならURLのみ（ステータス変更なし）。
    schedule_str が指定されたら H列に予約公開日を記録する（予約投稿の場合）。
    """
    try:
        sheet_id, sheets_mod = _get_sheet_env()
        if not sheet_id:
            return
        row_map = _get_note_row_map(sheet_id, sheets_mod)
        target_row = row_map.get(no)
        if not target_row:
            print(f"  [警告] #{no} のシート行が見つかりません")
            return

        if url_only:
            svc = sheets_mod.get_service()
            svc.spreadsheets().values().update(
                spreadsheetId=sheet_id,
                range=f"{sheets_mod.NOTE_SHEET_NAME}!I{target_row}",
                valueInputOption="RAW",
                body={"values": [[url]]},
            ).execute()
            print(f"  #{no:2d} URL記録完了（行{target_row}）")
        else:
            pub_date = schedule_str.split(" ")[0].replace("-", "/") if schedule_str else None
            sheets_mod.update_note_published(sheet_id, target_row, url, pub_date=pub_date)
            print(f"  シート更新完了（行{target_row}）")
    except Exception as e:
        print(f"  [警告] #{no} シート更新失敗: {e}")


def _get_note_articles_from_sheet() -> list[dict]:
    """note管理シートから記事一覧（No.・タイトル・note ID）を取得する。

    note_image_replace.py の _get_articles_from_sheet() と同じ方式。
    シートの A列=No.、F列=タイトル、I列=URL を読み取る。
    """
    import os
    from dotenv import load_dotenv
    load_dotenv(SCRIPT_DIR / ".env")
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
    for row in rows[1:]:  # ヘッダー行スキップ
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


def _find_article_body_html(no: int, title: str = "") -> str | None:
    """記事No.またはタイトルから本文の HTML を取得する。

    検索順序:
      1. _find_article(no) — No.16+ の第2弾記事（_ARTICLE_FILE_OFFSET使用）
      2. note_{no:02d}_*.md — No.1-15 の第1弾記事
      3. タイトル前方一致 — note_add_* 等の追加記事
    """
    # 1. No. 16+ (second batch)
    try:
        _, body, _ = _find_article(no)
        return _markdown_to_note_html(body)
    except FileNotFoundError:
        pass

    # 2. No. 1-15 (first batch)
    pattern = f"note_{no:02d}_*"
    matches = list(ARTICLES_DIR.glob(pattern))
    if matches:
        return _body_html_from_file(matches[0])

    # 3. Title match against all files
    if title:
        for md_file in sorted(ARTICLES_DIR.glob("*.md")):
            file_title = _extract_title_from_file(md_file)
            if file_title and (file_title[:15] in title or title[:15] in file_title):
                return _body_html_from_file(md_file)

    return None


def _extract_title_from_file(md_file: pathlib.Path) -> str:
    """markdown ファイルの先頭 # 行からタイトルを抽出する。"""
    for line in md_file.read_text(encoding="utf-8").split("\n"):
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _body_html_from_file(md_file: pathlib.Path) -> str:
    """markdown ファイルの本文（タイトル行以降）を HTML に変換する。"""
    text = md_file.read_text(encoding="utf-8")
    body_lines: list[str] = []
    past_title = False
    for line in text.split("\n"):
        if line.startswith("# ") and not past_title:
            past_title = True
        else:
            body_lines.append(line)
    return _markdown_to_note_html("\n".join(body_lines).strip())


def _repair_single_article(page: Page, note_id: str, body_html: str) -> bool:
    """1本の記事の本文フォーマットを修正する。

    エディタを開き → 本文を全選択 → 削除 → HTML で再入力 → 「公開に進む」→「更新する」。
    予約投稿の場合、「更新する」は予約状態を維持する。

    編集URL: note_image_replace.py で検証済みの editor.note.com/notes/{id}/edit/
    保存フロー: MEMORY記載の「公開に進む」→「更新する」（「下書き保存」→「予約投稿」は404の原因）
    """
    # エディタを開く（note_image_replace.py で検証済みの URL パターン）
    edit_url = f"https://editor.note.com/notes/{note_id}/edit/"
    page.goto(edit_url)
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    # 本文エリアをクリック（note_publish.py の post_article で検証済みのセレクタ）
    body_sel = 'div.ProseMirror[role="textbox"]'
    body_el = page.wait_for_selector(body_sel, timeout=10000)
    body_el.click()
    time.sleep(0.5)

    # 全選択 → 削除
    page.keyboard.press("Meta+a")
    time.sleep(0.3)
    page.keyboard.press("Backspace")
    time.sleep(0.5)

    # HTML で再入力（--draft テストで動作確認済み）
    page.evaluate(
        """html => {
            document.execCommand('insertHTML', false, html);
        }""",
        body_html,
    )
    time.sleep(1)

    # 保存: 「公開に進む」→「更新する」
    page.keyboard.press("Escape")
    time.sleep(1)

    publish_nav = page.wait_for_selector(
        'button:has-text("公開に進む")', timeout=10000
    )
    publish_nav.click()
    page.wait_for_load_state("networkidle")
    time.sleep(2)

    update_btn = page.wait_for_selector(
        'button:has-text("更新する")', timeout=10000
    )
    update_btn.click()
    time.sleep(5)

    return True


def do_repair():
    """全記事の本文フォーマットを修正する（■ 見出し → H3 見出し）。

    データソース: Google Sheet の note管理シート（note_image_replace.py と同じ方式）。
    ダッシュボード抽出は使わない（信頼性が低いため）。
    """
    # 1. シートから記事一覧を取得（note_image_replace.py と同じ方式）
    print("note管理シートから記事一覧を取得中...")
    articles = _get_note_articles_from_sheet()
    if not articles:
        print("[エラー] シートから記事URLが取得できませんでした。")
        print("  先に python note_publish.py --urls でURLをシートに記録してください。")
        return

    print(f"  シート上の記事（URL付き）: {len(articles)}本")

    # 2. 各記事の本文HTMLを事前に準備（ブラウザを開く前に全件確認）
    repair_list: list[dict] = []
    for art in articles:
        body_html = _find_article_body_html(art["no"], art["title"])
        if body_html:
            repair_list.append({**art, "body_html": body_html})
        else:
            print(f"  [スキップ] #{art['no']} {art['title'][:30]}: ローカルファイルなし")

    if not repair_list:
        print("[エラー] 修正対象の記事が見つかりませんでした。")
        return

    print(f"  修正対象: {len(repair_list)}本\n")

    # 3. ブラウザを開いて修正
    pw, context, page = _launch_browser(headless=False)
    try:
        repaired = 0
        failed = 0

        for art in repair_list:
            print(f"  修正中: #{art['no']} {art['title'][:35]}...", end="", flush=True)
            try:
                _repair_single_article(page, art["key"], art["body_html"])
                repaired += 1
                print(" 完了")
            except Exception as e:
                failed += 1
                print(f" [エラー] {e}")

            time.sleep(2)

        print(f"\n修正完了: {repaired}本, 失敗: {failed}本")

    finally:
        _close_browser(pw, context, wait_for_user=False)


def do_repair_add():
    """note_add_* 記事の本文フォーマットを修正する（シートにURLがない記事用）。

    ダッシュボードの HTML から note ID を取得し、タイトルで照合して修正する。
    do_fetch_urls() と同じ regex フォールバック方式を使用。
    """
    # 1. note_add ファイルを読み込み（ブラウザを開く前に全件確認）
    add_files = sorted(ARTICLES_DIR.glob("note_add_*.md"))
    if not add_files:
        print("[エラー] note_add_*.md ファイルが見つかりません")
        return

    targets: list[dict] = []
    for md_file in add_files:
        title = _extract_title_from_file(md_file)
        body_html = _body_html_from_file(md_file)
        if title and body_html:
            targets.append({"title": title, "body_html": body_html, "file": md_file.name})

    print(f"修正対象ファイル: {len(targets)}本")
    for t in targets:
        print(f"  {t['file']}: {t['title'][:40]}")

    # 2. ダッシュボードから全記事の key と name を取得
    pw, context, page = _launch_browser(headless=False)
    try:
        page.goto("https://note.com/dashboard/contents")
        page.wait_for_load_state("networkidle")
        time.sleep(5)

        # ページ末尾までスクロールして全記事を表示
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(2)

        # do_fetch_urls() と同じ regex でHTMLから抽出
        html_content = page.content()
        keys = re.findall(r'"key":"(n[a-f0-9]{12,})"', html_content)
        names = re.findall(r'"name":"([^"]{5,80})"', html_content)

        print(f"\nダッシュボードから検出: key={len(keys)}件, name={len(names)}件")

        if not keys:
            print("[エラー] ダッシュボードから記事が検出できませんでした。")
            print("  ブラウザでnoteにログインしているか確認してください。")
            return

        # key と name をペアにする（do_fetch_urls と同じ方式）
        dashboard_articles = []
        for i, key in enumerate(keys):
            name = names[i] if i < len(names) else ""
            dashboard_articles.append({"key": key, "name": name})

        # 3. タイトルマッチング → 修正
        repaired = 0
        not_found = 0

        for target in targets:
            matched_key = None
            for dart in dashboard_articles:
                if target["title"][:15] in dart["name"] or dart["name"][:15] in target["title"]:
                    matched_key = dart["key"]
                    break

            if not matched_key:
                print(f"  [マッチなし] {target['title'][:40]}")
                not_found += 1
                continue

            print(f"  修正中: {target['title'][:40]}...", end="", flush=True)
            try:
                _repair_single_article(page, matched_key, target["body_html"])
                repaired += 1
                print(" 完了")
            except Exception as e:
                not_found += 1
                print(f" [エラー] {e}")

            time.sleep(2)

        print(f"\n修正完了: {repaired}本, 未検出: {not_found}本")

    finally:
        _close_browser(pw, context, wait_for_user=False)


def main():
    parser = argparse.ArgumentParser(description="note記事 自動投稿")
    parser.add_argument("--login", action="store_true", help="ブラウザでログイン")
    parser.add_argument("--debug", action="store_true", help="エディタを開いてセレクタ確認")
    parser.add_argument("--no", type=int, help="投稿する記事No.")
    parser.add_argument("--schedule", type=str, help="予約日時（YYYY-MM-DD HH:MM）")
    parser.add_argument("--draft", action="store_true", help="下書き保存のみ")
    parser.add_argument("--batch", action="store_true", help="全記事をスケジュール通り投稿")
    parser.add_argument("--urls", action="store_true", help="ダッシュボードからURL取得→シート記録")
    parser.add_argument("--repair", action="store_true", help="全記事の見出しフォーマットを修正（■→H3）")
    parser.add_argument("--repair-add", action="store_true", help="note_add_*記事の見出しフォーマットを修正")
    args = parser.parse_args()

    if args.login:
        do_login()
    elif args.debug:
        do_debug()
    elif args.urls:
        do_fetch_urls()
    elif args.repair:
        do_repair()
    elif args.repair_add:
        do_repair_add()
    elif args.batch:
        do_batch()
    elif args.no:
        schedule = args.schedule or SCHEDULE.get(args.no)
        do_post_single(args.no, schedule, args.draft)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
