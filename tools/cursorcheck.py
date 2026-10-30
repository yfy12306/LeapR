"""验证鼠标检测的稳定性：快速移动 / 乱滑时窗口不应误消失。

用真实光标位置驱动（_poll_cursor 读的是真实鼠标），所以在进程内直接断言。
用法： .venv\\Scripts\\python.exe tools\\cursorcheck.py
"""

import ctypes
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt                        # noqa: E402
from PySide6.QtGui import QCursor                    # noqa: E402
from PySide6.QtWidgets import QApplication           # noqa: E402

from core.config import load_config                  # noqa: E402
from core.fonts import FontManager                   # noqa: E402
from ui.main_window import ReaderWindow              # noqa: E402

user32 = ctypes.windll.user32
PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(("  [OK]   " if ok else "  [FAIL] ") + name + ("  " + detail if detail else ""))


def pump(app, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


def main() -> int:
    app = QApplication(sys.argv)
    cfg = load_config()
    cfg["idle_opacity"] = 0
    cfg["idle_delay_ms"] = 0
    cfg["window_opacity"] = 100
    cfg["show_titlebar"] = True

    win = ReaderWindow(cfg, FontManager())
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    win.resize(700, 500)
    win.move(120, 120)
    win.show()
    pump(app, 0.5)

    print("窗口逻辑几何:", win.geometry().getRect())
    print("devicePixelRatio:", win.devicePixelRatioF())

    ratio = win.devicePixelRatioF()

    def to_phys(lx: float, ly: float) -> tuple[int, int]:
        return int(round((win.x() + lx) * ratio)), int(round((win.y() + ly) * ratio))

    def opacity() -> float:
        return win.windowOpacity()

    def goto(lx: float, ly: float, wait: float = 0.2) -> None:
        px, py = to_phys(lx, ly)
        user32.SetCursorPos(px, py)
        pump(app, wait)

    # 先确认坐标系对得上：把鼠标放到窗口中心，Qt 读回来的局部坐标应该接近 (350,250)
    px, py = to_phys(350, 250)
    user32.SetCursorPos(px, py)
    pump(app, 0.2)
    local = win.mapFromGlobal(QCursor.pos())
    print("放到物理 (%d,%d) 后 Qt 读到局部坐标 (%d,%d)  [期望接近 (350,250)]"
          % (px, py, local.x(), local.y()))
    check("坐标系换算正确", abs(local.x() - 350) < 6 and abs(local.y() - 250) < 6,
          "(%d,%d)" % (local.x(), local.y()))

    print("\n=== 鼠标在窗口内 ===")
    goto(350, 250, 0.25)
    check("窗口显示", opacity() > 0.9, "opacity=%.2f" % opacity())

    print("\n=== 快速乱滑（模拟手抖 / 反向滑动）===")
    spots = [(40, 40), (660, 460), (350, 250), (15, 480), (685, 15),
             (100, 400), (600, 100), (350, 470), (350, 30), (690, 250)]
    unstable = []
    for lx, ly in spots:
        px, py = to_phys(lx, ly)
        user32.SetCursorPos(px, py)
        pump(app, 0.10)
        if opacity() < 0.9:
            unstable.append((lx, ly, round(opacity(), 2)))
    check("窗口内各点始终显示", not unstable,
          "异常点: %s" % unstable if unstable else "%d 个点全部稳定" % len(spots))

    print("\n=== 停在窗口内 ===")
    goto(350, 250, 0.5)
    check("保持显示", opacity() > 0.9, "opacity=%.2f" % opacity())

    print("\n=== 边框栏区域 ===")
    goto(350, 20, 0.3)
    check("边框栏显示", win._toolbar.isVisible())
    check("窗口仍显示", opacity() > 0.9, "opacity=%.2f" % opacity())

    goto(350, 22, 0.3)
    check("在边框栏上来回微动仍显示", win._toolbar.isVisible() and opacity() > 0.9,
          "toolbar=%s opacity=%.2f" % (win._toolbar.isVisible(), opacity()))

    print("\n=== 移出边框栏、进入正文 ===")
    goto(350, 300, 0.3)
    check("边框栏收起", not win._toolbar.isVisible())
    check("窗口仍显示", opacity() > 0.9, "opacity=%.2f" % opacity())

    print("\n=== 移出窗口 ===")
    goto(1400, 950, 0.3)
    check("窗口瞬间消失", opacity() < 0.1, "opacity=%.2f" % opacity())

    print("\n=== 快速移回 ===")
    goto(350, 250, 0.15)
    check("立刻重新显示", opacity() > 0.9, "opacity=%.2f" % opacity())

    print("\n=== 反复穿越边界（各 6 次）===")
    bad = 0
    for i in range(6):
        if i % 2 == 0:
            goto(350, 250, 0.12)          # 进
            if opacity() < 0.9:
                bad += 1
        else:
            goto(1400, 950, 0.12)         # 出
            if opacity() > 0.1:
                bad += 1
    check("每次进出后状态都判断正确", bad == 0, "异常 %d 次" % bad)

    print("\n" + "=" * 56)
    print("通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
    for name in FAIL:
        print("  -", name)
    print("=" * 56)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
