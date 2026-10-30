"""真实运行验证：鼠标快速乱滑后窗口仍在（截图为证）。

用法： .venv\\Scripts\\python.exe tools\\cursorlive.py
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


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long), ("top", ctypes.c_long),
        ("right", ctypes.c_long), ("bottom", ctypes.c_long),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


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
    print("窗口物理范围:", rect.left, rect.top, rect.right, rect.bottom)
    cx = (rect.left + rect.right) // 2
    cy = (rect.top + rect.bottom) // 2

    def shot(name: str) -> None:
        screen.grabWindow(0).save(str(SHOTS / f"{name}.png"))
        print("  saved", name + ".png")

    # 快速乱滑：窗口内外交替，模拟手抖 / 反向滑动
    spots = [
        (cx, cy),
        (rect.right + 80, rect.bottom + 80),
        (rect.left + 40, rect.top + 40),
        (cx, rect.top + 12),
        (rect.left - 100, cy),
        (cx, cy),
        (rect.right + 70, rect.top + 40),
        (cx, cy),
    ]
    for x, y in spots:
        user32.SetCursorPos(x, y)
        time.sleep(0.04)

    # 最后停在窗口中心：窗口应当是可见的
    user32.SetCursorPos(cx, cy)
    time.sleep(0.6)
    shot("cursorlive_inside")

    # 停在顶部：边框栏应当出现
    user32.SetCursorPos(cx, rect.top + 20)
    time.sleep(0.6)
    shot("cursorlive_topbar")

    user32.SetCursorPos(origin.x, origin.y)

    if proc.poll() is None:
        kill_tree(proc.pid)
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
