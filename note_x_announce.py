"""Compatibility wrapper — real code in note/x_announce.py"""
from note.x_announce import *  # noqa: F401,F403
if __name__ == "__main__":
    from note.x_announce import main as _main; _main()
