"""验证窗口缩放。

- 边缘热区识别（_edge_at）
- 拖动后的尺寸计算（_do_resize）
- 拖动/缩放期间冻结"鼠标移开就淡出"

用法： .venv\\Scripts\\python.exe tools\\resizecheck.py
"""

import ctypes
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, Qt, QTimer            # noqa: E402
from PySide6.QtWidgets import QApplication               # noqa: E402

from core.config import load_config                      # noqa: E402
from core.fonts import FontManager                       # noqa: E402
from ui.main_window import ReaderWindow                  # noqa: E402

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

    win = ReaderWindow(cfg, FontManager())
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    win.resize(700, 500)
    win.move(200, 200)
    win.show()
    pump(app, 0.4)

    w, h = win.width(), win.height()
    print("窗口尺寸:", w, "x", h)
    print("缩放热区宽度 RESIZE_EDGE =", __import__("ui.main_window", fromlist=["x"]).RESIZE_EDGE)

    print("\n=== 边缘热区识别 ===")
    cases = [
        ("左边缘", (3, h // 2), "l"),
        ("右边缘", (w - 3, h // 2), "r"),
        ("上边缘", (w // 2, 3), "t"),
        ("下边缘", (w // 2, h - 3), "b"),
        ("左上角", (3, 3), "tl"),
        ("右下角", (w - 3, h - 3), "br"),
        ("正中央", (w // 2, h // 2), ""),
        ("边缘内 20px", (20, h // 2), ""),
    ]
    for label, (x, y), expect in cases:
        got = win._edge_at(QPoint(x, y))
        check("%s -> %r" % (label, expect), got == expect, "实际 %r" % got)

    print("\n=== 拖动缩放 ===")
    # 右边缘向右拖 120
    before = win.width()
    win._resize_edge = "r"
    win._resize_origin = QPoint(win.x() + win.width(), win.y() + win.height() // 2)
    win._resize_geom = win.geometry()
    win._do_resize(QPoint(win._resize_origin.x() + 120, win._resize_origin.y()))
    win._resize_edge = ""
    check("右边缘右拖 -> 变宽", win.width() >= before + 110,
          "%d -> %d" % (before, win.width()))

    before = win.width()
    win._resize_edge = "r"
    win._resize_origin = QPoint(win.x() + win.width(), win.y() + win.height() // 2)
    win._resize_geom = win.geometry()
    win._do_resize(QPoint(win._resize_origin.x() - 100, win._resize_origin.y()))
    win._resize_edge = ""
    check("右边缘左拖 -> 变窄", win.width() <= before - 90,
          "%d -> %d" % (before, win.width()))

    before = win.height()
    win._resize_edge = "b"
    win._resize_origin = QPoint(win.x() + win.width() // 2, win.y() + win.height())
    win._resize_geom = win.geometry()
    win._do_resize(QPoint(win._resize_origin.x(), win._resize_origin.y() + 100))
    win._resize_edge = ""
    check("下边缘下拖 -> 变高", win.height() >= before + 90,
          "%d -> %d" % (before, win.height()))

    print("\n=== 最小值约束 ===")
    win._resize_edge = "r"
    win._resize_origin = QPoint(win.x() + win.width(), win.y() + win.height() // 2)
    win._resize_geom = win.geometry()
    win._do_resize(QPoint(win._resize_origin.x() - 5000, win._resize_origin.y()))
    win._resize_edge = ""
    check("不会缩到最小宽度以下", win.width() >= win.minimumWidth(),
          "%d (min %d)" % (win.width(), win.minimumWidth()))

    print("\n=== 拖动期间冻结淡出 ===")
    win._begin_interaction()
    check("_interacting 已置位", win._interacting)

    # 把真实鼠标挪到窗口外
    ratio = win.devicePixelRatioF()
    user32.SetCursorPos(int((win.x() + win.width() + 300) * ratio), 1000)
    pump(app, 0.4)
    check("拖动中鼠标在窗口外，窗口仍显示", win.windowOpacity() > 0.9,
          "opacity=%.2f" % win.windowOpacity())

    win._interacting = False
    pump(app, 0.9)      # 轮询间隔 25ms，留足时间让"连续两次出界"判定生效

    class _PT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    _p = _PT()
    user32.GetCursorPos(ctypes.byref(_p))
    print("  [debug] 鼠标物理 (%d,%d)  窗口逻辑 %s  DPR=%.1f  物理约 x%d~%d, y%d~%d"
          % (_p.x, _p.y, win.geometry().getRect(), ratio,
             win.x() * ratio, (win.x() + win.width()) * ratio,
             win.y() * ratio, (win.y() + win.height()) * ratio))
    print("  [debug] _inside=%s _outside_hits=%d _interacting=%s opacity=%.2f"
          % (win._inside, win._outside_hits, win._interacting, win.windowOpacity()))
    check("松手后鼠标在窗口外 -> 恢复正常淡出", win.windowOpacity() < 0.1,
          "opacity=%.2f" % win.windowOpacity())

    print("\n=== 窄窗口下边框栏的收起行为 ===")
    print("（注意：用 isHidden() 判断。边框栏平时整体隐藏，父控件不可见时")
    print("  子控件的 isVisible() 一律为 False，用它判断会得出错误结论）")
    bar = win._toolbar
    vis = lambda b: not b.isHidden()

    win.resize(900, 600)
    app.processEvents()
    bar._fit_buttons()
    print("  [debug] 窗口 %dx%d, 边框栏宽 %d, 需要 %d"
          % (win.width(), win.height(), bar.width(), bar._required_width()))
    check("宽窗口：全部按钮直接可见",
          all(vis(b) for b in bar._buttons.values()) and not vis(bar._more_btn))

    win.resize(520, 600)
    app.processEvents()
    bar._fit_buttons()
    check("中等宽度：出现「更多」按钮", vis(bar._more_btn))
    check("确实有按钮被收起", len(bar._collapsed) > 0, "收起: %s" % bar._collapsed)
    check("核心按钮仍直接可见",
          vis(bar._buttons["目录"]) and vis(bar._buttons["下章"]))
    check("收起的按钮仍记录在案（不是凭空消失）",
          all(n in bar._buttons for n in bar._collapsed)
          and not any(vis(bar._buttons[n]) for n in bar._collapsed))

    win.resize(340, 600)
    app.processEvents()
    bar._fit_buttons()
    check("最窄宽度：核心按钮与「更多」都还在",
          vis(bar._buttons["目录"]) and vis(bar._buttons["下章"]) and vis(bar._more_btn))

    win.resize(900, 600)
    app.processEvents()
    bar._fit_buttons()
    check("拉宽后全部恢复",
          all(vis(b) for b in bar._buttons.values()) and not vis(bar._more_btn))

    print("\n=== 点「更多」时窗口不能被自己藏起来 ===")
    win.resize(430, 620)
    app.processEvents()
    bar._fit_buttons()
    check("确实进入了收起状态", len(bar._collapsed) > 0, str(bar._collapsed))

    state = {}

    def probe():
        # 菜单已经弹出来了：此刻窗口应当处于「冻结」状态
        try:
            popup = QApplication.activePopupWidget()
            state["found"] = popup is not None
            state["interacting"] = win._interacting
            if popup is not None:
                popup.close()
        except Exception as exc:                       # noqa: BLE001
            state["error"] = repr(exc)
        finally:
            if not state.get("found"):
                # 兜底：万一没拿到弹窗，也要让 exec() 结束，否则测试会一直卡住
                for w in app.topLevelWidgets():
                    if w.__class__.__name__ == "QMenu":
                        w.close()

    QTimer.singleShot(400, probe)
    QTimer.singleShot(2500, lambda: [w.close() for w in app.topLevelWidgets()
                                     if w.__class__.__name__ == "QMenu"])
    bar._show_more_menu()          # 会阻塞到菜单关闭

    check("菜单确实弹出过", state.get("found") is True,
          str(state.get("error", "")))
    check("菜单弹出期间窗口被冻结（不会因为鼠标移出去而消失）",
          state.get("interacting") is True, str(state.get("interacting")))
    check("菜单关闭后解除冻结", win._interacting is False)

    print("\n" + "=" * 56)
    print("通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
    for name in FAIL:
        print("  -", name)
    print("=" * 56)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
