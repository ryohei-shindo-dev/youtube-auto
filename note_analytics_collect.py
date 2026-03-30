"""Compatibility wrapper — real code in note/analytics.py"""
from note.analytics import *  # noqa: F401,F403
if __name__ == "__main__":
    from note.analytics import collect, save, print_summary, LOG_PATH
    data = collect(); save(data); print_summary(data)
    print(f"\n✅ {LOG_PATH} に記録しました")
