"""真实运行验证：窄窗口下边框栏的「更多」菜单。

用完会还原 config/settings.json。

用法： .venv\\Scripts\\python.exe tools\\morecheck.py
"""

import ctypes
import json
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "tools" / "shots"
CONFIG = ROOT / "config" / "settings.json"
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
    backup = CONFIG.read_text(encoding="utf-8") if CONFIG.exists() else None
    origin = POINT()
    user32.GetCursorPos(ctypes.byref(origin))

    code = 0
    proc = None
    try:
        cfg = json.loads(backup) if backup else {}
        cfg.pop("window_x", None)
        cfg.pop("window_y", None)
        cfg["window_width"] = 430          # 故意设得很窄，触发「更多」
        cfg["window_height"] = 620
        CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

        proc = subprocess.Popen([sys.executable, str(ROOT / "main.py")], cwd=str(ROOT))
        print("started pid", proc.pid)
        time.sleep(8)

        app = QApplication.instance() or QApplication(sys.argv)
        screen = QGuiApplication.primaryScreen()

        hwnd = user32.FindWindowW(None, WINDOW_TITLE)
        if not hwnd:
            print("没找到窗口")
            return 1
        rect = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        print("窗口物理范围:", rect.left, rect.top, rect.right, rect.bottom,
              "-> %dx%d" % (rect.right - rect.left, rect.bottom - rect.top))
        cx = (rect.left + rect.right) // 2

        # 鼠标移到顶部 -> 边框栏出现
        user32.SetCursorPos(cx, rect.top + 16)
        time.sleep(0.8)
        screen.grabWindow(0).save(str(SHOTS / "topbar_narrow.png"))
        print("saved topbar_narrow.png")

        # 鼠标移到窗口中间 -> 边框栏收起，窗口仍显示
        user32.SetCursorPos(cx, (rect.top + rect.bottom) // 2)
        time.sleep(0.6)
        screen.grabWindow(0).save(str(SHOTS / "body_narrow.png"))
        print("saved body_narrow.png")

        user32.SetCursorPos(origin.x, origin.y)
    finally:
        if proc is not None:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                           capture_output=True)
        if backup is not None:
            CONFIG.write_text(backup, encoding="utf-8")
            print("[配置已还原]")

    print("done")
    return code


if __name__ == "__main__":
    sys.exit(main())
