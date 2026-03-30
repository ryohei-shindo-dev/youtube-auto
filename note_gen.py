"""Compatibility wrapper — real code in note/gen.py"""
from note.gen import *  # noqa: F401,F403
if __name__ == "__main__":
    from note.gen import main as _main; _main()
