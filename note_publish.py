"""Compatibility wrapper — real code in note/publish.py"""
from note.publish import *  # noqa: F401,F403
from note.publish import (  # re-export private names used externally
    _launch_browser, _close_browser,
    _markdown_to_note_html, _split_body_for_note,
    _split_body_into_blocks, _insert_body_with_cards,
    _insert_body_blocks, _URL_LINE_RE_PUBLISH,
    _EMBED_SELECTORS, _wait_for_embed_card, _count_embed_cards,
    _repair_single_article,
)
if __name__ == "__main__":
    from note.publish import main as _main; _main()
