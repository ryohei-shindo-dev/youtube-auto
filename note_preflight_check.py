"""note_preflight_check.py — note記事の投稿前バリデーション。

投稿前に記事・画像の問題を検出し、事故を防ぐ。
記事ファイルは一切変更しない（読み取り専用チェック）。

使い方:
    python note_preflight_check.py              # 全記事チェック
    python note_preflight_check.py --add-only    # add系のみ
    python note_preflight_check.py --ugokite     # ugokite系のみ
    python note_preflight_check.py --file note_articles/note_add_01_xxx.md  # 単体
"""
from __future__ import annotations

import pathlib
import re
import sys

# ---------- 定数 ----------
ARTICLES_DIR = pathlib.Path(__file__).parent / "note_articles"
IMAGES_DIR = pathlib.Path(__file__).parent / "note_images"
NOTE_IMAGE_WIDTH = 1280

# 画像テキスト1行の最大文字数（フォント66px、max_width=1040px 基準）
# 全角1文字 ≈ 66px → 1040/66 ≈ 15.7文字。余裕を持って14文字
IMAGE_TEXT_MAX_CHARS = 14


# ---------- チェック関数 ----------

def check_article(md_path: pathlib.Path) -> list[str]:
    """1つの記事ファイルをチェックし、問題のリストを返す。"""
    errors: list[str] = []
    name = md_path.name

    if not md_path.exists():
        return [f"{name}: ファイルが存在しない"]

    text = md_path.read_text(encoding="utf-8")
    lines = text.split("\n")

    # --- 1. タイトル行チェック ---
    if not lines or not lines[0].startswith("# "):
        errors.append(f"{name}: 1行目が # タイトル行ではない")

    # --- 2. **太字** 残留チェック ---
    bold_lines = []
    for i, line in enumerate(lines, 1):
        if "**" in line:
            bold_lines.append(i)
    if bold_lines:
        errors.append(
            f"{name}: ** 太字マーカー残留（{len(bold_lines)}行: "
            f"L{','.join(str(n) for n in bold_lines[:5])}）"
        )

    # --- 3. 生HTMLタグチェック ---
    html_tag_re = re.compile(r"<(p|b|h[1-6]|br|hr|div|span|a |ul|ol|li)[>\s/]", re.IGNORECASE)
    html_lines = []
    for i, line in enumerate(lines, 1):
        if html_tag_re.search(line):
            html_lines.append(i)
    if html_lines:
        errors.append(
            f"{name}: 生HTMLタグ検出（{len(html_lines)}行: "
            f"L{','.join(str(n) for n in html_lines[:5])}）"
        )

    # --- 4. ## 見出しの存在チェック ---
    has_heading = any(line.startswith("## ") for line in lines)
    if not has_heading:
        errors.append(f"{name}: ## 見出しが1つもない（構造が弱い）")

    # --- 5. 本文の最低長チェック ---
    body_text = "\n".join(lines[1:]).strip()
    if len(body_text) < 200:
        errors.append(f"{name}: 本文が短すぎる（{len(body_text)}文字、最低200）")

    # --- 6. 末尾URLのMarkdownリンク残留チェック ---
    md_link_re = re.compile(r"\[.+?\]\(https?://.+?\)")
    for i, line in enumerate(lines, 1):
        if md_link_re.search(line):
            errors.append(f"{name}: Markdownリンク [text](url) 残留（L{i}）— noteではカード変換されない")
            break

    return errors


def check_image_spec(spec: dict) -> list[str]:
    """ARTICLE_SPECS の1エントリの画像関連をチェックする。"""
    errors: list[str] = []
    sid = spec["id"]

    # 画像ファイル存在
    img_path = spec.get("image_path")
    if img_path and not img_path.exists():
        errors.append(f"{sid}: 画像ファイルが存在しない: {img_path}")

    # 画像タイトルの文字数チェック（改行で分割して各行）
    image_title = spec.get("image_title", "")
    if image_title:
        for line in image_title.split("\n"):
            if len(line) > IMAGE_TEXT_MAX_CHARS:
                errors.append(
                    f"{sid}: 画像タイトル行が長すぎる"
                    f"（「{line}」{len(line)}文字、最大{IMAGE_TEXT_MAX_CHARS}）"
                )

    # 画像サブタイトルの文字数チェック
    image_sub = spec.get("image_subtitle", "")
    if image_sub and len(image_sub) > 20:
        errors.append(
            f"{sid}: 画像サブタイトルが長い"
            f"（「{image_sub}」{len(image_sub)}文字、推奨20以下）"
        )

    # 記事ファイル存在
    art_path = spec.get("article_path")
    if art_path and not art_path.exists():
        errors.append(f"{sid}: 記事ファイルが存在しない: {art_path}")

    return errors


def check_all_articles(pattern: str = "note_*.md") -> list[str]:
    """指定パターンの全記事をチェックする。"""
    all_errors: list[str] = []
    files = sorted(ARTICLES_DIR.glob(pattern))
    if not files:
        return [f"記事ファイルが見つからない: {ARTICLES_DIR}/{pattern}"]

    for f in files:
        errors = check_article(f)
        all_errors.extend(errors)

    return all_errors


def check_all_specs() -> list[str]:
    """ARTICLE_SPECS の全エントリの画像をチェックする。"""
    try:
        from note_publish_additional import ARTICLE_SPECS
    except ImportError:
        return ["note_publish_additional.py のインポートに失敗"]

    all_errors: list[str] = []
    for spec in ARTICLE_SPECS:
        errors = check_image_spec(spec)
        all_errors.extend(errors)
    return all_errors


# ---------- メイン ----------

def main():
    args = sys.argv[1:]

    if "--file" in args:
        idx = args.index("--file")
        if idx + 1 < len(args):
            path = pathlib.Path(args[idx + 1])
            errors = check_article(path)
        else:
            print("--file の後にファイルパスを指定してください")
            sys.exit(1)
    elif "--add-only" in args:
        errors = check_all_articles("note_add_*.md")
    elif "--ugokite" in args:
        errors = check_all_articles("note_ugokite_*.md")
    else:
        # 全記事 + 画像スペック
        errors = check_all_articles()
        errors.extend(check_all_specs())

    if errors:
        print(f"\n{'='*60}")
        print(f"  問題検出: {len(errors)}件")
        print(f"{'='*60}\n")
        for e in errors:
            print(f"  ❌ {e}")
        print()
        sys.exit(1)
    else:
        print("\n✅ 問題なし\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
