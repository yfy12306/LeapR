"""验证鼠标悬停行为，全部基于真实屏幕截图。

要确认的行为：
  1. 鼠标移开窗口 -> 窗口完全透明（截图里看不到任何内容）
  2. 鼠标移入正文区 -> 窗口恢复显示，但边框栏不出现
  3. 鼠标移到窗口顶部 -> 边框栏出现
  4. 再次移开 -> 又完全透明

用法： .venv\\Scripts\\python.exe tools\\hovercheck.py
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
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def snap(app, name: str) -> None:
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return
    out = SHOTS / f"hover_{name}.png"
    screen.grabWindow(0).save(str(out))
    print("  saved", out.name)


def main() -> int:
    SHOTS.mkdir(parents=True, exist_ok=True)

    origin = POINT()
    user32.GetCursorPos(ctypes.byref(origin))

    log_path = SHOTS / "hover_program.log"
    log_file = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "main.py")],
        cwd=str(ROOT),
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    print("started pid", proc.pid, "| 日志 ->", log_path.name)
    time.sleep(8)

    app = QApplication.instance() or QApplication(sys.argv)

    hwnd = user32.FindWindowW(None, WINDOW_TITLE)
    print("hwnd:", hwnd)
    if not hwnd:
        kill_tree(proc.pid)
        return 1

    rect = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    print("窗口位置:", rect.left, rect.top, rect.right, rect.bottom)
    cx = (rect.left + rect.right) // 2
    cy = (rect.top + rect.bottom) // 2

    # 查鼠标底下到底是哪个窗口，确认"鼠标到不了窗口"还是"到了但 Qt 没处理"
    user32.WindowFromPoint.argtypes = [POINT]
    user32.WindowFromPoint.restype = ctypes.c_void_p
    user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    user32.GetAncestor.restype = ctypes.c_void_p

    def probe(tag: str) -> None:
        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        under = user32.WindowFromPoint(pt)
        root = user32.GetAncestor(under, 2) if under else 0   # GA_ROOT
        print(
            f"  [{tag}] 光标=({pt.x},{pt.y}) 命中窗口={under} 顶层={root} "
            f"阅读器={hwnd} 是同一个={root == hwnd}"
        )

    # 屏幕尺寸；"移开"必须真的移到窗口之外，否则触发不了 leaveEvent
    scr_w = user32.GetSystemMetrics(0)
    scr_h = user32.GetSystemMetrics(1)
    away = (scr_w - 40, scr_h - 40)
    print("移开坐标:", away)

    print("场景 1：鼠标移开")
    user32.SetCursorPos(*away)
    time.sleep(2.2)
    probe("1")
    snap(app, "1_moved_away")

    print("场景 2：鼠标移到窗口正文区")
    user32.SetCursorPos(cx, cy)
    time.sleep(1.4)
    probe("2")
    snap(app, "2_hover_body")

    print("场景 3：鼠标移到窗口顶部（边框栏区域）")
    user32.SetCursorPos(cx, rect.top + 18)
    time.sleep(1.2)
    probe("3")
    snap(app, "3_hover_top")

    print("场景 4：再次移开")
    user32.SetCursorPos(*away)
    time.sleep(2.2)
    probe("4")
    snap(app, "4_away_again")

    # 还原鼠标位置
    user32.SetCursorPos(origin.x, origin.y)

    if proc.poll() is None:
        kill_tree(proc.pid)

    log_file.close()
    print("--- 程序日志（尾部） ---")
    print(log_path.read_text(encoding="utf-8", errors="ignore").strip()[-2500:] or "(空)")
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
