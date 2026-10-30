"""系统托盘图标：让用户能确认程序在运行，并提供退出入口。

没有托盘时，窗口一旦隐藏（老板键 / 全透明），用户既看不到任何痕迹，
也没有办法控制程序——这是之前最大的可用性缺口。
"""

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ui import theme
from ui.theme import menu_qss          # 样式统一放在 theme，这里 re-export 兼容旧引用

MAX_RECENT = 8


class TrayIcon(QSystemTrayIcon):
    """托盘图标 + 菜单。"""

    toggle_requested = Signal()
    open_requested = Signal()
    drawer_requested = Signal()
    settings_requested = Signal()
    recenter_requested = Signal()
    quit_requested = Signal()
    recent_requested = Signal(str)

    def __init__(self, icon: QIcon, parent=None):
        super().__init__(icon, parent)
        self.setToolTip("LeapR")

        self._menu = QMenu()
        self._menu.setStyleSheet(menu_qss())

        self._toggle_action = QAction("隐藏窗口", self._menu)
        self._toggle_action.triggered.connect(self.toggle_requested.emit)
        self._menu.addAction(self._toggle_action)

        recenter_action = QAction("窗口归位", self._menu)
        recenter_action.setToolTip("把窗口收回主屏中央并收成放得下的尺寸")
        recenter_action.triggered.connect(self.recenter_requested.emit)
        self._menu.addAction(recenter_action)

        self._menu.addSeparator()

        open_action = QAction("打开小说…", self._menu)
        open_action.triggered.connect(self.open_requested.emit)
        self._menu.addAction(open_action)

        drawer_action = QAction("章节目录", self._menu)
        drawer_action.triggered.connect(self.drawer_requested.emit)
        self._menu.addAction(drawer_action)

        settings_action = QAction("阅读设置…", self._menu)
        settings_action.triggered.connect(self.settings_requested.emit)
        self._menu.addAction(settings_action)

        self._recent_menu = QMenu("最近打开", self._menu)
        self._recent_menu.setStyleSheet(menu_qss())
        self._menu.addMenu(self._recent_menu)

        self._menu.addSeparator()

        quit_action = QAction("退出", self._menu)
        quit_action.triggered.connect(self.quit_requested.emit)
        self._menu.addAction(quit_action)

        self.setContextMenu(self._menu)
        self.activated.connect(self._on_activated)

    # ------------------------------------------------------------------ 状态
    def set_window_visible(self, visible: bool) -> None:
        self._toggle_action.setText("隐藏窗口" if visible else "显示窗口")

    def set_title(self, text: str) -> None:
        self.setToolTip(f"LeapR · {text}" if text else "LeapR")

    def set_recent(self, paths: list[str]) -> None:
        self._recent_menu.clear()
        usable = [p for p in paths if Path(p).exists()][:MAX_RECENT]
        if not usable:
            empty = QAction("（无）", self._recent_menu)
            empty.setEnabled(False)
            self._recent_menu.addAction(empty)
            return
        for path in usable:
            action = QAction(Path(path).stem, self._recent_menu)
            action.triggered.connect(lambda _=False, p=path: self.recent_requested.emit(p))
            self._recent_menu.addAction(action)

    # ------------------------------------------------------------------ 提示
    def notify_started(self) -> None:
        """启动气泡：直接回答"它到底跑起来没有、图标在哪"。"""
        self.showMessage(
            "LeapR已在运行",
            "双击托盘图标显示 / 隐藏窗口；右键可打开文件、设置或退出。\n"
            "Esc 或老板键同样可以快速隐藏窗口。",
            QSystemTrayIcon.MessageIcon.Information,
            6000,
        )

    # ------------------------------------------------------------------ 事件
    def _on_activated(self, reason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.toggle_requested.emit()
