"""Compatibility wrapper — real code in note/analytics.py"""
from note.analytics import *  # noqa: F401,F403
if __name__ == "__main__":
    from note.analytics import main as _main; _main()
