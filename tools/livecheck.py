"""真实屏幕验证：启动程序 -> 可选操作 -> 截图。

离屏 grab() 对透明窗口的合成不可靠（子控件的 rgba 背景会被算错），
所以检查视觉效果时用这个脚本截真实屏幕。

只依赖 PySide6 与标准库（ctypes 调 user32 发按键，Qt 负责截屏）。

用法：
    .venv\\Scripts\\python.exe tools\\livecheck.py            # 只截正文
    .venv\\Scripts\\python.exe tools\\livecheck.py drawer     # 顺便打开目录抽屉
"""

import ctypes
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parent))
from procutil import kill_tree

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "tools" / "shots"
WINDOW_TITLE = "LeapR"

VK_CONTROL = 0x11
KEYEVENTF_KEYUP = 0x0002


def _send_ctrl(key: str) -> None:
    user32 = ctypes.windll.user32
    user32.keybd_event(VK_CONTROL, 0, 0, 0)
    user32.keybd_event(ord(key.upper()), 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(ord(key.upper()), 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def main() -> int:
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    SHOTS.mkdir(parents=True, exist_ok=True)

    proc = subprocess.Popen([sys.executable, str(ROOT / "main.py")], cwd=str(ROOT))
    print("started pid", proc.pid)
    time.sleep(7)

    if action == "drawer":
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, WINDOW_TITLE)
        print("hwnd:", hwnd)
        if hwnd:
            user32.SetForegroundWindow(hwnd)
            time.sleep(0.5)
            _send_ctrl("J")
            time.sleep(1.6)

    app = QApplication.instance() or QApplication(sys.argv)
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        print("no screen")
        return 1

    pix = screen.grabWindow(0)
    out = SHOTS / f"live_{action or 'main'}.png"
    pix.save(str(out))
    print("saved", out)

    if proc.poll() is None:
        kill_tree(proc.pid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
