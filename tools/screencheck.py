"""验证多屏 / 屏幕外场景下的窗口归位逻辑。

用完会还原 config/settings.json（窗口关闭时会写配置，不能污染真实设置）。

用法： .venv\\Scripts\\python.exe tools\\screencheck.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt                        # noqa: E402
from PySide6.QtWidgets import QApplication           # noqa: E402

from core.config import load_config                  # noqa: E402
from core.fonts import FontManager                   # noqa: E402
from ui.main_window import ReaderWindow              # noqa: E402

CONFIG = ROOT / "config" / "settings.json"
PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(("  [OK]   " if ok else "  [FAIL] ") + name + ("  " + detail if detail else ""))


def make_window(cfg: dict) -> ReaderWindow:
    win = ReaderWindow(cfg, FontManager())
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    win.show()
    QApplication.processEvents()
    return win


def main() -> int:
    app = QApplication(sys.argv)

    print("=== 当前屏幕 ===")
    for s in app.screens():
        g = s.geometry()
        print("  %-14s %-26s DPR=%-4s 主屏=%s"
              % (s.name(), g.getRect(), s.devicePixelRatio(), s is app.primaryScreen()))

    base = load_config()
    primary = app.primaryScreen().availableGeometry()

    print("\n【1】副屏上的合法位置应当被保留")
    cfg = dict(base)
    cfg.update({"window_x": -700, "window_y": -1000,
                "window_width": 800, "window_height": 500})
    win = make_window(cfg)
    check("停在副屏指定位置", (win.x(), win.y()) == (-700, -1000),
          "实际 (%d,%d)" % (win.x(), win.y()))
    win.close()

    print("\n【2】坐标完全在屏幕外 -> 自动收回（这就是你遇到的问题）")
    cfg = dict(base)
    cfg.update({"window_x": 9999, "window_y": 9999,
                "window_width": 900, "window_height": 600})
    win = make_window(cfg)
    inter = win.geometry().intersected(win._screen_union())
    check("窗口被收回屏幕内", inter.width() > 0 and inter.height() > 0,
          "实际 (%d,%d) %dx%d" % (win.x(), win.y(), win.width(), win.height()))
    check("落在主屏上", primary.intersects(win.geometry()))
    win.close()

    print("\n【3】尺寸超过屏幕 -> 被限制（拖到低 DPI 屏会遇到的暴涨）")
    cfg = dict(base)
    cfg.pop("window_x", None)
    cfg.pop("window_y", None)
    cfg.update({"window_width": 5000, "window_height": 4000})
    win = make_window(cfg)
    largest = win._largest_available()
    check("宽度被限制", win.width() <= largest.width(),
          "%d <= %d" % (win.width(), largest.width()))
    check("高度被限制", win.height() <= largest.height(),
          "%d <= %d" % (win.height(), largest.height()))
    win.close()

    print("\n【4】recenter()：窗口被挪到屏幕外后能归位")
    cfg = dict(base)
    cfg.pop("window_x", None)
    cfg.pop("window_y", None)
    win = make_window(cfg)
    win.move(-9000, -9000)
    QApplication.processEvents()
    check("挪出去后确实在屏幕外",
          win.geometry().intersected(win._screen_union()).width() <= 0)
    win.recenter()
    QApplication.processEvents()
    inter = win.geometry().intersected(win._screen_union())
    check("recenter 后回到屏幕内", inter.width() > 0 and inter.height() > 0,
          "(%d,%d) %dx%d" % (win.x(), win.y(), win.width(), win.height()))
    check("落在主屏上", primary.intersects(win.geometry()))
    win.close()

    print("\n【5】_ensure_visible()：对只露出一条边的窗口也会收回")
    cfg = dict(base)
    cfg.pop("window_x", None)
    cfg.pop("window_y", None)
    win = make_window(cfg)
    virtual = win._screen_union()
    win.move(virtual.right() - 50, virtual.bottom() - 20)
    QApplication.processEvents()
    win._ensure_visible()
    QApplication.processEvents()
    inter = win.geometry().intersected(win._screen_union())
    check("残留可见面积足够", inter.width() >= min(160, win.width())
          and inter.height() >= min(80, win.height()),
          "%dx%d" % (inter.width(), inter.height()))
    win.close()

    print("\n【6】拖动缩放的上限")
    cfg = dict(base)
    cfg.pop("window_x", None)
    cfg.pop("window_y", None)
    win = make_window(cfg)
    from PySide6.QtCore import QPoint
    win._resize_edge = "r"
    win._resize_origin = QPoint(win.x() + win.width(), win.y() + win.height() // 2)
    win._resize_geom = win.geometry()
    win._do_resize(QPoint(win._resize_origin.x() + 99999, win._resize_origin.y()))
    win._resize_edge = ""
    check("拖到天边也不会超过屏幕宽", win.width() <= largest.width(),
          "%d <= %d" % (win.width(), largest.width()))
    win.close()

    print("\n" + "=" * 56)
    print("通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
    for name in FAIL:
        print("  -", name)
    print("=" * 56)
    return 1 if FAIL else 0


if __name__ == "__main__":
    backup = CONFIG.read_text(encoding="utf-8") if CONFIG.exists() else None
    try:
        code = main()
    finally:
        if backup is not None:
            CONFIG.write_text(backup, encoding="utf-8")
            print("[配置已还原]")
    sys.exit(code)
