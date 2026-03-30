"""Compatibility wrapper — real code in note/cli.py"""
from note.cli import *  # noqa: F401,F403
if __name__ == "__main__":
    from note.cli import main as _main; _main()
