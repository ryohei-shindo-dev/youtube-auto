"""
note_article_updater.py
note記事の更新を一括で行う汎用スクリプト。
manifest (note_manifest.json) を唯一のIDソースとして使う。

使い方:
    # ヘッダー画像を再生成してアップロード（sheet_no指定）
    python note_article_updater.py --regen-images 23 30 49 50 53

    # タイトル変更（sheet_no → 新タイトル）
    python note_article_updater.py --update-title 23 "新しいタイトル"

    # manifest の内容確認
    python note_article_updater.py --show 23
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import time
from typing import Optional

from dotenv import load_dotenv

SCRIPT_DIR = pathlib.Path(__file__).parent.resolve()
load_dotenv(SCRIPT_DIR / ".env")

MANIFEST_PATH = SCRIPT_DIR / "note_manifest.json"
IMAGES_DIR = SCRIPT_DIR / "note_images"
DEBUG_DIR = SCRIPT_DIR / "debug"
DEBUG_DIR.mkdir(exist_ok=True)


# ========== manifest 操作 ==========

def load_manifest() -> dict[int, dict]:
    """manifest を読み込み、sheet_no をキーにした dict を返す。"""
    rows = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest: dict[int, dict] = {}
    for row in rows:
        sn = int(row["sheet_no"])
        if sn in manifest:
            raise ValueError(f"duplicate sheet_no: {sn}")
        manifest[sn] = row
    return manifest


def get_article(sheet_no: int) -> dict:
    """sheet_no から記事情報を取得する。"""
    manifest = load_manifest()
    if sheet_no not in manifest:
        raise KeyError(f"sheet_no not found: {sheet_no}")
    return manifest[sheet_no]


def save_manifest(manifest: dict[int, dict]):
    """manifest を保存する。"""
    rows = [manifest[sn] for sn in sorted(manifest.keys())]
    MANIFEST_PATH.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ========== 画像再生成 ==========

# sheet_no → 画像テキスト（短い見出し）のマッピング
# generate_note_image() に渡す title / subtitle / bg / layout
IMAGE_TEXT: dict[int, dict] = {
    23: {
        "title": "何もしない日は\n意味がある",
        "subtitle": "",
        "bg": "継続",
        "layout": "left_sub",
    },
    30: {
        "title": "SNSの爆益を\n見た夜に",
        "subtitle": "軸が揺れる理由",
        "bg": "比較",
        "layout": "left_sub",
    },
    49: {
        "title": "何も起きない日\nそれが大切",
        "subtitle": "",
        "bg": "継続",
        "layout": "center",
    },
    50: {
        "title": "引き落とされた\nそれが大切",
        "subtitle": "",
        "bg": "積立",
        "layout": "center",
    },
    53: {
        "title": "気づいたら\n続いていた",
        "subtitle": "長期投資が続く人の共通点",
        "bg": "継続",
        "layout": "left_sub",
    },
}


def regen_images(sheet_nos: list[int]):
    """指定した sheet_no の画像を再生成する。"""
    from note_image_gen import generate_note_image, LAYOUT_LEFT, LAYOUT_LEFT_SUB, LAYOUT_CENTER

    layout_map = {
        "left": LAYOUT_LEFT,
        "left_sub": LAYOUT_LEFT_SUB,
        "center": LAYOUT_CENTER,
    }

    manifest = load_manifest()
    generated = []

    for sn in sheet_nos:
        if sn not in manifest:
            print(f"  #{sn}: manifest に存在しません。スキップ。")
            continue
        if sn not in IMAGE_TEXT:
            print(f"  #{sn}: IMAGE_TEXT に定義がありません。スキップ。")
            continue

        art = manifest[sn]
        spec = IMAGE_TEXT[sn]

        # 出力先: 既存の image_path があればそこに、なければ新規作成
        if art.get("image_path"):
            out_path = SCRIPT_DIR / art["image_path"]
        else:
            out_path = IMAGES_DIR / f"sheet_{sn:03d}.png"

        layout = layout_map.get(spec["layout"], LAYOUT_LEFT_SUB)

        print(f"  #{sn}: {spec['title'].replace(chr(10), ' ')} → {out_path.name}")
        result = generate_note_image(
            title=spec["title"],
            subtitle=spec["subtitle"],
            output_path=out_path,
            bg_keyword=spec["bg"],
            layout=layout,
        )
        if result:
            # manifest を更新
            art["image_path"] = str(out_path.relative_to(SCRIPT_DIR))
            generated.append(sn)

    save_manifest(manifest)
    print(f"\n画像再生成: {len(generated)}/{len(sheet_nos)} 枚完了")
    return generated


# ========== 画像アップロード ==========

def upload_images(sheet_nos: list[int]):
    """指定した sheet_no の画像を note にアップロードする。"""
    from note_publish import _launch_browser, _close_browser
    from playwright.sync_api import Page

    manifest = load_manifest()

    # 対象をフィルタ
    targets = []
    for sn in sheet_nos:
        art = manifest.get(sn)
        if not art:
            print(f"  #{sn}: manifest に存在しません。スキップ。")
            continue
        if not art.get("note_key"):
            print(f"  #{sn}: note_key がありません。スキップ。")
            continue
        if not art.get("image_path"):
            print(f"  #{sn}: image_path がありません。スキップ。")
            continue
        img_path = SCRIPT_DIR / art["image_path"]
        if not img_path.exists():
            print(f"  #{sn}: 画像ファイルが存在しません: {img_path}")
            continue
        targets.append((sn, art, img_path))

    if not targets:
        print("アップロード対象がありません。")
        return

    print(f"\n画像アップロード: {len(targets)}本\n")
    pw, context, page = _launch_browser(headless=False)

    try:
        ok = fail = 0
        for i, (sn, art, img_path) in enumerate(targets):
            print(f"[{i+1}/{len(targets)}] #{sn} {art['sheet_title'][:35]}…")
            result = _upload_one(page, art, img_path)
            if result == "ok":
                ok += 1
            else:
                fail += 1

            if i < len(targets) - 1:
                time.sleep(8)
            if (i + 1) % 3 == 0 and i < len(targets) - 1:
                page.close()
                page = context.new_page()
                time.sleep(2)

        print(f"\n完了: 成功 {ok} / 失敗 {fail}")
        _close_browser(pw, context, wait_for_user=False)
    except Exception:
        _close_browser(pw, context, wait_for_user=False)
        raise


def _dismiss_modal(page):
    """メッセージモーダル（「タイトル、本文を入力してください」等）を閉じる。"""
    for _ in range(3):
        close_btn = page.query_selector(
            '.MessageModal__overlay button:has-text("閉じる")'
        )
        if not close_btn:
            close_btn = page.query_selector(
                '.ReactModal__Overlay button:has-text("閉じる")'
            )
        if close_btn:
            close_btn.click()
            time.sleep(1)
        else:
            break


def _trigger_change_detection(page):
    """本文とタイトルにダミー入力して変更検知を発動させる。"""
    # タイトル
    title_el = page.query_selector('textarea[placeholder="記事タイトル"]')
    if title_el:
        title_el.click()
        time.sleep(0.3)
        page.keyboard.press("End")
        page.keyboard.press(" ")
        page.keyboard.press("Backspace")
        time.sleep(0.5)

    # 本文
    body_el = page.query_selector('div.ProseMirror[role="textbox"]')
    if body_el:
        body_el.click()
        time.sleep(0.3)
        page.keyboard.press("End")
        page.keyboard.press(" ")
        page.keyboard.press("Backspace")
        time.sleep(1)


def _upload_one(page, art: dict, img_path: pathlib.Path) -> str:
    """1記事のヘッダー画像を差し替える。"""
    key = art["note_key"]
    edit_url = f"https://editor.note.com/notes/{key}/edit/"
    page.goto(edit_url)
    page.wait_for_load_state("networkidle")
    time.sleep(3)

    try:
        # 既存画像を削除
        delete_span = page.query_selector('span[aria-label="削除"]')
        if delete_span:
            parent = delete_span.evaluate_handle('el => el.closest("button")')
            parent.as_element().click()
            time.sleep(2)

        # 「画像を追加」
        add_btn = page.wait_for_selector(
            'button[aria-label="画像を追加"]', timeout=5000
        )
        add_btn.click()
        time.sleep(1)

        # 「画像をアップロード」→ ファイル選択
        with page.expect_file_chooser() as fc_info:
            page.wait_for_selector(
                'button:has-text("画像をアップロード")', timeout=5000
            ).click()
        fc_info.value.set_files(str(img_path))
        time.sleep(3)

        # モーダル「保存」
        page.wait_for_selector(
            '.ReactModal__Content button:has-text("保存")', timeout=5000
        ).click()
        time.sleep(5)

        # 画像保存モーダルが閉じるのを待つ
        page.wait_for_selector(
            '.ReactModal__Overlay', state='hidden', timeout=10000
        )
        time.sleep(2)

        # メッセージモーダルが出ていたら閉じる
        _dismiss_modal(page)

        # 本文をクリックしてダミー入力（変更検知を発動させる）
        _trigger_change_detection(page)

        # 一時保存してから publish URL に直接遷移
        save_draft = page.query_selector(
            'button:has-text("一時保存")'
        )
        if save_draft:
            save_draft.click()
            time.sleep(3)

        publish_url = f"https://editor.note.com/notes/{key}/publish/"
        page.goto(publish_url)
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        # 更新ボタン
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
        # デバッグ情報
        ss_path = DEBUG_DIR / f"img_upload_{art['sheet_no']:03d}.png"
        page.screenshot(path=str(ss_path))
        print(f"    スクリーンショット: {ss_path}")
        print(f"    現在のURL: {page.url}")
        buttons = page.evaluate("""
            () => Array.from(document.querySelectorAll('button'))
                .map(b => b.textContent.trim().substring(0, 60))
                .filter(t => t).slice(0, 20)
        """)
        print(f"    ボタン一覧: {buttons}")
        return "fail"


# ========== show ==========

def show_article(sheet_no: int):
    """manifest の内容を表示する。"""
    art = get_article(sheet_no)
    for k, v in art.items():
        print(f"  {k}: {v}")


# ========== main ==========

def main():
    parser = argparse.ArgumentParser(description="note記事更新ツール（manifest基準）")
    parser.add_argument("--regen-images", nargs="+", type=int,
                        metavar="SHEET_NO",
                        help="画像を再生成する sheet_no（複数指定可）")
    parser.add_argument("--upload-images", nargs="+", type=int,
                        metavar="SHEET_NO",
                        help="画像をnoteにアップロードする sheet_no（複数指定可）")
    parser.add_argument("--regen-and-upload", nargs="+", type=int,
                        metavar="SHEET_NO",
                        help="画像再生成 → アップロードを一括実行")
    parser.add_argument("--show", type=int, metavar="SHEET_NO",
                        help="manifest の内容を表示")
    args = parser.parse_args()

    if not any([args.regen_images, args.upload_images,
                args.regen_and_upload, args.show]):
        parser.print_help()
        return

    if args.show:
        show_article(args.show)
        return

    if args.regen_images:
        regen_images(args.regen_images)

    if args.upload_images:
        upload_images(args.upload_images)

    if args.regen_and_upload:
        generated = regen_images(args.regen_and_upload)
        if generated:
            upload_images(generated)


if __name__ == "__main__":
    main()
