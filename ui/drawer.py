"""章节目录抽屉：从左侧滑出的章节列表。

原项目的目录是一个独立 QDialog 弹窗，会打断阅读；这里改成贴在窗口左侧的
抽屉，滑入滑出，带搜索过滤。顶部留出空间，避免压住悬浮工具条。
"""

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui import theme

DRAWER_WIDTH = 252
DRAWER_MARGIN = 12
DRAWER_TOP = 56          # 顶部留给悬浮工具条


class ChapterDrawer(QWidget):
    """章节列表抽屉。chapter_selected 携带章节索引。"""

    chapter_selected = Signal(int)

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("Drawer")
        self.setStyleSheet(theme.drawer_qss())
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.hide()

        self._titles: list[str] = []
        self._opening = True
        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(190)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.finished.connect(self._on_anim_finished)

        self._build_ui()

    # ------------------------------------------------------------------ 构建
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QHBoxLayout()
        header.setContentsMargins(4, 0, 10, 0)
        self._title_label = QLabel("目录")
        self._title_label.setObjectName("DrawerTitle")
        header.addWidget(self._title_label)
        header.addStretch(1)
        self._count_label = QLabel("")
        self._count_label.setObjectName("DrawerTitle")
        header.addWidget(self._count_label)
        root.addLayout(header)

        self._search = QLineEdit()
        self._search.setPlaceholderText("搜索章节")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._apply_filter)
        root.addWidget(self._search)

        self._list = QListWidget()
        self._list.setUniformItemSizes(True)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.itemClicked.connect(self._on_clicked)
        root.addWidget(self._list, 1)

    # ------------------------------------------------------------------ 数据
    def set_chapters(self, titles: list[str]) -> None:
        self._titles = list(titles)
        self._count_label.setText(f"{len(titles)} 章")
        self._apply_filter(self._search.text())

    def set_current(self, index: int) -> None:
        """高亮当前章，但不触发跳转。"""
        if 0 <= index < self._list.count():
            self._list.blockSignals(True)
            self._list.setCurrentRow(index)
            self._list.blockSignals(False)

    def _apply_filter(self, keyword: str) -> None:
        keyword = (keyword or "").strip().lower()
        self._list.clear()
        for i, title in enumerate(self._titles):
            if keyword and keyword not in title.lower():
                continue
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, i)
            self._list.addItem(item)

    def _on_clicked(self, item: QListWidgetItem) -> None:
        index = item.data(Qt.ItemDataRole.UserRole)
        if index is None:
            return
        self.chapter_selected.emit(int(index))
        self.close_drawer()

    # ------------------------------------------------------------------ 动画
    @staticmethod
    def _geometry_for(parent: QWidget) -> tuple[int, int]:
        height = max(160, parent.height() - DRAWER_TOP - DRAWER_MARGIN)
        return DRAWER_WIDTH, height

    def open_drawer(self) -> None:
        if not self._titles:
            return
        self._opening = True
        w, h = self._geometry_for(self.parentWidget())
        self.resize(w, h)
        top = DRAWER_TOP
        start = QPoint(-w - 4, top)
        end = QPoint(DRAWER_MARGIN, top)

        self._anim.stop()
        self.move(start)
        self.show()
        self.raise_()
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.start()
        self._search.setFocus()

    def close_drawer(self) -> None:
        if not self.isVisible():
            return
        self._opening = False
        w, _ = self._geometry_for(self.parentWidget())
        start = self.pos()
        end = QPoint(-w - 4, start.y())
        self._anim.stop()
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.start()

    def _on_anim_finished(self) -> None:
        """动画结束后才真正隐藏，避免滑出过程中被裁掉。"""
        if not self._opening:
            self.hide()

    def toggle(self) -> None:
        if self.isVisible():
            self.close_drawer()
        else:
            self.open_drawer()

    def reposition(self) -> None:
        """窗口尺寸变化时重排。"""
        if not self.isVisible():
            return
        w, h = self._geometry_for(self.parentWidget())
        self.resize(w, h)
        self.move(DRAWER_MARGIN, DRAWER_TOP)
