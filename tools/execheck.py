"""验证打包出来的 exe 能正常启动、窗口行为正常。

用法： .venv\\Scripts\\python.exe tools\\execheck.py
"""

import ctypes
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent
EXE = ROOT / "dist" / "LeapR" / "LeapR.exe"
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


def kill_tree(pid: int) -> None:
    """结束整棵进程树。

    PyInstaller 打包的 exe 是「bootloader + 实际应用」两个进程，
    只 terminate 外层的话，真正运行的应用会残留下来，
    还会占着 dist 目录，导致下次打包失败。
    """
    subprocess.run(
        ["taskkill", "/T", "/F", "/PID", str(pid)],
        capture_output=True,
    )


def main() -> int:
    if not EXE.exists():
        print("找不到 exe:", EXE)
        return 1
    SHOTS.mkdir(parents=True, exist_ok=True)

    origin = POINT()
    user32.GetCursorPos(ctypes.byref(origin))

    proc = subprocess.Popen([str(EXE)], cwd=str(EXE.parent))
    print("已启动 exe，pid =", proc.pid)
    time.sleep(10)

    if proc.poll() is not None:
        print("!! exe 已经退出，returncode =", proc.returncode)
        return 1
    print("10 秒后仍存活: True")

    hwnd = user32.FindWindowW(None, WINDOW_TITLE)
    print("窗口句柄:", hwnd)

    app = QApplication.instance() or QApplication(sys.argv)
    screen = QGuiApplication.primaryScreen()

    # 场景 A：鼠标移开 -> 应该完全透明
    scr_w, scr_h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    user32.SetCursorPos(scr_w - 40, scr_h - 40)
    time.sleep(2.0)
    screen.grabWindow(0).save(str(SHOTS / "exe_away.png"))
    print("  saved exe_away.png")

    # 场景 B：鼠标移到窗口顶部 -> 边框栏应出现
    if hwnd:
        rect = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        print("窗口位置:", rect.left, rect.top, rect.right, rect.bottom)
        cx = (rect.left + rect.right) // 2
        user32.SetCursorPos(cx, rect.top + 18)
        time.sleep(1.3)
        screen.grabWindow(0).save(str(SHOTS / "exe_hover_top.png"))
        print("  saved exe_hover_top.png")

    user32.SetCursorPos(origin.x, origin.y)

    kill_tree(proc.pid)
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
