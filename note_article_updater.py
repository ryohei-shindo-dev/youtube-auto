"""Compatibility wrapper — real code in note/article_updater.py"""
from note.article_updater import *  # noqa: F401,F403
from note.article_updater import (
    load_manifest, _check_published, NOTE_KEY_RE, _append_card_links,
)
if __name__ == "__main__":
    from note.article_updater import main as _main; _main()
