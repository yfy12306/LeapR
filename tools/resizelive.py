"""端到端验证：用真实鼠标拖动窗口右下角，确认尺寸真的改变。

用法： .venv\\Scripts\\python.exe tools\\resizelive.py
"""

import ctypes
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "tools" / "shots"
WINDOW_TITLE = "LeapR"

user32 = ctypes.windll.user32
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long), ("top", ctypes.c_long),
        ("right", ctypes.c_long), ("bottom", ctypes.c_long),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def window_rect(hwnd) -> tuple[int, int, int, int]:
    rect = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def main() -> int:
    SHOTS.mkdir(parents=True, exist_ok=True)
    origin = POINT()
    user32.GetCursorPos(ctypes.byref(origin))

    proc = subprocess.Popen([sys.executable, str(ROOT / "main.py")], cwd=str(ROOT))
    print("started pid", proc.pid)
    time.sleep(8)

    hwnd = user32.FindWindowW(None, WINDOW_TITLE)
    if not hwnd:
        print("没找到窗口")
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        return 1

    app = QApplication.instance() or QApplication(sys.argv)
    screen = QGuiApplication.primaryScreen()

    x0, y0, x1, y1 = window_rect(hwnd)
    print("初始窗口:", x0, y0, x1, y1, "-> %dx%d" % (x1 - x0, y1 - y0))

    # 鼠标先进入窗口（不然窗口是全透明的），再挪到右下角内侧
    user32.SetCursorPos((x0 + x1) // 2, (y0 + y1) // 2)
    time.sleep(0.4)
    grab_x, grab_y = x1 - 4, y1 - 4
    user32.SetCursorPos(grab_x, grab_y)
    time.sleep(0.4)
    print("光标移到右下角内侧:", grab_x, grab_y)

    # 按下并拖动
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.2)
    for i in range(1, 9):
        user32.SetCursorPos(grab_x + i * 22, grab_y + i * 16)
        time.sleep(0.06)
    time.sleep(0.3)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.6)

    nx0, ny0, nx1, ny1 = window_rect(hwnd)
    print("拖动后窗口:", nx0, ny0, nx1, ny1, "-> %dx%d" % (nx1 - nx0, ny1 - ny0))

    grew_w = (nx1 - nx0) - (x1 - x0)
    grew_h = (ny1 - ny0) - (y1 - y0)
    print()
    print("宽度变化: %+d px" % grew_w)
    print("高度变化: %+d px" % grew_h)
    ok = grew_w >= 120 and grew_h >= 80
    print("结果:", "通过 —— 拖动右下角可以改变窗口大小" if ok else "失败 —— 窗口尺寸没变")

    screen.grabWindow(0).save(str(SHOTS / "resize_after.png"))
    print("saved resize_after.png")

    user32.SetCursorPos(origin.x, origin.y)
    subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    print("done")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
