"""Compatibility wrapper — real code in note/seo.py"""
from note.seo import *  # noqa: F401,F403
if __name__ == "__main__":
    from note.seo import main as _main; _main()
