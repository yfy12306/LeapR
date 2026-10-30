"""真实屏幕截图：确认章节之间是连续衔接的，而不是翻页跳变。

用法： .venv\\Scripts\\python.exe tools\\scrollshot.py
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

user32 = ctypes.windll.user32
MOUSEEVENTF_WHEEL = 0x0800
WHEEL_DELTA = 120


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long), ("top", ctypes.c_long),
        ("right", ctypes.c_long), ("bottom", ctypes.c_long),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def wheel(down: bool = True, times: int = 20) -> None:
    delta = -WHEEL_DELTA if down else WHEEL_DELTA
    for _ in range(times):
        user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, delta, 0)
        time.sleep(0.02)


def main() -> int:
    SHOTS.mkdir(parents=True, exist_ok=True)
    origin = POINT()
    user32.GetCursorPos(ctypes.byref(origin))

    proc = subprocess.Popen([sys.executable, str(ROOT / "main.py")], cwd=str(ROOT))
    print("started pid", proc.pid)
    time.sleep(8)

    app = QApplication.instance() or QApplication(sys.argv)
    screen = QGuiApplication.primaryScreen()

    hwnd = user32.FindWindowW(None, WINDOW_TITLE)
    if not hwnd:
        print("没找到窗口")
        kill_tree(proc.pid)
        return 1

    rect = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    print("窗口位置:", rect.left, rect.top, rect.right, rect.bottom)
    cx = (rect.left + rect.right) // 2
    cy = (rect.top + rect.bottom) // 2

    def snap(name: str) -> None:
        screen.grabWindow(0).save(str(SHOTS / f"{name}.png"))
        print("  saved", name + ".png")

    # 鼠标移到窗口里：窗口显示出来（否则是全透明的）
    user32.SetCursorPos(cx, cy)
    time.sleep(1.0)
    snap("scroll_1_first_chapter")

    wheel(down=True, times=22)
    time.sleep(1.2)
    snap("scroll_2_mid")

    wheel(down=True, times=22)
    time.sleep(1.2)
    snap("scroll_3_next_chapter")

    user32.SetCursorPos(origin.x, origin.y)

    if proc.poll() is None:
        kill_tree(proc.pid)
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
