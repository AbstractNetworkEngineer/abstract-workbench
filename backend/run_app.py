"""抽象的工作台 — 桌面启动入口（bat / 可执行文件共用）。

默认仅监听 127.0.0.1:18765（冷门端口，避免与常用服务冲突）。
启动后自动打开浏览器；关闭本窗口即退出软件。
"""

import os
import sys
import threading
import webbrowser
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

import uvicorn  # noqa: E402

from main import app  # noqa: E402

HOST = os.environ.get("ABSTRACT_WORKBENCH_HOST", "127.0.0.1")
PORT = int(os.environ.get("ABSTRACT_WORKBENCH_PORT", "18765"))
URL = f"http://{HOST if HOST != '0.0.0.0' else '127.0.0.1'}:{PORT}"


def open_browser():
    webbrowser.open(URL)


def main():
    print("=" * 52)
    print("  抽象的工作台  v0.1.0")
    print(f"  已启动: {URL}  (监听 {HOST})")
    print("  安全: 仅本机访问 + 访问令牌 + 跨域拦截")
    print("  关闭此窗口即退出软件")
    print("=" * 52)
    threading.Timer(1.8, open_browser).start()
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
