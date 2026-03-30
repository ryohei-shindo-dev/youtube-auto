"""Compatibility wrapper — real code in note/reaction.py"""
from note.reaction import *  # noqa: F401,F403
if __name__ == "__main__":
    from note.reaction import main as _main; _main()
