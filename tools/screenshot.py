"""离屏渲染截图，用来检查视觉结果。

用法： .venv\\Scripts\\python.exe tools\\screenshot.py
产物： tools/shots/*.png
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 注意：不要用 offscreen 平台，它没有字体数据库，中文会渲染成方块。
# 改用真实平台 + WA_DontShowOnScreen：布局照常计算，但窗口不出现在屏幕上。

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core.config import load_config  # noqa: E402
from core.fonts import FontManager  # noqa: E402
from ui.main_window import ReaderWindow  # noqa: E402

SHOTS = ROOT / "tools" / "shots"
W, H = 920, 620


def compose(pix: QPixmap, backdrop: str, out: Path) -> None:
    """把带透明通道的窗口截图叠加到一个背景上，方便肉眼查看。"""
    canvas = QPixmap(pix.size())
    canvas.fill(QColor(backdrop))
    painter = QPainter(canvas)
    painter.drawPixmap(0, 0, pix)
    painter.end()
    canvas.save(str(out))
    print("  saved", out.name, f"{pix.width()}x{pix.height()}")


def main() -> int:
    SHOTS.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv)
    cfg = load_config()
    cfg["window_width"], cfg["window_height"] = W, H
    cfg["window_x"] = cfg["window_y"] = 0

    fonts = FontManager()
    win = ReaderWindow(cfg, fonts)
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    win.resize(W, H)
    win.show()
    app.processEvents()

    book = ROOT / "books" / "长夜书店.txt"
    if book.exists():
        win.load_file(str(book))
        app.processEvents()

    # 1) 全透明背景（默认）——模拟贴在浅色桌面上
    cfg["bg_mode"] = "transparent"
    win._apply_config()
    app.processEvents()
    compose(win.grab(), "#eef0f3", SHOTS / "01_透明背景.png")

    # 2) 纯色背景（深色）
    cfg["bg_mode"] = "color"
    cfg["bg_color"] = "#1c1c1e"
    cfg["bg_opacity"] = 88
    cfg["text_color"] = "#f2f2f7"
    win._apply_config()
    app.processEvents()
    compose(win.grab(), "#3a3a3c", SHOTS / "02_纯色背景.png")

    # 3) 目录抽屉
    cfg["bg_color"] = "#ffffff"
    cfg["bg_opacity"] = 96
    cfg["text_color"] = "#1d1d1f"
    win._apply_config()
    win._drawer.open_drawer()
    # 没有跑事件循环时 QPropertyAnimation 不会推进，直接落到终点位置
    from ui.drawer import DRAWER_MARGIN, DRAWER_TOP

    dw, dh = win._drawer._geometry_for(win)
    win._drawer.resize(dw, dh)
    win._drawer.move(DRAWER_MARGIN, DRAWER_TOP)
    win._toolbar.setWindowOpacity(1.0)
    win._toolbar.show()
    win._place_toolbar()
    app.processEvents()
    compose(win.grab(), "#e6e8ec", SHOTS / "03_目录抽屉.png")

    win._drawer.close_drawer()
    win._drawer.hide()
    win._toolbar.hide()
    app.processEvents()

    # 4) 设置面板
    from ui.settings_panel import SettingsPanel

    panel = SettingsPanel(cfg, fonts, win)
    panel.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    panel.show()
    for _ in range(15):          # 等布局稳定，否则控件会被压缩着渲染
        app.processEvents()
    compose(panel.grab(), "#dfe2e7", SHOTS / "04_设置面板.png")
    panel.close()

    print("\n截图完成 ->", SHOTS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
