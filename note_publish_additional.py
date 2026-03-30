"""Compatibility wrapper — real code in note/publish_additional.py"""
from note.publish_additional import *  # noqa: F401,F403
from note.publish_additional import ARTICLE_SPECS
if __name__ == "__main__":
    from note.publish_additional import main as _main; _main()
