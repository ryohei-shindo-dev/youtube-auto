"""noteリアクション設定を API 直叩きで一括変更するスクリプト。

UI操作（React hook form）ではstate更新が通らないため、
context.request.post() で API を直接叩く。
Playwright の browser context と Cookie jar を共有するため、
HttpOnly Cookie（_note_session）も含めて認証が通る。

使い方:
    # 1. 現在の設定を確認
    python note_reaction_settings.py --discover

    # 2. dry-run で変更内容を確認
    python note_reaction_settings.py --apply --dry-run

    # 3. 本番実行
    python note_reaction_settings.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from note.browser import _launch_browser, _close_browser

SCRIPT_DIR = Path(__file__).resolve().parent.parent
IMAGE_DIR = SCRIPT_DIR / "note_images" / "reactions"

# ── API エンドポイント ──
API_SAVE = "https://note.com/api/v2/user_appeal_messages/add"
API_IMAGE_UPLOAD = "https://note.com/api/v2/image_upload/reaction_images"
API_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "*/*",
    "Origin": "https://note.com",
}

# ── GraphQL フィールド名 → API kind 値のマッピング ──
GRAPHQL_TO_KIND = {
    "toNoteLike": "like",
    "toCommentLike": "comment_like",
    "toFollow": "follow",
    "toAddToMagazine": "magazine_add",
    "toShare": "share",
}

# ── 種類ごとの設定ページURL ──
SETTINGS_URLS = {
    "like": "https://note.com/settings/reactions/like/note",
    "comment_like": "https://note.com/settings/reactions/like/comment",
    "follow": "https://note.com/settings/reactions/follow",
    "magazine_add": "https://note.com/settings/reactions/magazine_add",
    "share": "https://note.com/settings/reactions/share",
}

# ── 種類ごとの画像ファイル ──
IMAGE_FILES = {
    "like": IMAGE_DIR / "reaction_like.png",
    "comment_like": IMAGE_DIR / "reaction_comment_like.png",
    "follow": IMAGE_DIR / "reaction_follow.png",
    "magazine_add": IMAGE_DIR / "reaction_magazine_add.png",
    "share": IMAGE_DIR / "reaction_share.png",
}

# ── テキスト（各種類×10パターン、35文字以内） ──
MESSAGES: dict[str, list[str]] = {
    "like": [
        "スキ、ありがとうございます",
        "読んでもらえてうれしいです",
        "今日も一緒に、静かにガチホです",
        "揺れた日に読んでもらえて光栄です",
        "そのスキが、かなり励みになります",
        "積み立てみたいに、少しずつ続けます",
        "同じ目線の人がいると心強いです",
        "今日のガチホ、おつかれさまです",
        "静かに受け取ってもらえてうれしいです",
        "含み損の日にも、ありがとうございます",
    ],
    "comment_like": [
        "コメントにスキ、ありがとうございます",
        "その言葉に、こちらが励まされます",
        "反応を残してもらえてうれしいです",
        "同じ悩みの声があると落ち着きます",
        "静かに届いていて、うれしいです",
        "一緒に積み上げていけたらうれしいです",
        "コメントまで読んでくださって感謝です",
        "その一言、ちゃんと受け取りました",
        "同じ目線のやり取りが心地いいです",
        "今日もガチホ仲間がいて心強いです",
    ],
    "follow": [
        "フォローありがとうございます",
        "これから静かに積み上げていきます",
        "揺れた日にも寄れる場所でいたいです",
        "長期投資の気持ちを一緒に整えましょう",
        "受け取ってもらえて、うれしいです",
        "焦る日に戻れる場所になれたらうれしいです",
        "これからも静かな温度で書いていきます",
        "ガチホの途中で思い出してもらえたら",
        "同じ歩幅で続けていけたらうれしいです",
        "フォロー、かなり励みになります",
    ],
    "magazine_add": [
        "マガジン追加、ありがとうございます",
        "まとめて置いてもらえてうれしいです",
        "揺れた日に戻れる棚になりますように",
        "積み上げの途中に置いてもらえて光栄です",
        "必要な日に開いてもらえたらうれしいです",
        "静かな読み物として育てていきます",
        "長期投資の休憩所になれたらうれしいです",
        "その追加が、かなり励みになります",
        "積み立てみたいに、少しずつ増やします",
        "読み返したい場所に入れてもらえて感謝です",
    ],
    "share": [
        "シェアありがとうございます",
        "届けてくださって、うれしいです",
        "揺れている誰かにも届きますように",
        "静かな記事を広げてもらえて感謝です",
        "その共有、とても励みになります",
        "ガチホの途中の誰かに届いたらうれしいです",
        "長期投資の気持ちが少し軽くなりますように",
        "受け渡してもらえて、ありがたいです",
        "同じ悩みの人に届くことを願っています",
        "そのシェアに背中を押されます",
    ],
}


def _fetch_existing_data(page, context, kind: str) -> list[dict]:
    """設定ページにアクセスしてGraphQLから既存データを取得する。"""
    captured = []

    def on_response(response):
        if "graphql" not in response.url:
            return
        try:
            data = response.json()
        except Exception:
            return
        captured.append(data)

    page.on("response", on_response)

    try:
        url = SETTINGS_URLS[kind]
        page.goto(url)
        page.wait_for_load_state("networkidle")
        time.sleep(3)
    finally:
        page.remove_listener("response", on_response)

    # GraphQL レスポンスから既存メッセージを抽出
    existing = []
    for data in captured:
        _extract_messages(data, kind, existing)

    return existing


def _extract_messages(data: dict, kind: str, result: list[dict]):
    """GraphQLレスポンスを再帰的に探索して既存メッセージを抽出する。"""
    if isinstance(data, dict):
        # viewer.reactions 内の該当フィールドを探す
        for gql_field, api_kind in GRAPHQL_TO_KIND.items():
            if api_kind != kind:
                continue
            if gql_field in data:
                node = data[gql_field]
                if isinstance(node, dict) and "messages" in node:
                    for msg in node["messages"]:
                        result.append({
                            "id": msg.get("numberTypeId", 0),
                            "text": msg.get("text", ""),
                            "image": msg.get("image", ""),
                            "image_id": msg.get("imageId"),
                            "preset_reaction_image_key": msg.get("presetReactionImageKey"),
                        })
                    return
        # reactions ノードを探す
        if "reactions" in data:
            _extract_messages(data["reactions"], kind, result)
            return
        if "viewer" in data:
            _extract_messages(data["viewer"], kind, result)
            return
        if "data" in data:
            _extract_messages(data["data"], kind, result)
            return
        for v in data.values():
            if isinstance(v, (dict, list)):
                _extract_messages(v, kind, result)
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, (dict, list)):
                _extract_messages(item, kind, result)


def _upload_image(context, kind: str) -> tuple[str, int]:
    """画像をアップロードしてURL と image_id を返す。"""
    img_path = IMAGE_FILES[kind]
    if not img_path.exists():
        raise FileNotFoundError(f"画像がありません: {img_path}")

    response = context.request.post(
        API_IMAGE_UPLOAD,
        multipart={
            "file": {
                "name": img_path.name,
                "mimeType": "image/png",
                "buffer": img_path.read_bytes(),
            },
        },
        headers={
            **API_HEADERS,
            "Referer": SETTINGS_URLS[kind],
        },
    )

    if response.status != 200:
        raise RuntimeError(f"画像アップロード失敗: {response.status} {response.text()}")

    data = response.json()["data"]
    return data["url"], data["image_id"]


def _build_payload(kind: str, messages: list[str], existing: list[dict],
                   image_id: int) -> dict:
    """保存APIのペイロードを構築する。"""
    # 既存データからid>0のエントリだけ引き継ぐ（id=0は空スロットなので除外）
    valid_existing = [e for e in existing if e.get("id", 0) > 0]

    entries = []
    for i, text in enumerate(messages):
        entry = {
            "kind": kind,
            "image": "",
            "image_id": image_id,
            "text": text,
            "preset_reaction_image_key": None,
        }
        if i < len(valid_existing):
            entry["id"] = valid_existing[i]["id"]
        entries.append(entry)

    return {
        "kind": kind,
        "support_box_appeal_texts": entries,
    }


def _save_reactions(context, kind: str, payload: dict) -> bool:
    """リアクション設定を保存する。"""
    response = context.request.post(
        API_SAVE,
        data=json.dumps(payload),
        headers={
            **API_HEADERS,
            "Content-Type": "application/json",
            "Referer": SETTINGS_URLS[kind],
        },
    )

    if response.status == 200:
        return True

    print(f"    保存失敗: {response.status}")
    try:
        print(f"    レスポンス: {response.text()[:500]}")
    except Exception:
        pass
    return False


# ── コマンド ──

LABELS = {
    "like": "記事にスキ",
    "comment_like": "コメントにスキ",
    "follow": "フォロー",
    "magazine_add": "マガジン追加",
    "share": "シェア",
}


def cmd_discover(page, context):
    """現在の設定を表示する。"""
    print("\n現在のリアクション設定:\n")

    for kind in MESSAGES:
        label = LABELS[kind]
        print(f"── {label}（{kind}）──")

        existing = _fetch_existing_data(page, context, kind)

        if not existing:
            print("  (未設定)")
        else:
            for i, e in enumerate(existing, 1):
                img_mark = "🖼" if e.get("image") or e.get("image_id") else "  "
                print(f"  {i:2d}. {img_mark} 「{e['text']}」 (id={e['id']})")

        print()


def cmd_apply(page, context, dry_run: bool):
    """全種類のリアクション設定を一括変更する。"""
    print("\n設定内容:\n")
    for kind, msgs in MESSAGES.items():
        label = LABELS[kind]
        print(f"── {label}（{kind}）── {len(msgs)}パターン")
        for i, m in enumerate(msgs, 1):
            print(f"  {i:2d}. 「{m}」({len(m)}文字)")
        print()

    # テキスト長チェック
    errors = []
    for kind, msgs in MESSAGES.items():
        for i, m in enumerate(msgs):
            if len(m) > 35:
                errors.append(f"  {LABELS[kind]} #{i+1}: {len(m)}文字 「{m}」")
    if errors:
        print("❌ 35文字超過:")
        for e in errors:
            print(e)
        sys.exit(1)

    if dry_run:
        print("(dry-run: ここで終了)")
        return

    ok, fail = 0, 0

    for kind, msgs in MESSAGES.items():
        label = LABELS[kind]
        print(f"\n[{label}]")

        # 1. 既存データ取得
        print("  既存データ取得中...", end="", flush=True)
        existing = _fetch_existing_data(page, context, kind)
        print(f" {len(existing)}件")

        # 2. 画像アップロード
        print("  画像アップロード中...", end="", flush=True)
        try:
            _, img_id = _upload_image(context, kind)
            print(f" OK (image_id={img_id})")
        except Exception as e:
            print(f" 失敗: {e}")
            fail += 1
            continue

        # 3. ペイロード構築
        payload = _build_payload(kind, msgs, existing, img_id)

        # 4. 保存
        print(f"  保存中（{len(msgs)}パターン）...", end="", flush=True)
        if _save_reactions(context, kind, payload):
            print(" ✅")
            ok += 1
        else:
            print(" ❌")
            fail += 1

        time.sleep(2)

    print(f"\n=== 完了: {ok}成功 / {fail}失敗 ===")


def main():
    parser = argparse.ArgumentParser(description="note リアクション設定（API直叩き）")
    parser.add_argument("--discover", action="store_true",
                        help="現在の設定を表示")
    parser.add_argument("--apply", action="store_true",
                        help="全種類を一括設定")
    parser.add_argument("--dry-run", action="store_true",
                        help="設定内容の確認のみ（実際には保存しない）")
    args = parser.parse_args()

    if not args.discover and not args.apply:
        parser.print_help()
        sys.exit(1)

    pw, context, page = _launch_browser()

    try:
        if args.discover:
            cmd_discover(page, context)
        elif args.apply:
            cmd_apply(page, context, dry_run=args.dry_run)
    finally:
        _close_browser(pw, context, wait_for_user=False)


if __name__ == "__main__":
    main()
