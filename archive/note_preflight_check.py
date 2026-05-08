"""Compatibility wrapper — real code in note/preflight.py"""
from note.preflight import *  # noqa: F401,F403
if __name__ == "__main__":
    from note.preflight import main as _main; _main()
