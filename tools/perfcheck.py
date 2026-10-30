"""测量滚动过程中的重建行为，定位"卡几秒然后跳"的问题。

用法： .venv\\Scripts\\python.exe tools\\perfcheck.py
"""

import os
import sys
import time

os.environ["LEAPR_PERF"] = "1"          # 必须在导入 ui.main_window 之前

from pathlib import Path                              # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt                         # noqa: E402
from PySide6.QtWidgets import QApplication            # noqa: E402

from core.config import load_config                   # noqa: E402
from core.fonts import FontManager                    # noqa: E402
from ui.main_window import ReaderWindow               # noqa: E402

BOOK = ROOT / "books" / "长夜书店.txt"


def make_long_chapters() -> Path:
    """把现有书按章放大 6 倍，模拟"每章几千字"的真实长篇。

    单章越长，重建一次的成本越高，这个场景更能压出问题。
    """
    out = ROOT / "books" / "长章书.txt"
    if out.exists():
        return out

    from core.reader_engine import ReaderEngine

    text = BOOK.read_text(encoding="utf-8")
    positions = [m.start() for m in ReaderEngine.CHAPTER_PATTERN.finditer(text)]
    parts = []
    for i, start in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(text)
        parts.append(text[start:end] * 6)          # 每章重复 6 遍
    out.write_text("".join(parts), encoding="utf-8")
    print("已生成: %s (%.0f KB)" % (out.name, out.stat().st_size / 1024))
    return out


def wait_loaded(win, path: str, timeout: float = 30.0) -> bool:
    """等加载真正结束。

    不能用 `chapter_count == 0` 判断 —— 换书时上一本还在，计数不是 0。
    用「加载动画是否还在跑」当判据才可靠。
    """
    win.load_file(path)
    waited = 0.0

    while not win._loading_timer.isActive() and waited < 3.0:
        QApplication.processEvents()
        time.sleep(0.01)
        waited += 0.01

    while win._loading_timer.isActive() and waited < timeout:
        QApplication.processEvents()
        time.sleep(0.05)
        waited += 0.05

    for _ in range(20):                 # 留点时间让渲染落地
        QApplication.processEvents()
        time.sleep(0.02)
    return win._reader.chapter_count > 0


def scroll_bench(app, win, label: str, steps: int = 80, step_px: int = 120) -> None:
    print("\n=== %s ===" % label)
    bar = win._browser.verticalScrollBar()
    print("  文档高度 %.0f px，滚动范围 0~%d，视口 %d"
          % (win._browser.document().size().height(), bar.maximum(),
             win._browser.viewport().height()))

    last = (win._window_lo, win._window_hi)
    rebuilds = []
    total = 0.0
    moved = 0
    for i in range(steps):
        bar = win._browser.verticalScrollBar()
        if bar.value() >= bar.maximum() - 2:
            break
        t0 = time.perf_counter()
        bar.setValue(min(bar.maximum(), bar.value() + step_px))
        app.processEvents()
        cost = (time.perf_counter() - t0) * 1000
        total += cost
        moved += 1
        now = (win._window_lo, win._window_hi)
        if now != last:
            rebuilds.append((i, round(cost, 1), now))
            last = now

    print("  滚动 %d 步，累计 %.0f ms（平均 %.1f ms/步）"
          % (moved, total, total / max(1, moved)))
    print("  期间触发重建 %d 次" % len(rebuilds))
    for i, cost, w in rebuilds[:15]:
        print("    第 %-3d 步   %7.1f ms   窗口 -> %s" % (i, cost, w))
    if len(rebuilds) > 15:
        print("    ...(还有 %d 次)" % (len(rebuilds) - 15))


def main() -> int:
    app = QApplication(sys.argv)
    cfg = load_config()
    cfg["window_width"], cfg["window_height"] = 900, 560

    win = ReaderWindow(cfg, FontManager())
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    win.resize(900, 560)
    win.show()
    app.processEvents()

    if not wait_loaded(win, str(BOOK)):
        print("加载失败")
        return 1
    print("章数:", win._reader.chapter_count)

    for preload in (1, 2, 3):
        win._cfg["preload_chapters"] = preload
        win._window_lo = win._window_hi = -1
        win._rebuild_window(0, 0, 0.0)
        app.processEvents()
        scroll_bench(app, win, "预加载 %d 章" % preload)

    # 真实长篇：每章几千字，重建成本高得多
    long_book = make_long_chapters()
    if wait_loaded(win, str(long_book)):
        for preload in (1, 2):
            win._cfg["preload_chapters"] = preload
            win._window_lo = win._window_hi = -1
            win._rebuild_window(0, 0, 0.0)
            app.processEvents()
            scroll_bench(app, win, "长章书 · 预加载 %d 章" % preload)

    print("\ndone")
    return 0


if __name__ == "__main__":
    sys.exit(main())
