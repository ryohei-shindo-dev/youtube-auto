"""
ChatGPTレビュー用プロンプト自動生成スクリプト

使い方:
    python review_gen.py --copy           # テキストレビュー依頼をクリップボードにコピー
    python review_gen.py --count 10 --copy  # 最新10本だけ
    python review_gen.py --video            # 動画レビュー用（動画パス＋プロンプトを表示）
    python review_gen.py --video --count 3  # 最新3本の動画レビュー
    python review_gen.py --read             # シートからレビュー結果を読み取り

テキストレビュー（台本の一括評価）:
    1. python review_gen.py --copy        → クリップボードにコピーされる
    2. ChatGPTに貼り付けて送信            → TSV形式でスコアが返ってくる
    3. ChatGPTの回答のTSV部分をコピー
    4. スプレッドシートのP2セルを選択して貼り付け（1回で完了）
    5. Claude Codeに「レビュー結果読んで」と伝える

動画レビュー（映像・音声・字幕の品質確認）:
    1. python review_gen.py --video       → 動画パスが表示される
    2. 動画ファイルをChatGPTにドラッグ&ドロップ
    3. レビュープロンプトがクリップボードにコピーされるので貼り付けて送信
"""

import argparse
import json
import os
import subprocess
import sys

from dotenv import load_dotenv
import pathlib

load_dotenv(pathlib.Path(__file__).parent / ".env")

DONE_DIR = os.path.join(os.path.dirname(__file__), "done")

REVIEW_PROMPT_HEADER = """以下はYouTube Shorts動画（投資モチベーションチャンネル「ガチホのモチベ」）の台本データです。
{count}本分の台本をまとめてレビューしてください。

チャンネル概要:
- ジャンル: 長期投資モチベーション（煽らない・助言しない・静かに寄り添う）
- ターゲット: 長期投資をしている/始めたばかりの20〜50代
- 構成: hook(痛みワード) → empathy(共感) → data(数字で希望) → resolve(断言) → closing(CTA)
- 目標尺: 17秒前後
- 映像: ダークトーン・シルエット・ミニマル
- AI音声: ElevenLabs speed=1.15

レビュー観点（各10点満点）:
1. hook力: スクロール停止力。痛みワード1語で止められるか
2. 感情曲線: 痛み→共感→希望→断言が自然につながっているか
3. 文脈: dataとresolveの接続詞（でも/だから/そう）が適切か
4. 1メッセージ: 1動画1メッセージになっているか（説明的になっていないか）
5. 総合: 上記を踏まえた総合評価

━━━ 重要: 出力形式 ━━━
レビュー結果はスプレッドシートに貼り付けるため、以下のTSV形式で出力してください。
各行はスプレッドシートの行番号に対応しています。

まず自由形式で分析を書いてから、最後に以下の形式でTSVブロックを出力してください:

```tsv
（行{start_row}〜行{end_row}のデータ。各行: hook力[TAB]感情曲線[TAB]文脈[TAB]1メッセージ[TAB]総合[TAB]コメント）
```

- 各スコアは整数（1〜10）
- コメントは改善点を20文字以内で簡潔に
- 問題なければコメントは「OK」
- 行番号の順序を守ること（シートの行番号と一致させる）
- 未生成（タイトルなし）の行はスキップ

---
"""

REVIEW_PROMPT_VIDEO = """
### シート行{row}: {title}
テーマ: {theme} / 尺: {duration:.1f}秒

| シーン | テキスト | スライド |
|---|---|---|
{scenes_table}
"""


def get_sheet_data():
    """スプレッドシートから生成済み動画のデータを取得する。"""
    sheet_id = os.getenv("YOUTUBE_SHEET_ID", "")
    if not sheet_id:
        return []

    import sheets
    svc = sheets.get_service()
    res = svc.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range="投稿管理!A:P",
    ).execute()
    rows = res.get("values", [])
    if len(rows) <= 1:
        return []

    results = []
    for i, row in enumerate(rows[1:], start=2):
        if len(row) < 8:
            continue
        status = sheets.get_cell(row, 6)
        title = sheets.get_cell(row, 7)
        if status == "生成済み" and title:
            results.append({
                "row": i,
                "type": sheets.get_cell(row, 2),
                "topic": sheets.get_cell(row, 3),
                "title": title,
            })
    return results


def get_transcript_for_title(title):
    """done/フォルダからタイトルに一致するtranscript.jsonを探す。"""
    folders = sorted(
        [d for d in os.listdir(DONE_DIR) if d != "archive_test" and os.path.isdir(os.path.join(DONE_DIR, d))]
    )
    for folder in reversed(folders):
        tj = os.path.join(DONE_DIR, folder, "transcript.json")
        if not os.path.exists(tj):
            continue
        with open(tj, encoding="utf-8") as f:
            data = json.load(f)
        if data.get("title") == title:
            return data
    return None


def format_review_prompt(sheet_items, count=None):
    """レビュー用プロンプトを生成する。"""
    if count:
        sheet_items = sheet_items[-count:]

    start_row = sheet_items[0]["row"] if sheet_items else 2
    end_row = sheet_items[-1]["row"] if sheet_items else 2

    parts = [REVIEW_PROMPT_HEADER.format(
        count=len(sheet_items),
        start_row=start_row,
        end_row=end_row,
    )]

    for item in sheet_items:
        transcript = get_transcript_for_title(item["title"])
        if not transcript:
            parts.append(f"\n### シート行{item['row']}: {item['title']}\n（台本データなし）\n")
            continue

        scenes = transcript.get("scenes", [])
        duration = transcript.get("total_duration_sec", 0)
        theme = transcript.get("theme", item["type"])

        rows = []
        for s in scenes:
            role = s.get("role", "")
            text = s.get("text", "")
            slide = s.get("slide_text", "")
            rows.append(f"| {role} | {text} | {slide} |")

        parts.append(REVIEW_PROMPT_VIDEO.format(
            row=item["row"],
            title=item["title"],
            theme=theme,
            duration=duration,
            scenes_table="\n".join(rows),
        ))

    return "".join(parts)


def copy_to_clipboard(text):
    """macOSのクリップボードにコピー。"""
    try:
        proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        proc.communicate(text.encode("utf-8"))
        return True
    except Exception:
        return False


VIDEO_REVIEW_PROMPT = """この動画はYouTube Shorts（投資モチベーションチャンネル「ガチホのモチベ」）です。

チャンネル概要:
- ジャンル: 長期投資モチベーション（煽らない・助言しない・静かに寄り添う）
- 構成: hook(痛みワード) → empathy(共感) → data(数字で希望) → resolve(断言) → closing(CTA)
- 目標尺: 17秒前後
- 映像: ダークトーン・シルエット・ミニマル
- AI音声: ElevenLabs speed=1.15

以下の観点でレビューしてください（各10点満点）:

1. hook力: 最初の1〜2秒でスクロールを止められるか
2. 音声: AI音声の読み間違い・不自然なイントネーションはないか
3. テンポ: 各シーンの間・速度は適切か（速すぎ/遅すぎ）
4. 字幕: スライド上のテキストは読みやすいか（サイズ・位置・表示時間）
5. 感情曲線: 痛み→共感→希望→断言の流れが映像として成立しているか
6. 総合: Shorts動画としての完成度

出力形式:
| 項目 | スコア | コメント |
で表にしてから、具体的な改善点を箇条書きで出してください。

特に音声の読み間違いがあれば、該当箇所を正確に教えてください。
"""


def get_video_files(count=None):
    """done/フォルダから動画ファイルとメタデータを取得する。"""
    folders = sorted(
        [d for d in os.listdir(DONE_DIR) if d != "archive_test" and os.path.isdir(os.path.join(DONE_DIR, d))]
    )

    videos = []
    for folder in folders:
        mp4 = os.path.join(DONE_DIR, folder, "output.mp4")
        tj = os.path.join(DONE_DIR, folder, "transcript.json")
        if not os.path.exists(mp4):
            continue
        title = ""
        if os.path.exists(tj):
            with open(tj, encoding="utf-8") as f:
                title = json.load(f).get("title", "")
        videos.append({"path": mp4, "title": title, "folder": folder})

    if count:
        videos = videos[-count:]
    return videos


def show_video_review(count=None):
    """動画レビュー用の情報を表示し、プロンプトをクリップボードにコピーする。"""
    videos = get_video_files(count=count)
    if not videos:
        print("レビュー対象の動画がありません。")
        return

    print(f"動画レビュー対象: {len(videos)}本\n")
    print("以下の動画をChatGPTにドラッグ&ドロップしてください:")
    print("-" * 60)
    for i, v in enumerate(videos, 1):
        print(f"  {i}. {v['title']}")
        print(f"     {v['path']}")
        print()

    # Finderで開くか聞く
    if len(videos) == 1:
        # 1本の場合はFinderでファイルを選択状態にする
        subprocess.run(["open", "-R", videos[0]["path"]])
        print("Finderで動画ファイルを開きました。ChatGPTにドラッグしてください。")
    else:
        # 複数の場合はフォルダ一覧を表示
        folders = set(os.path.dirname(v["path"]) for v in videos)
        for folder in folders:
            subprocess.run(["open", folder])
        print("Finderでフォルダを開きました。動画を1本ずつChatGPTにドラッグしてください。")

    # プロンプトをクリップボードにコピー
    if copy_to_clipboard(VIDEO_REVIEW_PROMPT):
        print("\nレビュープロンプトをクリップボードにコピーしました。")
        print("動画をドラッグした後、⌘V で貼り付けて送信してください。")


def read_reviews():
    """スプレッドシートからレビュー結果（M〜R列）を読み取って表示する。"""
    sheet_id = os.getenv("YOUTUBE_SHEET_ID", "")
    if not sheet_id:
        print("YOUTUBE_SHEET_IDが未設定です。")
        return

    import sheets
    svc = sheets.get_service()
    res = svc.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range="投稿管理!A:V",
    ).execute()
    rows = res.get("values", [])
    if len(rows) <= 1:
        print("データがありません。")
        return

    print(f"{'行':>3} | {'タイトル':<30} | hook | 曲線 | 文脈 | 1msg | 総合 | コメント")
    print("-" * 100)

    reviewed = 0
    low_scores = []
    total_score = 0

    for i, row in enumerate(rows[1:], start=2):
        if len(row) < 17:
            continue
        title = sheets.get_cell(row, 7)
        if not title:
            continue

        # Q=16, R=17, S=18, T=19, U=20, V=21
        hook = sheets.get_cell(row, 16)
        curve = sheets.get_cell(row, 17)
        context = sheets.get_cell(row, 18)
        one_msg = sheets.get_cell(row, 19)
        overall = sheets.get_cell(row, 20)
        comment = sheets.get_cell(row, 21)

        if not hook:
            continue

        reviewed += 1
        try:
            score = int(overall)
            total_score += score
            if score <= 6:
                low_scores.append((i, title, score, comment))
        except ValueError:
            pass

        short_title = title[:28] + ".." if len(title) > 30 else title
        print(f"{i:3d} | {short_title:<30} | {hook:>4} | {curve:>4} | {context:>4} | {one_msg:>4} | {overall:>4} | {comment}")

    if reviewed > 0:
        avg = total_score / reviewed
        print(f"\nレビュー済み: {reviewed}本 / 平均スコア: {avg:.1f}/10")
        if low_scores:
            print(f"\n改善が必要な動画（6点以下）:")
            for row, title, score, comment in low_scores:
                print(f"  行{row}: {title}（{score}点）— {comment}")


def main():
    parser = argparse.ArgumentParser(description="ChatGPTレビュー用プロンプト生成")
    parser.add_argument("--count", type=int, default=None, help="レビューする動画数（デフォルト: 全生成済み）")
    parser.add_argument("--all", action="store_true", help="本番動画すべてをレビュー")
    parser.add_argument("--copy", action="store_true", help="クリップボードにコピー")
    parser.add_argument("--save", type=str, default=None, help="ファイルに保存")
    parser.add_argument("--video", action="store_true", help="動画ファイルのレビュー（映像・音声・字幕）")
    parser.add_argument("--read", action="store_true", help="シートからレビュー結果を読み取って表示")
    args = parser.parse_args()

    if args.read:
        read_reviews()
        return

    if args.video:
        show_video_review(count=args.count)
        return

    sheet_items = get_sheet_data()
    if not sheet_items:
        print("レビュー対象の生成済み動画がありません。")
        sys.exit(1)

    if args.count:
        sheet_items = sheet_items[-args.count:]

    prompt = format_review_prompt(sheet_items, count=args.count)

    print(f"レビュー対象: {len(sheet_items)}本")
    for item in sheet_items:
        print(f"  行{item['row']}: {item['title']}")
    print(f"\nプロンプト文字数: {len(prompt)}文字")

    if args.copy:
        if copy_to_clipboard(prompt):
            print("\nクリップボードにコピーしました。ChatGPTに貼り付けてください。")
        else:
            print("\nクリップボードへのコピーに失敗しました。")

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            f.write(prompt)
        print(f"保存しました: {args.save}")

    if not args.copy and not args.save:
        print("\n" + "=" * 60)
        print("以下をChatGPTに貼り付けてください:")
        print("=" * 60 + "\n")
        print(prompt)


if __name__ == "__main__":
    main()
