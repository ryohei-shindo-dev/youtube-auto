"""
note_x_announce.py
note記事のURL記録＋X告知を1コマンドで行うスクリプト。

使い方:
    python note_x_announce.py              # URL入力 → シート記録 → X告知
    python note_x_announce.py --x-only     # シートにURLがある未告知分をX告知

動作（通常モード）:
    1. note管理シートを読み取り、公開日順で次のURL未記入の記事を特定
    2. note URLの入力を求める
    3. シートのI列にURLを記録
    4. Xに告知ポストを投稿
    5. J列に「X告知済み」と記録
"""

from __future__ import annotations

import os
import pathlib
import sys

from dotenv import load_dotenv

_DIR = pathlib.Path(__file__).parent
load_dotenv(_DIR / ".env")

from sheets import get_service, NOTE_SHEET_NAME

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
}

HASHTAGS = "#長期投資 #積立投資 #ガチホ"


def _build_x_text(article_no: int, note_url: str) -> str:
    """X告知ポストのテキストを組み立てる。"""
    tpl = X_TEMPLATES.get(article_no, {})
    line1 = tpl.get("line1", "")
    line2 = tpl.get("line2", "")
    return f"{line1}\n{line2}\n\n{note_url}\n\n{HASHTAGS}"


def _get_cell(row: list[str], idx: int) -> str:
    """行データから安全にセルを取得する。"""
    return row[idx] if len(row) > idx else ""


def _read_sheet() -> list[list[str]]:
    """note管理シートの全行を取得する。"""
    service = get_service()
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range=f"{NOTE_SHEET_NAME}!A1:J16",
    ).execute()
    return result.get("values", [])


def _find_next_unregistered(rows: list[list[str]]) -> dict | None:
    """公開日（H列）順で、URL（I列）が未記入の次の記事を返す。"""
    candidates = []
    for sheet_row, row in enumerate(rows[1:], start=2):
        no_str = _get_cell(row, 0)
        no = int(no_str) if no_str.isdigit() else 0
        pub_date = _get_cell(row, 7)
        note_url = _get_cell(row, 8)
        title = _get_cell(row, 5)

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


def mode_x_only():
    """X告知のみモード: URLあり＋未告知の記事をまとめてX投稿"""
    rows = _read_sheet()
    if len(rows) <= 1:
        print("シートにデータがありません。")
        return

    posted_count = 0
    for sheet_row, row in enumerate(rows[1:], start=2):
        no_str = _get_cell(row, 0)
        no = int(no_str) if no_str.isdigit() else 0
        note_url = _get_cell(row, 8)
        remark = _get_cell(row, 9)

        if not note_url or STATUS_X_ANNOUNCED in remark:
            continue

        tweet_id = _post_x(no, note_url)
        if tweet_id:
            print(f"  X投稿成功: tweet_id={tweet_id}")
            new_remark = STATUS_X_ANNOUNCED if not remark else f"{remark} / {STATUS_X_ANNOUNCED}"
            _update_cells(sheet_row, remark=new_remark)
            posted_count += 1
        else:
            print(f"  [エラー] 記事#{no:02d}のX告知に失敗しました。")

    if posted_count == 0:
        print("\nX告知する記事はありませんでした。")
    else:
        print(f"\n{posted_count}件のX告知を完了しました。")


def main():
    if "--x-only" in sys.argv:
        mode_x_only()
    else:
        mode_register_and_announce()


if __name__ == "__main__":
    main()
