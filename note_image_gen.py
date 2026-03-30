"""Compatibility wrapper — real code in note/image_gen.py"""
from note.image_gen import *  # noqa: F401,F403
if __name__ == "__main__":
    from note.image_gen import main as _main; _main()
