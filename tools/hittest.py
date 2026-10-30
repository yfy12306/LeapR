"""真实窗口的鼠标命中测试。

透明窗口在 Windows 上按像素 alpha 做命中测试：全透明像素会让鼠标穿透到下层窗口，
于是窗口边缘的缩放热区收不到事件 —— 表现就是"拖不动窗口大小"。

这个脚本用 WindowFromPoint 直接探测各位置命中的是不是 LeapR 窗口。

用法： .venv\\Scripts\\python.exe tools\\hittest.py
"""

import ctypes
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WINDOW_TITLE = "LeapR"

user32 = ctypes.windll.user32
GA_ROOT = 2


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long), ("top", ctypes.c_long),
        ("right", ctypes.c_long), ("bottom", ctypes.c_long),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


user32.WindowFromPoint.argtypes = [POINT]
user32.WindowFromPoint.restype = ctypes.c_void_p
user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
user32.GetAncestor.restype = ctypes.c_void_p


def main() -> int:
    proc = subprocess.Popen([sys.executable, str(ROOT / "main.py")], cwd=str(ROOT))
    print("started pid", proc.pid)
    time.sleep(8)

    hwnd = user32.FindWindowW(None, WINDOW_TITLE)
    if not hwnd:
        print("没找到窗口")
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
        return 1

    rect = RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    x0, y0, x1, y1 = rect.left, rect.top, rect.right, rect.bottom
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    print("窗口范围:", x0, y0, x1, y1)

    probes = [
        ("左边缘内侧 4px", x0 + 4, cy),
        ("右边缘内侧 4px", x1 - 4, cy),
        ("上边缘内侧 4px", cx, y0 + 4),
        ("下边缘内侧 4px", cx, y1 - 4),
        ("左上角内侧 4px", x0 + 4, y0 + 4),
        ("右下角内侧 4px", x1 - 4, y1 - 4),
        ("正文区中部", cx, cy),
        ("正文区偏上", x0 + 80, y0 + 120),
    ]

    print()
    print("%-18s %-8s %s" % ("位置", "命中", "细节"))
    print("-" * 62)
    hit_count = 0
    for label, px, py in probes:
        user32.SetCursorPos(px, py)
        time.sleep(0.16)
        under = user32.WindowFromPoint(POINT(px, py))
        root = user32.GetAncestor(under, GA_ROOT) if under else 0
        hit = int(root or 0) == int(hwnd)
        hit_count += hit
        print("%-18s %-8s under=%-10s root=%-10s %s"
              % (label, "是" if hit else "否", under, root,
                 "" if hit else "<-- 穿透到下层了"))

    total = len(probes)
    print("-" * 62)
    print("命中 %d / %d" % (hit_count, total))

    subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    print("done")
    return 0 if hit_count == total else 1


if __name__ == "__main__":
    sys.exit(main())
