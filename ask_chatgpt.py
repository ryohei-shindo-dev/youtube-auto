"""youtube-auto 用 ChatGPT CLI（デフォルトモデル: gpt-5.5）"""
from __future__ import annotations

if __name__ == "__main__":
    import os
    os.environ.setdefault("OPENAI_MODEL", "gpt-5.5")
    from ops_shared.chatgpt import main
    main()
