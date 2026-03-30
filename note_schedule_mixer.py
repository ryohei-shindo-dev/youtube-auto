"""Compatibility wrapper — real code in note/schedule.py"""
from note.schedule import *  # noqa: F401,F403
if __name__ == "__main__":
    from note.schedule import main as _main; _main()
