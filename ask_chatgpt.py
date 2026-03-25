"""youtube-auto 用 ChatGPT CLI（デフォルトモデル: gpt-5.4）"""
import os
os.environ.setdefault("OPENAI_MODEL", "gpt-5.4")
from ops_shared.chatgpt import main
if __name__ == "__main__":
    main()
