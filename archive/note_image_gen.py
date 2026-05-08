"""Compatibility wrapper — real code in note/image_gen.py"""
from note.image_gen import *  # noqa: F401,F403
if __name__ == "__main__":
    from note.image_gen import generate_all; generate_all()
