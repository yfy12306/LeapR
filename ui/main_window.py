"""主窗口：无边框、可全透明的纯文字阅读窗口。

与原始项目的差别：
- 背景改成自绘（transparent / color / image 三模式），窗口本身可以是完全透明的，
  此时屏幕上只剩文字，看不到任何边框和底板
- 去掉了标题栏，操作入口收进一条鼠标靠近才浮现的悬浮工具条
- 目录从弹窗改成左侧滑出抽屉
"""

import math
import os
import sys
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QFontMetricsF,
    QIcon,
    QPainter,
    QPainterPath,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMenu,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from core import config as cfg_mod
from core.bookmark import BookmarkManager
from core.fonts import FontManager
from core.loader import FileLoader
from core.reader_engine import ReaderEngine
from ui import theme
from ui.drawer import ChapterDrawer
from ui.hotkey import HotkeyManager
from ui.settings_panel import SettingsPanel
from ui.topbar import TopBar
from ui.tray import TrayIcon, menu_qss

RESIZE_EDGE = 8          # 边缘缩放热区宽度
TOOLBAR_MARGIN = 10
HOVER_ZONE_HEIGHT = 46   # 鼠标进入窗口顶部这个高度内就唤出边框栏
CURSOR_POLL_MS = 25      # 光标位置轮询间隔（透明窗口收不到 enterEvent，只能自己查）
OUTSIDE_CONFIRM = 2      # 连续多少次采样都在窗口外，才判定"鼠标真的离开了"

# 上下键滚动时，只在这些修饰键按下时才让路（保留系统默认行为）。
# 不能用 ==NoModifier 判断：小键盘方向键会带 KeypadModifier，那样就被漏掉了。
SCROLL_BLOCK_MODS = (
    Qt.KeyboardModifier.ControlModifier
    | Qt.KeyboardModifier.AltModifier
    | Qt.KeyboardModifier.ShiftModifier
    | Qt.KeyboardModifier.MetaModifier
)

# 设 LEAPR_PERF=1 会把各阶段耗时打到 stderr，用来定位卡顿
_PERF = bool(os.environ.get("LEAPR_PERF"))


def _perf(label: str, started: float) -> None:
    if _PERF:
        print("[perf] %-18s %7.1f ms" % (label, (time.perf_counter() - started) * 1000),
              file=sys.stderr, flush=True)


class ReaderWindow(QWidget):
    """阅读窗口本体。"""

    def __init__(self, cfg: dict, font_manager: FontManager):
        super().__init__()
        self._cfg = cfg
        self._fonts = font_manager
        self._bookmarks = BookmarkManager(cfg_mod.CONFIG_DIR)
        self._reader = ReaderEngine(chars_per_page=cfg.get("chars_per_page", 3000))
        self._chapter_index = 0
        self._file_path = ""
        self._visible = True
        self._drag_offset: QPoint | None = None
        self._resize_edge = ""
        self._resize_origin: QPoint | None = None
        self._resize_geom = None
        self._bg_pixmap: QPixmap | None = None
        self._bg_pixmap_path = ""
        self._tray: TrayIcon | None = None
        self._idle = False
        self._inside = False
        self._outside_hits = 0            # 连续多少次采样发现鼠标在窗口外
        self._notified = False

        # 连续阅读：当前渲染窗口覆盖的章节范围，以及每章在文档里的像素范围
        self._window_lo = -1
        self._window_hi = -1
        self._chapter_y: dict[int, tuple[float, float]] = {}
        self._rebuilding = False          # 重渲染中，屏蔽滚动回调，避免递归
        self._suspend_idle = False        # 加载中：不要因为鼠标移开而淡出
        self._interacting = False         # 拖动 / 缩放中：同样冻结淡出
        self._screen_hooked = False       # 是否已挂上 screenChanged
        self._loading_name = ""
        self._loading_tick = 0
        self._loader: FileLoader | None = None

        # 用于 tooltip/选择时保持内容宽度
        self._content_padding = int(cfg.get("page_padding", 30))

        self._setup_window()
        self._build_ui()
        self._setup_timers()
        self._setup_hotkey()
        self._setup_tray()
        self._apply_config()
        self._restore_last()

    # ================================================================== 窗口
    def _force_topmost(self) -> None:
        """用原生 API 把窗口顶到最前。

        实测：`Qt.Tool | WindowStaysOnTopHint` 在 Windows 上压不住企业微信这类窗口，
        窗口会被完全盖住（正文一点都看不见）。所以每次显示后再用 SetWindowPos
        强制设一次 HWND_TOPMOST。
        """
        if sys.platform != "win32":
            return
        try:
            import ctypes

            HWND_TOPMOST = -1
            SWP_NOSIZE = 0x0001
            SWP_NOMOVE = 0x0002
            SWP_NOACTIVATE = 0x0010
            ctypes.windll.user32.SetWindowPos(
                int(self.winId()),
                HWND_TOPMOST,
                0, 0, 0, 0,
                SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE,
            )
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        self._force_topmost()

        handle = self.windowHandle()
        if handle is not None and not self._screen_hooked:
            handle.screenChanged.connect(self._on_screen_changed)
            self._screen_hooked = True

    def _ensure_topmost(self) -> None:
        """发现窗口掉了 topmost 就重新顶上去。

        只在 show() 时设一次不够：别的窗口被激活之后有可能压到上面，
        用户就一点内容都看不到了。鼠标移入时顺手查一下，开销只有一次 API 调用。
        """
        if sys.platform != "win32":
            return
        try:
            import ctypes

            GWL_EXSTYLE = -20
            WS_EX_TOPMOST = 0x00000008
            ex = ctypes.windll.user32.GetWindowLongW(int(self.winId()), GWL_EXSTYLE)
            if not (ex & WS_EX_TOPMOST):
                self._force_topmost()
        except Exception:
            pass

    def _on_screen_changed(self, screen) -> None:
        """窗口被拖到另一块屏幕时调用。

        DPI 不同的屏之间拖动时，Qt 会保持**物理尺寸**不变，逻辑尺寸于是突变
        （1.5x 屏上的 920 宽，拖到 1.0x 屏就变成 1380，看起来"突然变大"）。
        这里把尺寸收回目标屏放得下的范围，再确认窗口没跑丢。
        """
        if screen is not None:
            area = screen.availableGeometry()
            w = max(self.minimumWidth(), min(self.width(), area.width()))
            h = max(self.minimumHeight(), min(self.height(), area.height()))
            if (w, h) != (self.width(), self.height()):
                self.resize(w, h)
        QTimer.singleShot(0, self._ensure_visible)

    def _setup_window(self) -> None:
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if self._cfg.get("always_on_top", True):
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setWindowTitle("LeapR")
        self.setAcceptDrops(True)

        icon_path = cfg_mod.resource_path("assets/app.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        # 边框栏会在窄窗口下自动收起次要按钮，所以最小宽度可以比较小
        self.setMinimumSize(340, 160)
        w, h = self._clamp_size(
            int(self._cfg.get("window_width", 760)),
            int(self._cfg.get("window_height", 480)),
        )
        self.resize(w, h)
        self._place_initially()

    # ================================================================== 屏幕
    def _screen_union(self) -> QRect:
        """所有屏幕几何的并集，也就是虚拟桌面。"""
        rect = QRect()
        for screen in QApplication.screens():
            rect = rect.united(screen.geometry())
        return rect

    def _largest_available(self) -> QRect:
        """面积最大的一块可用屏幕区域。"""
        areas = [s.availableGeometry() for s in QApplication.screens()]
        if not areas:
            return QRect(0, 0, 1280, 800)
        return max(areas, key=lambda r: r.width() * r.height())

    def _clamp_size(self, w: int, h: int) -> tuple[int, int]:
        """把尺寸限制在"单块屏幕放得下"的范围内。

        多屏 + 混合 DPI 时会出问题：窗口从一个屏拖到另一块 DPI 不同的屏，Qt 会
        保持**物理尺寸**不变，于是逻辑尺寸暴涨（1.5x 屏上的 920 宽，到 1.0x 屏
        就变成 1380）。这个值被存下来，下次启动窗口就比屏幕还大。
        """
        area = self._largest_available()
        return (
            max(self.minimumWidth(), min(int(w), area.width())),
            max(self.minimumHeight(), min(int(h), area.height())),
        )

    def _place_initially(self) -> None:
        """决定初始位置。

        校验必须基于**全部屏幕的并集**，不能只看主屏：
        只看主屏的话，停在外接屏上的窗口会被误判成"跑到屏幕外"而强行拉回；
        反过来，外接屏拔掉之后，保存在那块区域的坐标也必须能自动收回。
        """
        virtual = self._screen_union()
        if virtual.isNull():
            return

        x, y = self._cfg.get("window_x"), self._cfg.get("window_y")
        if isinstance(x, int) and isinstance(y, int):
            inter = QRect(x, y, self.width(), self.height()).intersected(virtual)
            if (
                inter.width() >= min(160, self.width())
                and inter.height() >= min(80, self.height())
            ):
                self.move(x, y)
                return

        self.recenter()

    def recenter(self) -> None:
        """把窗口收回主屏，并收成一个放得下的尺寸。

        这也是托盘菜单「窗口归位」的实现 —— 窗口跑到屏幕外时的兜底出口。
        """
        area = self._largest_available()
        w, h = self._clamp_size(self.width(), self.height())
        if (w, h) != (self.width(), self.height()):
            self.resize(w, h)

        screen = QApplication.primaryScreen()
        base = screen.availableGeometry() if screen else area
        self.move(
            base.x() + max(0, (base.width() - w) // 2),
            base.y() + max(0, int(base.height() * 0.12)),
        )
        self._force_topmost()
        self._inside = True
        self._outside_hits = 0
        self._set_active_opacity()

    def _ensure_visible(self) -> None:
        """窗口至少要有足够部分落在某块屏幕上，否则收回来。"""
        if self._screen_union().isNull():
            return
        inter = self.geometry().intersected(self._screen_union())
        if (
            inter.width() < min(160, self.width())
            or inter.height() < min(80, self.height())
        ):
            self.recenter()

    # ================================================================== 构建
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._browser = QTextBrowser()
        self._browser.setFrameShape(QTextBrowser.Shape.NoFrame)
        self._browser.setOpenExternalLinks(False)
        self._browser.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._browser.installEventFilter(self)
        self._browser.viewport().installEventFilter(self)
        self._browser.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._browser.customContextMenuRequested.connect(self._show_menu)
        root.addWidget(self._browser)

        self._drawer = ChapterDrawer(self)
        self._drawer.chapter_selected.connect(self._on_chapter_selected)

        self._toolbar = TopBar(self)
        self._toolbar.installEventFilter(self)
        self._toolbar.drawer_clicked.connect(self._toggle_drawer)
        self._toolbar.prev_clicked.connect(self._prev_chapter)
        self._toolbar.next_clicked.connect(self._next_chapter)
        self._toolbar.open_clicked.connect(self.open_file_dialog)
        self._toolbar.settings_clicked.connect(self._open_settings)
        self._toolbar.hide_clicked.connect(self.toggle_visibility)
        self._toolbar.close_clicked.connect(self._quit)
        self._toolbar.font_smaller.connect(lambda: self._zoom(-1))
        self._toolbar.font_larger.connect(lambda: self._zoom(1))

    def _setup_tray(self) -> None:
        """托盘图标：确认程序在运行、快速显隐、退出入口。"""
        icon_path = cfg_mod.resource_path("assets/app.ico")
        icon = QIcon(str(icon_path)) if icon_path.exists() else self.windowIcon()
        self._tray = TrayIcon(icon, self)
        self._tray.toggle_requested.connect(self.toggle_visibility)
        self._tray.open_requested.connect(self.open_file_dialog)
        self._tray.drawer_requested.connect(self._toggle_drawer)
        self._tray.settings_requested.connect(self._open_settings)
        self._tray.recenter_requested.connect(self.recenter)
        self._tray.recent_requested.connect(self.load_file)
        self._tray.quit_requested.connect(self._quit)
        self._tray.set_recent(self._cfg.get("recent_files", []))

    # ================================================================== 定时器
    def _setup_timers(self) -> None:
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._go_idle)

        # 光标轮询。
        # 窗口用 WA_TranslucentBackground + 全透明背景时，Windows 会把落在透明像素上的
        # 鼠标判给下层窗口，Qt 的 enterEvent / leaveEvent 基本不会触发；
        # 所以这里按屏幕坐标自己判断"鼠标在不在窗口里"，可靠得多。
        # 间隔取得很小，让显示/隐藏跟得上手速。
        self._cursor_timer = QTimer(self)
        self._cursor_timer.timeout.connect(self._poll_cursor)
        self._cursor_timer.start(CURSOR_POLL_MS)

        # "正在打开…"的点点动画
        self._loading_timer = QTimer(self)
        self._loading_timer.timeout.connect(self._on_loading_tick)

        self._save_timer = QTimer(self)
        self._save_timer.timeout.connect(self._auto_save)
        self._save_timer.start(max(1000, int(self._cfg.get("auto_save_interval", 3000))))

        # 滚动驱动"连续阅读"的窗口滑动
        self._browser.verticalScrollBar().valueChanged.connect(self._on_scroll)

    def _setup_hotkey(self) -> None:
        self._hotkey = HotkeyManager(self._cfg.get("hotkey", "ctrl+shift+x"), self)
        self._hotkey.triggered.connect(self.toggle_visibility)
        self._hotkey.start()

    # ================================================================== 配置
    def _apply_config(self) -> None:
        """把配置刷到界面上。"""
        cfg = self._cfg

        # --- 置顶 ---
        want_top = bool(cfg.get("always_on_top", True))
        has_top = bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        if want_top != has_top:
            flags = self.windowFlags()
            flags = flags | Qt.WindowType.WindowStaysOnTopHint if want_top else flags & ~Qt.WindowType.WindowStaysOnTopHint
            was_visible = self.isVisible()
            self.setWindowFlags(flags)
            if was_visible:
                self.show()

        # --- 整窗不透明度 ---
        self.setWindowOpacity(max(0.05, min(1.0, cfg.get("window_opacity", 100) / 100)))

        # --- 正文样式 ---
        self._content_padding = int(cfg.get("page_padding", 30))
        self._apply_browser_style()
        if self._reader.chapter_count:
            self._refresh_render()

        # --- 文字衬底 ---
        # 刻意不用 QGraphicsDropShadowEffect：它会把正文控件变成独立合成层，
        # 导致抽屉/工具条的半透明背景与正文混合出错（正文会透过抽屉显形）。
        # 改在 paintEvent 里统一绘制，z 序和混合由窗口自己管。

        # --- 背景 ---
        self._load_bg_pixmap()
        self.update()

        # --- 老板键 ---
        if self._hotkey._combo != cfg.get("hotkey", "ctrl+shift+x"):
            self._hotkey.update(cfg.get("hotkey", "ctrl+shift+x"))

        # --- 顶栏 / 托盘显隐 ---
        self._apply_chrome()

    def _apply_chrome(self) -> None:
        """顶栏和托盘的显示状态。

        顶栏是"用户知道窗口在哪、程序在跑"的主要线索，默认常驻。
        关掉它之后退回"鼠标移入才浮现"的形态。
        """
        # 边框栏不常驻：鼠标移到窗口顶部才出现（由 _hover_update 控制），
        # 所以这里一律先收起
        self._toolbar.hide()

        if self._tray is not None:
            if self._cfg.get("show_tray", True):
                self._tray.set_window_visible(self._visible)
                self._tray.show()
                # 启动时弹一次气泡：让用户明确知道"程序已经在跑，图标在哪"
                if not self._notified and self._cfg.get("notify_on_start", True):
                    self._notified = True
                    self._tray.notify_started()
            else:
                self._tray.hide()

    def _apply_browser_style(self) -> None:
        cfg = self._cfg
        pad = self._content_padding
        extra = self._side_padding()

        if cfg.get("bg_mode") == "transparent":
            bg = "transparent"
        else:
            bg = theme.rgba_css(cfg.get("bg_color", "#1c1c1e"), cfg.get("bg_opacity", 80))

        self._browser.setStyleSheet(f"""
            QTextBrowser {{
                background: {bg};
                border: none;
                padding: {pad}px {extra}px {pad}px {extra}px;
                selection-background-color: {theme.ACCENT};
                selection-color: #ffffff;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 7px;
                margin: {pad}px 0 {pad}px 0;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(128, 128, 128, 90);
                border-radius: 3px;
                min-height: 28px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: rgba(128, 128, 128, 150);
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none; height: 0;
            }}
        """)

    def _side_padding(self) -> int:
        """内容最大宽度限制：窗口宽时把正文居中留白。"""
        limit = int(self._cfg.get("content_width", 0) or 0)
        if limit <= 0:
            return self._content_padding
        avail = self._browser.width() - self._content_padding * 2
        if avail <= limit:
            return self._content_padding
        return self._content_padding + (avail - limit) // 2

    def _load_bg_pixmap(self) -> None:
        path = self._cfg.get("bg_image", "")
        if self._cfg.get("bg_mode") != "image" or not path:
            self._bg_pixmap = None
            self._bg_pixmap_path = ""
            return
        if path == self._bg_pixmap_path and self._bg_pixmap is not None:
            return
        pix = QPixmap(path)
        if pix.isNull():
            self._bg_pixmap = None
            return
        self._bg_pixmap = pix.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._bg_pixmap_path = path

    # ================================================================== 绘制
    def paintEvent(self, event):
        cfg = self._cfg
        mode = cfg.get("bg_mode", "transparent")
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect())
        radius = float(theme.RADIUS_WINDOW)
        path = QPainterPath()
        path.addRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

        # 垫一层肉眼看不见的底（alpha = 1/255），覆盖**整个窗口矩形**。
        #
        # 透明窗口在 Windows 上按像素 alpha 做鼠标命中测试：全透明的像素会让鼠标
        # 穿透到下层窗口，窗口边缘的缩放热区于是收不到事件（表现成"拖不动大小"）。
        # 这里必须用 fillRect 而不是沿圆角路径填充 —— 圆角之外那几个像素否则仍是
        # 全透明，右下角（最顺手的缩放手柄）就点不到。
        painter.fillRect(QRectF(self.rect()), QColor(0, 0, 0, 1))

        if mode in ("color", "image"):
            if mode == "image" and self._bg_pixmap is not None:
                painter.setClipPath(path)
                painter.drawPixmap(0, 0, self._bg_pixmap)
            painter.fillPath(
                path,
                theme.qcolor(
                    cfg.get("bg_color", "#1c1c1e"),
                    round(cfg.get("bg_opacity", 80) / 100 * 255),
                ),
            )

        # 可选衬底：全透明模式下垫一层几乎看不见的淡色，避免文字被同色桌面吞掉
        if mode == "transparent" and cfg.get("text_shadow"):
            tc = theme.qcolor(cfg.get("text_color", "#1d1d1f"))
            luma = 0.299 * tc.red() + 0.587 * tc.green() + 0.114 * tc.blue()
            pad = float(self._content_padding) * 0.5
            backing = QPainterPath()
            backing.addRoundedRect(rect.adjusted(pad, pad, -pad, -pad), 10.0, 10.0)
            painter.fillPath(
                backing,
                QColor(255, 255, 255, 40) if luma < 128 else QColor(0, 0, 0, 40),
            )

        # 描边：让用户看得见窗口边界。顶栏常驻或有边框设置时画一圈淡轮廓。
        if cfg.get("show_border", True) and (self._toolbar.isVisible() or self.underMouse()):
            painter.setPen(
                QColor(255, 255, 255, 52) if mode != "color" else QColor(0, 0, 0, 40)
            )
            painter.drawPath(path)

        painter.end()

    # ================================================================== 事件
    def enterEvent(self, event):
        """故意什么都不做。

        透明窗口下这些进出事件不可信：鼠标进入子控件（正文区）时，父窗口同样会
        收到 leaveEvent。如果拿它们驱动显隐，就会出现"鼠标明明在窗口里、窗口却
        消失"的情况。显隐一律由 _poll_cursor 按坐标判断。
        """
        super().enterEvent(event)

    def leaveEvent(self, event):
        """故意什么都不做，理由同 enterEvent。"""
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):
        local = event.position().toPoint()

        if self._resize_edge and self._resize_origin is not None:
            self._do_resize(event.globalPosition().toPoint())
            event.accept()
            return
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return

        self._hover_update(local)
        self._update_cursor(self._edge_at(local))
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            edge = self._edge_at(event.position().toPoint())
            if edge:
                self._resize_edge = edge
                self._resize_origin = event.globalPosition().toPoint()
                self._resize_geom = self.geometry()
                self._begin_interaction()
                event.accept()
                return
            if event.modifiers() & Qt.KeyboardModifier.AltModifier:
                self._drag_offset = (
                    event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                )
                self._begin_interaction()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        was_interacting = self._interacting
        self._resize_edge = ""
        self._resize_origin = None
        self._drag_offset = None
        self._interacting = False
        # 拖完确认窗口还在屏幕里（拖拽过程中允许临时越界，松手时收回来）
        if was_interacting:
            self._ensure_visible()
        super().mouseReleaseEvent(event)

    def _begin_interaction(self) -> None:
        """开始拖动 / 缩放：期间冻结"鼠标移开就淡出"。

        抓窗口边缘时鼠标很容易滑到窗口外面，如果仍按"出界就消失"处理，
        窗口会在操作途中消失，缩放根本没法完成。
        """
        self._interacting = True
        self._idle_timer.stop()
        # 操作期间视作"在窗口内"，同时清掉出界计数。
        # 否则松手后若鼠标停在窗口外，_inside 还是 False，轮询就不会再触发隐藏，
        # 窗口会一直留在屏幕上。
        self._inside = True
        self._outside_hits = 0
        self._set_active_opacity()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._cfg["window_width"] = self.width()
        self._cfg["window_height"] = self.height()
        self._toolbar.adjustSize()
        self._place_toolbar()
        self._drawer.reposition()
        self._apply_browser_style()
        if self._cfg.get("bg_mode") == "image":
            self._bg_pixmap_path = ""      # 触发按新尺寸重采样
            self._load_bg_pixmap()

        # 尺寸一变换行就变，章节的像素范围得重新量；延到本次事件处理完再算，
        # 否则拿到的还是旧布局
        if self._reader.chapter_count:
            QTimer.singleShot(0, self._after_resize)

    def _after_resize(self) -> None:
        """窗口尺寸变化后重新测量章节位置，并尽量停在原来的地方。"""
        if not self._reader.chapter_count or self._rebuilding:
            return
        idx, ratio = self._current_position()
        self._measure_chapters()
        self._scroll_to(idx, ratio)

    def moveEvent(self, event):
        super().moveEvent(event)
        self._cfg["window_x"] = self.x()
        self._cfg["window_y"] = self.y()

    def eventFilter(self, obj, event):
        # 工具条空白处按住即可拖动窗口
        if obj is getattr(self, "_toolbar", None):
            etype = event.type()
            if etype == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._drag_offset = (
                    event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                )
                return True
            if etype == QEvent.Type.MouseMove and self._drag_offset is not None:
                self.move(event.globalPosition().toPoint() - self._drag_offset)
                return True
            if etype == QEvent.Type.MouseButtonRelease:
                self._drag_offset = None
                return True
            return False

        if obj in (self._browser, self._browser.viewport()):
            etype = event.type()
            if etype == QEvent.Type.KeyPress:
                if self._handle_key(event):
                    return True
            elif etype == QEvent.Type.Wheel:
                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    self._zoom(1 if event.angleDelta().y() > 0 else -1)
                    return True
            elif etype == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton and (
                    event.modifiers() & Qt.KeyboardModifier.AltModifier
                ):
                    self._drag_offset = (
                        event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                    )
                    return True
            elif etype == QEvent.Type.MouseMove:
                local = self.mapFromGlobal(event.globalPosition().toPoint())
                self._hover_update(local)
                if self._drag_offset is not None:
                    self.move(event.globalPosition().toPoint() - self._drag_offset)
                    return True
            elif etype == QEvent.Type.MouseButtonRelease:
                self._drag_offset = None
        return super().eventFilter(obj, event)

    # ================================================================== 键盘
    def keyPressEvent(self, event):
        if not self._handle_key(event):
            super().keyPressEvent(event)

    def _handle_key(self, event) -> bool:
        key = event.key()
        mods = event.modifiers()

        if key == Qt.Key.Key_Escape:
            self.toggle_visibility()
            return True
        # 上下键：按正文行滚动（约 2 行）。方向键含小键盘方向键。
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down) and not (mods & SCROLL_BLOCK_MODS):
            self._scroll_lines(-2 if key == Qt.Key.Key_Up else 2)
            return True
        if key == Qt.Key.Key_Left:
            self._prev_chapter()
            return True
        if key == Qt.Key.Key_Right:
            self._next_chapter()
            return True
        if key == Qt.Key.Key_O and mods & Qt.KeyboardModifier.ControlModifier:
            self.open_file_dialog()
            return True
        if key == Qt.Key.Key_Comma and mods & Qt.KeyboardModifier.ControlModifier:
            self._open_settings()
            return True
        if key == Qt.Key.Key_J and mods & Qt.KeyboardModifier.ControlModifier:
            self._toggle_drawer()
            return True
        return False

    def _line_px(self) -> float:
        """正文一行的实际像素高度；量不出来时按字号估算。"""
        # 首选：从已排版的正文段落实测第一行高度，跟字体/字号/行高设置天然一致
        try:
            doc = self._browser.document()
            block = doc.begin()
            while block.isValid() and block.blockFormat().headingLevel() > 0:
                block = block.next()          # 跳过章节标题
            if block.isValid():
                lay = block.layout()
                if lay is not None and lay.lineCount() > 0:
                    return max(6.0, float(lay.lineAt(0).height()))
        except Exception:
            pass
        # 回退：字号 × 字体行距 × 行高百分比
        font = QFont(self._cfg.get("font_family") or "Microsoft YaHei UI")
        font.setPixelSize(max(1, int(self._cfg.get("font_size", 17))))
        ratio = max(100, int(self._cfg.get("line_height", 185))) / 100.0
        return max(6.0, QFontMetricsF(font).lineSpacing() * ratio)

    def _scroll_lines(self, lines: int) -> None:
        """按行滚动。lines 为正向下、负向上。

        直接改滚动条的值，这样会走既有的 _on_scroll：自动更新当前章、
        进度标签，并在滚到文档边缘时滑动阅读窗口（自然衔接上一/下一章）。
        """
        if not self._reader.chapter_count:
            return
        bar = self._browser.verticalScrollBar()
        bar.setValue(bar.value() + int(round(self._line_px() * lines)))

    def _zoom(self, delta: int) -> None:
        size = int(self._cfg.get("font_size", 17)) + delta
        size = max(10, min(40, size))
        self._cfg["font_size"] = size
        self._apply_browser_style()
        self._refresh_render()
        cfg_mod.save_config(self._cfg)

    # ================================================================== 缩放
    def _edge_at(self, pos: QPoint) -> str:
        w, h, m = self.width(), self.height(), RESIZE_EDGE
        left, right = pos.x() < m, pos.x() > w - m
        top, bottom = pos.y() < m, pos.y() > h - m
        if top and left:
            return "tl"
        if top and right:
            return "tr"
        if bottom and left:
            return "bl"
        if bottom and right:
            return "br"
        if left:
            return "l"
        if right:
            return "r"
        if top:
            return "t"
        if bottom:
            return "b"
        return ""

    def _update_cursor(self, edge: str) -> None:
        cursors = {
            "l": Qt.CursorShape.SizeHorCursor,
            "r": Qt.CursorShape.SizeHorCursor,
            "t": Qt.CursorShape.SizeVerCursor,
            "b": Qt.CursorShape.SizeVerCursor,
            "tl": Qt.CursorShape.SizeFDiagCursor,
            "br": Qt.CursorShape.SizeFDiagCursor,
            "tr": Qt.CursorShape.SizeBDiagCursor,
            "bl": Qt.CursorShape.SizeBDiagCursor,
        }
        self.setCursor(cursors.get(edge, Qt.CursorShape.ArrowCursor))

    def _do_resize(self, global_pos: QPoint) -> None:
        dx = global_pos.x() - self._resize_origin.x()
        dy = global_pos.y() - self._resize_origin.y()
        geo = self._resize_geom
        x, y, w, h = geo.x(), geo.y(), geo.width(), geo.height()
        min_w, min_h = self.minimumWidth(), self.minimumHeight()

        # 上限：不超过单块屏幕的可用区域。否则窗口能被拖得比屏幕还大，
        # 尺寸一旦存下来，下次启动就可能整块落在屏幕外，找不回来。
        area = self._largest_available()
        max_w, max_h = area.width(), area.height()

        if "r" in self._resize_edge:
            w = max(min_w, min(max_w, geo.width() + dx))
        if "b" in self._resize_edge:
            h = max(min_h, min(max_h, geo.height() + dy))
        if "l" in self._resize_edge:
            new_w = max(min_w, min(max_w, geo.width() - dx))
            x = x + (geo.width() - new_w)
            w = new_w
        if "t" in self._resize_edge:
            new_h = max(min_h, min(max_h, geo.height() - dy))
            y = y + (geo.height() - new_h)
            h = new_h

        self.setGeometry(x, y, w, h)

    # ================================================================== 工具条
    def _place_toolbar(self) -> None:
        """顶栏横跨窗口宽度。"""
        margin = TOOLBAR_MARGIN
        self._toolbar.setFixedWidth(max(220, self.width() - margin * 2))
        self._toolbar.adjustSize()
        self._toolbar.move(margin, margin)
        self._toolbar.raise_()
        self._drawer.raise_()

    def _show_toolbar(self) -> None:
        if not self._visible or not self._cfg.get("show_titlebar", True):
            return
        self._place_toolbar()
        self._toolbar.show()
        self._toolbar.raise_()

    def _hide_toolbar(self) -> None:
        if self._toolbar.isVisible():
            self._toolbar.hide()
        self._drawer.close_drawer()

    def _hover_update(self, pos: QPoint) -> None:
        """按鼠标位置决定边框栏显隐：只在顶部那一带出现，鼠标离开就收起。"""
        if not self._cfg.get("show_titlebar", True):
            return
        if self._toolbar.isVisible():
            # 留点余量，避免贴着边框栏边缘移动时反复闪
            if not self._toolbar.geometry().adjusted(-6, -10, 6, 12).contains(pos):
                self._toolbar.hide()
        elif pos.y() <= HOVER_ZONE_HEIGHT:
            self._show_toolbar()

    def _poll_cursor(self) -> None:
        """按光标位置驱动「移入显示 / 移开全透明」和边框栏显隐。

        这是显示/隐藏的**唯一**判据。不要同时依赖 enterEvent / leaveEvent：
        鼠标进入子控件（正文区）时父窗口会收到 leaveEvent，两套判据打架，
        快速移动鼠标时窗口就忽隐忽现。

        「进入」一次命中就立刻显示；「离开」要连续采样确认两次才生效，
        免得鼠标快速划过窗口边缘时被误判成离开。
        """
        if not self._visible or self._suspend_idle or self._interacting:
            return

        local = self.mapFromGlobal(QCursor.pos())

        if self.rect().contains(local):
            self._outside_hits = 0
            if not self._inside:
                self._inside = True
                self._idle_timer.stop()
                self._set_active_opacity()
                self.update()
            self._hover_update(local)
            return

        self._outside_hits += 1
        if self._inside and self._outside_hits >= OUTSIDE_CONFIRM:
            self._inside = False
            delay = int(self._cfg.get("idle_delay_ms", 0))
            if delay <= 0:
                self._go_idle()
            else:
                self._idle_timer.start(delay)

    # ================================================================== 空转
    def _go_idle(self) -> None:
        """鼠标离开窗口：**立刻**切到设定透明度（默认完全透明）。

        去掉淡入淡出动画——鼠标进出的响应要是"瞬间"的，动画会拖出可见的过渡。
        """
        if not self._visible or self._suspend_idle:
            return
        self._hide_toolbar()
        self.setWindowOpacity(
            max(0.0, min(1.0, self._cfg.get("idle_opacity", 0) / 100))
        )

    def _set_active_opacity(self) -> None:
        """鼠标进入窗口：立刻恢复不透明度。"""
        if not self._visible:
            return
        self._ensure_topmost()
        self.setWindowOpacity(
            max(0.05, min(1.0, self._cfg.get("window_opacity", 100) / 100))
        )

    # ================================================================== 老板键
    def toggle_visibility(self) -> None:
        if self.isVisible():
            self._drawer.close_drawer()
            self.hide()
            self._visible = False
        else:
            self.show()
            self._visible = True
            self.setWindowOpacity(
                max(0.05, min(1.0, self._cfg.get("window_opacity", 100) / 100))
            )
            self.activateWindow()
        if self._tray is not None:
            self._tray.set_window_visible(self._visible)
        cfg_mod.save_config(self._cfg)

    # ================================================================== 菜单
    def _show_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(menu_qss())

        menu.addAction("打开 TXT…", "Ctrl+O", self.open_file_dialog)
        menu.addAction("目录", "Ctrl+J", self._toggle_drawer)

        recent = [p for p in self._cfg.get("recent_files", []) if Path(p).exists()]
        if recent:
            sub = menu.addMenu("最近打开")
            sub.setStyleSheet(menu_qss())
            for path in recent[:8]:
                sub.addAction(Path(path).stem, lambda p=path: self.load_file(p))

        menu.addSeparator()
        menu.addAction("阅读设置…", "Ctrl+,", self._open_settings)
        menu.addAction("隐藏窗口", self._cfg.get("hotkey", "ctrl+shift+x").upper(), self.toggle_visibility)
        menu.addSeparator()
        menu.addAction("退出", self._quit)

        menu.exec(self._browser.viewport().mapToGlobal(pos))

    def _quit(self) -> None:
        self._auto_save()
        cfg_mod.save_config(self._cfg)
        self._hotkey.stop()
        self._wait_loader()
        if self._tray is not None:
            self._tray.hide()
        QApplication.quit()

    # ================================================================== 阅读
    def open_file_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "打开小说", "", "文本文件 (*.txt *.md);;所有文件 (*)"
        )
        if path:
            self.load_file(path)

    # ================================================================== 加载
    def load_file(self, path: str) -> None:
        """异步加载。

        解析放到子线程，主线程先亮出"正在打开…"并保持窗口可见——否则选完文件后
        界面会先消失几秒再突然出现，像是卡死了。
        """
        self._file_path = path
        cfg_mod.add_recent(self._cfg, path)
        cfg_mod.save_config(self._cfg)
        if self._tray is not None:
            self._tray.set_recent(self._cfg.get("recent_files", []))

        # 加载期间冻结"鼠标移开就淡出"，并强制可见
        self._suspend_idle = True
        self._idle_timer.stop()
        self.setWindowOpacity(
            max(0.05, min(1.0, self._cfg.get("window_opacity", 100) / 100))
        )

        self._start_loading_animation(Path(path).name)

        self._loader = FileLoader(
            path, int(self._cfg.get("chars_per_page", 3000)), self
        )
        self._loader.loaded.connect(self._on_file_loaded)
        self._loader.failed.connect(self._on_load_failed)
        self._loader.start()

    def _start_loading_animation(self, name: str) -> None:
        self._loading_name = name
        self._loading_tick = 0
        self._paint_loading()
        self._loading_timer.start(260)

    def _paint_loading(self) -> None:
        dots = "." * (self._loading_tick % 4)
        self._browser.setHtml(
            '<div style="color:rgba(150,150,158,235); font-size:14px;'
            ' line-height:200%;">'
            f"正在打开《{self._loading_name}》{dots}"
            "</div>"
        )

    def _on_loading_tick(self) -> None:
        self._loading_tick += 1
        self._paint_loading()

    def _stop_loading_animation(self) -> None:
        self._loading_timer.stop()
        self._suspend_idle = False

    def _on_load_failed(self, message: str) -> None:
        self._stop_loading_animation()
        self._browser.setHtml(f'<p style="color:#ff453a">读取失败：{message}</p>')

    def _on_file_loaded(self, engine) -> None:
        self._stop_loading_animation()
        self._reader = engine

        total = engine.chapter_count
        if not total:
            self._show_empty()
            return

        self._drawer.set_chapters([c.title for c in engine.chapters])

        progress = self._bookmarks.get_progress(self._file_path)
        start = 0
        ratio = 0.0
        if progress is not None:
            start = max(0, min(int(progress.chapter_index), total - 1))
            ratio = max(0.0, min(1.0, getattr(progress, "scroll_ratio", 0.0) or 0.0))

        self._chapter_index = start
        self._rebuild_window(start, start, ratio)

    # ================================================================== 渲染
    def _preload(self) -> int:
        return max(1, min(5, int(self._cfg.get("preload_chapters", 2))))

    def _window_bounds(self, center: int) -> tuple[int, int]:
        p = self._preload()
        total = self._reader.chapter_count
        return max(0, center - p), min(total - 1, center + p)

    def _rebuild_window(
        self,
        center: int,
        anchor_chapter: int | None = None,
        anchor_ratio: float = 0.0,
    ) -> None:
        """把 center 前后各 preload 章拼成一个连续文档渲染出来。

        这样上下滚动都是一篇连贯的长文，章末不会出现"加载下一章"的跳变；
        滚出这个范围再整体滑动重建，内存里始终只有 2*preload+1 章。
        """
        total = self._reader.chapter_count
        if not total:
            self._show_empty()
            return

        center = max(0, min(center, total - 1))
        lo, hi = self._window_bounds(center)
        chapters = [
            c for c in (self._reader.get_chapter(i) for i in range(lo, hi + 1)) if c
        ]
        if not chapters:
            self._show_empty()
            return

        self._rebuilding = True
        try:
            t = time.perf_counter()
            html = theme.build_range_html(self._cfg, chapters)
            _perf("build_html", t); t = time.perf_counter()

            self._browser.setHtml(html)
            _perf("setHtml", t); t = time.perf_counter()

            theme.apply_document_format(self._browser, self._cfg)
            _perf("apply_format", t); t = time.perf_counter()

            self._apply_browser_style()
            _perf("browser_style", t); t = time.perf_counter()

            self._tag_chapter_blocks(chapters)
            _perf("tag_blocks", t); t = time.perf_counter()

            self._measure_chapters()
            _perf("measure", t); t = time.perf_counter()

            self._window_lo, self._window_hi = lo, hi
        finally:
            self._rebuilding = False

        if anchor_chapter is None:
            anchor_chapter = center
        anchor_chapter = max(lo, min(anchor_chapter, hi))
        self._chapter_index = anchor_chapter
        self._scroll_to(anchor_chapter, anchor_ratio)
        self._drawer.set_current(anchor_chapter)
        self._update_progress_label()

    def _tag_chapter_blocks(self, chapters: list) -> None:
        """给每个段落 block 标记所属章节。

        以标题 block（headingLevel > 0）为分界：每遇到一个标题就进入下一章。
        不按"第几个 block"推算——Qt 排版时会插入额外 block，序号对不上，
        结果就是量不出某几章的位置，滚动定位整个失灵。
        """
        doc = self._browser.document()
        order = [c.index for c in chapters]

        block = doc.begin()
        pos = -1
        while block.isValid():
            if block.blockFormat().headingLevel() > 0:
                pos += 1
            if 0 <= pos < len(order):
                block.setUserState(order[pos])
            block = block.next()

    def _measure_chapters(self) -> None:
        """量出每章在文档里的纵向像素范围，用于滚动定位。"""
        doc = self._browser.document()
        layout = doc.documentLayout()

        tops: dict[int, float] = {}
        block = doc.begin()
        while block.isValid():
            idx = block.userState()
            if idx >= 0 and idx not in tops:
                tops[idx] = layout.blockBoundingRect(block).top()
            block = block.next()

        total_h = max(1.0, doc.size().height())
        order = sorted(tops)
        self._chapter_y = {}
        for i, idx in enumerate(order):
            top = tops[idx]
            bottom = tops[order[i + 1]] if i + 1 < len(order) else total_h
            self._chapter_y[idx] = (top, max(top + 1.0, bottom))

    def _chapter_at(self, y: float) -> int | None:
        """给定文档纵坐标，返回它落在哪一章。"""
        if not self._chapter_y:
            return None
        for idx in sorted(self._chapter_y):
            top, bottom = self._chapter_y[idx]
            if top <= y < bottom:
                return idx
        order = sorted(self._chapter_y)
        return order[0] if y < self._chapter_y[order[0]][0] else order[-1]

    def _scroll_to(self, chapter_index: int, ratio: float = 0.0) -> None:
        """滚到指定章的指定位置（ratio 为章内比例）。

        向上取整是必须的：章的起点通常是小数（例如 2094.97px），
        setValue(int(...)) 会落在 2094，正好掉进前一章的最后一个像素里，
        结果"跳到第 8 章"变成停在第 7 章。
        """
        span = self._chapter_y.get(chapter_index)
        if span is None:
            return
        top, bottom = span
        y = top + (bottom - top) * max(0.0, min(1.0, ratio))
        self._browser.verticalScrollBar().setValue(int(math.ceil(y)))

    def _current_position(self) -> tuple[int, float]:
        """视口顶部当前落在（哪一章, 章内比例）。"""
        y = float(self._browser.verticalScrollBar().value())
        idx = self._chapter_at(y)
        if idx is None:
            return self._chapter_index, 0.0
        top, bottom = self._chapter_y.get(idx, (y, y + 1.0))
        ratio = (y - top) / max(1.0, bottom - top)
        return idx, max(0.0, min(1.0, ratio))

    def _on_scroll(self, value: int) -> None:
        """滚动时更新当前章；快滚到文档顶/底时把阅读窗口整体滑动一下。

        判据用"距文档边缘还有几屏"而不是"章节偏离中心"——后者在窗口被首尾
        clamp 住时（比如刚打开只有 3 章）会导致滚到底就卡住、翻不动。
        """
        if self._rebuilding or not self._chapter_y:
            return

        viewport_h = self._browser.viewport().height()
        bar = self._browser.verticalScrollBar()
        idx = self._chapter_at(value + viewport_h * 0.5)
        if idx is None:
            return

        if idx != self._chapter_index:
            self._chapter_index = idx
            self._drawer.set_current(idx)
            self._update_progress_label()

        total = self._reader.chapter_count
        margin = max(200.0, viewport_h * 2.0)
        need_earlier = self._window_lo > 0 and value < margin
        need_later = self._window_hi < total - 1 and value > bar.maximum() - margin
        if need_earlier or need_later:
            self._slide_window(idx)

    def _slide_window(self, center: int) -> None:
        """保持阅读位置不变，把窗口整体挪到新的中心。"""
        lo, hi = self._window_bounds(center)
        if (lo, hi) == (self._window_lo, self._window_hi):
            # 算出来的窗口和当前一模一样，重建纯属浪费。
            # 之前缺这道判断：滚动到底部时反复触发滑动、每次都整篇重渲染，
            # 每滚一步白卡两百毫秒，表现就是"滚到下面就卡住然后乱跳"。
            return
        anchor_chapter, anchor_ratio = self._current_position()
        self._rebuild_window(center, anchor_chapter, anchor_ratio)

    def _refresh_render(self) -> None:
        """配置变化（字号/字色/行高等）后，保持当前位置重新渲染。"""
        if not self._reader.chapter_count:
            return
        idx, ratio = self._current_position()
        self._rebuild_window(idx, idx, ratio)

    def _update_progress_label(self) -> None:
        total = self._reader.chapter_count
        if not total:
            self._toolbar.set_progress("—/—")
            self._toolbar.set_title("LeapR")
        else:
            self._toolbar.set_progress(f"{self._chapter_index + 1}/{total}")
            chapter = self._reader.get_chapter(self._chapter_index)
            name = self._reader.title or "LeapR"
            if chapter is not None and total > 1:
                self._toolbar.set_title(f"{name} · {chapter.title}")
            else:
                self._toolbar.set_title(name)

        if self._tray is not None:
            self._tray.set_title(Path(self._file_path).stem if self._file_path else "")

    def _show_empty(self) -> None:
        self._toolbar.set_progress("—/—")
        self._toolbar.set_title("LeapR")
        self._chapter_y = {}
        self._window_lo = self._window_hi = -1
        hint = self._cfg.get("hotkey", "ctrl+shift+x").upper()
        self._browser.setHtml(
            f'<div style="color:rgba(140,140,148,220); font-size:14px; line-height:200%;">'
            f"拖入 TXT 文件，或按 Ctrl+O 打开<br><br>"
            f"← → 翻章　↑ ↓ 滚动　Ctrl+滚轮 调字号<br>"
            f"Esc 或 {hint} 隐藏窗口<br>"
            f"Ctrl+, 打开设置　Ctrl+J 打开目录"
            f"</div>"
        )

    def _goto_chapter(self, index: int, ratio: float = 0.0) -> None:
        """跳到指定章节：目录点击、上一章/下一章按钮都走这里。"""
        total = self._reader.chapter_count
        if not total:
            return
        index = max(0, min(index, total - 1))

        if self._window_lo <= index <= self._window_hi and index in self._chapter_y:
            # 目标章已经在当前文档里，直接滚过去，不用重渲染
            self._scroll_to(index, ratio)
            self._chapter_index = index
            self._drawer.set_current(index)
            self._update_progress_label()
        else:
            self._rebuild_window(index, index, ratio)

        self._save_progress()

    def _next_chapter(self) -> None:
        self._goto_chapter(self._chapter_index + 1)

    def _prev_chapter(self) -> None:
        self._goto_chapter(self._chapter_index - 1)

    def _toggle_drawer(self) -> None:
        if not self._reader.chapter_count:
            return
        if self._drawer.isVisible():
            self._drawer.close_drawer()
        else:
            self._drawer.open_drawer()
        self.update()

    def _on_chapter_selected(self, index: int) -> None:
        self._goto_chapter(index)

    def _save_progress(self) -> None:
        if not self._file_path or not self._reader.chapter_count:
            return
        idx, ratio = self._current_position()
        bar = self._browser.verticalScrollBar()
        self._bookmarks.save_progress(self._file_path, idx, bar.value(), ratio)

    def _auto_save(self) -> None:
        self._save_progress()
        cfg_mod.save_config(self._cfg)

    def _restore_last(self) -> None:
        last = self._bookmarks.get_last_file()
        if last:
            self.load_file(last)
        elif self._reader.chapter_count == 0:
            self._show_empty()

    # ================================================================== 设置
    def _open_settings(self) -> None:
        panel = SettingsPanel(self._cfg, self._fonts, self)
        panel.config_changed.connect(self._on_settings_changed)
        panel.fonts_changed.connect(self._on_fonts_changed)
        panel.exec()

        theme.apply_document_format(self._browser, self._cfg)
        self._refresh_render()
        cfg_mod.save_config(self._cfg)

    def _on_settings_changed(self, new_cfg: dict) -> None:
        self._cfg.update(new_cfg)
        self._apply_config()

    def _on_fonts_changed(self, files: list[str]) -> None:
        self._cfg["font_files"] = list(files)
        cfg_mod.save_config(self._cfg)

    # ================================================================== 拖放
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith((".txt", ".md")):
                self.load_file(path)
                break

    def closeEvent(self, event):
        self._auto_save()
        self._hotkey.stop()
        self._wait_loader()
        event.accept()

    def _wait_loader(self) -> None:
        """退出前等一下后台加载线程，免得 Qt 报 QThread 还在跑。"""
        if self._loader is not None and self._loader.isRunning():
            self._loader.wait(3000)
