"""state.jsonに既存公開記事の追加済みカード情報を初期化する（1回だけ実行）。"""
from __future__ import annotations

from pathlib import Path

from note_article_updater import load_manifest, _check_published, NOTE_KEY_RE
from run_note_body_update import save_state

SCRIPT_DIR = Path(__file__).parent.resolve()


def main():
    manifest = load_manifest()

    print("公開状態チェック中...")
    published_sns, published_keys = _check_published(manifest)
    print(f"  公開済み: {len(published_sns)}本")

    cards = {}
    for sn in sorted(published_sns):
        art = manifest[sn]
        md_path = SCRIPT_DIR / art.get("md_path", "")
        try:
            text = md_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        embedded = [
            m.group(1) for m in NOTE_KEY_RE.finditer(text)
            if m.group(1) in published_keys
        ]
        cards[str(sn)] = sorted(set(embedded))

    save_state(published_sns, cards)
    print(f"state.json 初期化完了: {len(cards)}記事分のカード情報を記録")


if __name__ == "__main__":
    main()
