"""
note_x_announce.py
note記事のURL記録＋X告知を1コマンドで行うスクリプト。

使い方:
    python note_x_announce.py              # URL入力 → シート記録 → X告知
    python note_x_announce.py --x-only     # 公開日が今日以前＋未告知の記事をX告知
    python note_x_announce.py --x-only --dry-run  # 告知対象を確認（投稿しない）

動作（通常モード）:
    1. note管理シートを読み取り、公開日順で次のURL未記入の記事を特定
    2. note URLの入力を求める
    3. シートのI列にURLを記録
    4. Xに告知ポストを投稿
    5. J列に「X告知済み」と記録

安全策:
    --x-only モードでは公開日（H列）が今日以前の記事のみ告知対象にする。
    予約投稿中（公開日が未来）の記事はスキップし、未公開URLの事故を防ぐ。
"""

from __future__ import annotations

import os
import pathlib
import sys
from datetime import date, datetime
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

_DIR = pathlib.Path(__file__).parent
load_dotenv(_DIR / ".env")

from sheets import get_service, get_cell, NOTE_SHEET_NAME

SHEET_ID = os.environ.get("YOUTUBE_SHEET_ID", "")
STATUS_X_ANNOUNCED = "X告知済み"

# 記事No → X告知テンプレ
X_TEMPLATES: dict[int, dict] = {
    1:  {"line1": "含み損の夜は、何度もアプリを開いてしまう。",
         "line2": "確認回数を減らすだけで、眠れる夜が増えるかもしれません。"},
    2:  {"line1": "積立3年目、なぜかしんどくなる。",
         "line2": "その原因は数字じゃなく「期待とのズレ」かもしれません。"},
    3:  {"line1": "暴落ニュースの夜、口座を開く前に。",
         "line2": "S&P500を15年以上持ち続けた人の過去データを整理しました。"},
    4:  {"line1": "SNSの爆益スクショを見て、焦った夜に。",
         "line2": "比較をやめるための「1つの視点」を書きました。"},
    5:  {"line1": "利確したい。でも複利が止まる。",
         "line2": "その両方が本物の気持ちだという話を書きました。"},
    6:  {"line1": "毎日口座を見てしまう人へ。",
         "line2": "確認するほど不安が増える理由を、行動経済学から整理しました。"},
    7:  {"line1": "積立をやめたくなる瞬間は、誰にでもある。",
         "line2": "やめた人がよく口にする後悔を書きました。"},
    8:  {"line1": "暴落から1年後、売らなかった人はどうなったか。",
         "line2": "リーマン・コロナの底値から1年後の数字を整理しました。"},
    9:  {"line1": "含み損で眠れない夜に思い出したい数字。",
         "line2": "20年間積立を続けた場合の元本割れ確率を書きました。"},
    10: {"line1": "初めての暴落で「売りたい」と思った。",
         "line2": "その気持ちは正常です、という話を書きました。"},
    11: {"line1": "相場が下がると不安になる。",
         "line2": "でもドルコスト平均法では「安く買える期間」でもあります。"},
    12: {"line1": "10年続けても「増えてない」と感じる。",
         "line2": "複利は後半に動く、という話を書きました。"},
    13: {"line1": "退場しない人が特別にやっていることは、たぶん何もない。",
         "line2": "「何もしなかった日」が続けた日としてカウントされています。"},
    14: {"line1": "つい売ってしまった人の多くが、直前にやっていたこと。",
         "line2": "毎日アプリを開いていた、という共通点を整理しました。"},
    15: {"line1": "含み損の夜に読む、バフェットの言葉。",
         "line2": "「潮が引いたとき」の意味を整理しました。"},
    16: {"line1": "新NISAを始めて1年。「やめたい」が頭をよぎる夜に。",
         "line2": "その気持ちの正体を整理しました。"},
    17: {"line1": "含み益があるのに、なぜか不安になる。",
         "line2": "利確したくなる夜に起きていることを書きました。"},
    18: {"line1": "投資を始めるのが遅かった、と感じる夜に。",
         "line2": "「30年」の数字を見ると、少し気持ちが楽になるかもしれません。"},
    19: {"line1": "老後資金が間に合わない気がする夜に。",
         "line2": "「65歳まで」の計算を整理しました。"},
    20: {"line1": "一括投資が怖い。その気持ちは正しい。",
         "line2": "「怖さ」の正体を分解して書きました。"},
    21: {"line1": "積立なのに「今買って大丈夫？」と思う夜がある。",
         "line2": "その不安が来る理由を書きました。"},
    22: {"line1": "「あのとき買っておけば」がつらい夜に。",
         "line2": "後悔を整理するための1つの視点を書きました。"},
    23: {"line1": "円高ショックが怖い夜に。",
         "line2": "20年の数字を見ると、少し落ち着けるかもしれません。"},
    24: {"line1": "一括か積立か、ずっと迷っている。",
         "line2": "迷い続けた時間より大切なことを書きました。"},
    25: {"line1": "現金のまま10年置いた100万円、実質いくら残るか。",
         "line2": "「何もしないリスク」の話を書きました。"},
    26: {"line1": "下がった月に積立を止めたくなる。",
         "line2": "止めると平均取得単価に何が起きるかを整理しました。"},
    27: {"line1": "何もしなかった日が、実は一番大事かもしれない。",
         "line2": "「続けた記録」の話を書きました。"},
}

HASHTAGS = "#長期投資 #積立投資 #ガチホ"


def _build_x_text(article_no: int, note_url: str) -> str:
    """X告知ポストのテキストを組み立てる。"""
    tpl = X_TEMPLATES.get(article_no, {})
    line1 = tpl.get("line1", "")
    line2 = tpl.get("line2", "")
    return f"{line1}\n{line2}\n\n{note_url}\n\n{HASHTAGS}"


def _read_sheet() -> list[list[str]]:
    """note管理シートの全行を取得する。"""
    service = get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range=f"{NOTE_SHEET_NAME}!A1:J50",
    ).execute()
    return result.get("values", [])


_JST = ZoneInfo("Asia/Tokyo")


def _parse_pub_date(pub_date_str: str) -> date | None:
    """シートの公開日文字列を date に変換する。パース失敗は None。

    対応フォーマット: "2026/03/09", "2026-03-09", "2026/3/9" 等
    """
    if not pub_date_str:
        return None
    normalized = pub_date_str.replace("-", "/").strip()
    try:
        parts = normalized.split("/")
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return None


def _is_published_today_or_before(pub_date_str: str) -> bool:
    """公開日が今日（JST）以前（＝既に公開済み）かどうかを判定する。

    公開日が空、またはパースできない場合は False を返す（安全側に倒す）。
    """
    pub = _parse_pub_date(pub_date_str)
    if pub is None:
        return False
    today = datetime.now(_JST).date()
    return pub <= today


def _is_note_url_public(note_url: str) -> bool:
    """note URLに実際にアクセスし、記事が公開済みかどうかを確認する。

    1. HEAD リクエストでステータスコードを確認（軽量）
    2. 200 の場合のみ GET で本文を取得し「予約投稿中」の文字列を検出
    アクセスエラー時は False（安全側に倒す）。
    """
    try:
        head = requests.head(note_url, timeout=10, allow_redirects=True)
        if head.status_code != 200:
            print(f"    [URL確認] ステータス {head.status_code} — 未公開扱い")
            return False
        # 200 でも予約投稿ページの可能性があるため本文を確認
        resp = requests.get(note_url, timeout=15, allow_redirects=True)
        if "予約投稿中の公開前記事です" in resp.text:
            return False
        return True
    except Exception as e:
        print(f"    [URL確認] アクセス失敗: {e} — 未公開扱い")
        return False


def _find_next_unregistered(rows: list[list[str]]) -> dict | None:
    """公開日（H列）順で、URL（I列）が未記入の次の記事を返す。"""
    candidates = []
    for sheet_row, row in enumerate(rows[1:], start=2):
        no_str = get_cell(row, 0)
        no = int(no_str) if no_str.isdigit() else 0
        pub_date = get_cell(row, 7)
        note_url = get_cell(row, 8)
        title = get_cell(row, 5)

        if not note_url and pub_date:
            candidates.append({
                "no": no,
                "title": title,
                "pub_date": pub_date,
                "sheet_row": sheet_row,
            })

    if not candidates:
        return None

    # 公開日順でソート → 一番早い日付の記事
    candidates.sort(key=lambda c: c["pub_date"])
    return candidates[0]


def _update_cells(sheet_row: int, note_url: str | None = None, remark: str | None = None):
    """シートのI列（URL）とJ列（備考）をまとめて更新する。"""
    data = []
    if note_url is not None:
        data.append({
            "range": f"{NOTE_SHEET_NAME}!I{sheet_row}",
            "values": [[note_url]],
        })
    if remark is not None:
        data.append({
            "range": f"{NOTE_SHEET_NAME}!J{sheet_row}",
            "values": [[remark]],
        })
    if not data:
        return
    service = get_service()
    service.spreadsheets().values().batchUpdate(
        spreadsheetId=SHEET_ID,
        body={"valueInputOption": "RAW", "data": data},
    ).execute()


def _post_x(article_no: int, note_url: str) -> str | None:
    """Xに告知ポストを投稿する。"""
    import x_upload
    text = _build_x_text(article_no, note_url)
    print(f"\n--- X告知テキスト ---")
    print(text)
    print("---")
    tweet_id = x_upload.post_tweet(text)
    return tweet_id


def mode_register_and_announce():
    """通常モード: URL入力 → シート記録 → X告知"""
    rows = _read_sheet()
    if len(rows) <= 1:
        print("シートにデータがありません。")
        return

    target = _find_next_unregistered(rows)
    if not target:
        print("URL未記入の記事はありません。全記事登録済みです。")
        return

    no = target["no"]
    title = target["title"]
    pub_date = target["pub_date"]
    sheet_row = target["sheet_row"]

    print(f"\n次の記事: #{no:02d}（公開日: {pub_date}）")
    print(f"タイトル: {title}")
    print()

    note_url = input("note URLを入力 > ").strip()
    if not note_url:
        print("キャンセルしました。")
        return

    if not note_url.startswith("https://"):
        print("URLが正しくないようです。https:// で始まるURLを入力してください。")
        return

    # 1. X告知
    tweet_id = _post_x(no, note_url)

    # 2. シート更新（URL + 告知結果をまとめて書き込み）
    if tweet_id:
        print(f"  X投稿成功: tweet_id={tweet_id}")
        _update_cells(sheet_row, note_url=note_url, remark=STATUS_X_ANNOUNCED)
        print(f"  シート更新: I列にURL、J列に「{STATUS_X_ANNOUNCED}」記録完了")
    else:
        _update_cells(sheet_row, note_url=note_url)
        print(f"  シート更新: I列にURL記録完了")
        print(f"  [エラー] X告知に失敗。シートにはURLのみ記録済みです。")

    print(f"\n記事#{no:02d} 完了！")


def mode_x_only(dry_run: bool = False):
    """X告知のみモード: 5条件すべて満たす記事のみX投稿する。

    対象条件:
        1. H列（公開日）あり
        2. I列（note URL）あり
        3. J列に「X告知済み」なし
        4. 公開日 <= 今日（JST）
        5. note URLへアクセスして公開済み確認
    追加安全策:
        - テンプレ未定義の記事はスキップ（空文面で投稿しない）
    """
    rows = _read_sheet()
    if len(rows) <= 1:
        print("シートにデータがありません。")
        return

    posted_count = 0
    skipped_future = 0
    skipped_not_public = 0
    skipped_no_template = 0
    for sheet_row, row in enumerate(rows[1:], start=2):
        no_str = get_cell(row, 0)
        no = int(no_str) if no_str.isdigit() else 0
        title = get_cell(row, 5)
        pub_date = get_cell(row, 7)
        note_url = get_cell(row, 8)
        remark = get_cell(row, 9)

        # 条件1〜3: URL・告知済みチェック
        if not note_url or STATUS_X_ANNOUNCED in remark:
            continue

        # 条件4: 公開日チェック（date比較、JST）
        if not _is_published_today_or_before(pub_date):
            skipped_future += 1
            print(f"  [スキップ] #{no:02d} 公開日={pub_date or '未設定'} — 公開日が未来")
            continue

        # テンプレ未定義チェック
        if no not in X_TEMPLATES:
            skipped_no_template += 1
            print(f"  [スキップ] #{no:02d} — X告知テンプレートが未定義")
            continue

        # 条件5: note URLへ実アクセスして公開確認
        print(f"  #{no:02d} 公開確認中... {note_url[:50]}")
        if not _is_note_url_public(note_url):
            skipped_not_public += 1
            print(f"  [スキップ] #{no:02d} — noteページがまだ公開されていません")
            continue

        if dry_run:
            text = _build_x_text(no, note_url)
            print(f"\n  [dry-run] #{no:02d}（公開日: {pub_date}）{title[:25]}")
            print(f"  --- X告知テキスト ---")
            print(f"  {text[:80]}...")
            posted_count += 1
            continue

        tweet_id = _post_x(no, note_url)
        if tweet_id:
            print(f"  X投稿成功: tweet_id={tweet_id}")
            new_remark = STATUS_X_ANNOUNCED if not remark else f"{remark} / {STATUS_X_ANNOUNCED}"
            _update_cells(sheet_row, remark=new_remark)
            posted_count += 1
        else:
            print(f"  [エラー] 記事#{no:02d}のX告知に失敗しました。")

    # サマリー
    skipped_total = skipped_future + skipped_not_public + skipped_no_template
    if skipped_total > 0:
        print(f"\n  スキップ: 公開日未来={skipped_future} 未公開={skipped_not_public} テンプレなし={skipped_no_template}")
    if posted_count == 0:
        print("\nX告知する記事はありませんでした。")
    elif dry_run:
        print(f"\n[dry-run] {posted_count}件が告知対象です（実際の投稿はしていません）。")
    else:
        print(f"\n{posted_count}件のX告知を完了しました。")


def main():
    dry_run = "--dry-run" in sys.argv
    if "--x-only" in sys.argv:
        mode_x_only(dry_run=dry_run)
    else:
        mode_register_and_announce()


if __name__ == "__main__":
    main()
