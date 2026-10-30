"""边框栏（标题栏）：书名/章节 + 一组操作按钮。

显隐由主窗口的 _hover_update 控制——鼠标移到窗口顶部那一带才出现。
宽度不够时会自动收起次要按钮，保证书名和翻章始终可用。
"""

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from ui import theme

BAR_HEIGHT = 34
BAR_MARGIN = 8

# 空间不够时按这个顺序收起（越靠前越先收）。
# 退出/隐藏有托盘菜单兜底，打开/设置有快捷键兜底，所以先收它们。
COLLAPSE_ORDER = ["退出", "隐藏", "设置", "打开", "A-", "A+"]

# 布局边距 + 书名最少要占的宽度
BASE_WIDTH = 62


class TopBar(QWidget):
    """边框栏。只发信号，不直接操作主窗口。"""

    drawer_clicked = Signal()
    prev_clicked = Signal()
    next_clicked = Signal()
    open_clicked = Signal()
    settings_clicked = Signal()
    hide_clicked = Signal()
    close_clicked = Signal()
    font_smaller = Signal()
    font_larger = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("ToolBar")
        self.setStyleSheet(theme.toolbar_qss())
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setToolTip("按住这一条可以拖动窗口")
        self.setFixedHeight(BAR_HEIGHT)

        # 背景层：用一个铺满的 QFrame 承载底色。
        # 直接在本类的 paintEvent 里画不出效果（带 QSS 的控件上背景绘制不可靠，
        # 实测 paintEvent 有执行但像素没上屏）；QFrame + QSS 是可靠的
        # —— 左侧目录抽屉就是这么做的，已经验证过。
        self._bg = QFrame(self)
        self._bg.setObjectName("TopBarBg")
        self._bg.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._bg.setStyleSheet(
            f"""
            QFrame#TopBarBg {{
                background: {theme.PANEL_BG};
                border: 1px solid {theme.PANEL_BORDER};
                border-radius: {theme.RADIUS_PILL}px;
            }}
            """
        )

        self._full_title = "LeapR"
        self._buttons: dict[str, QPushButton] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 2, 6, 2)
        layout.setSpacing(2)
        self._layout = layout

        # 书名 + 章节：占左侧弹性空间，窗口变窄时自动省略
        self._title = QLabel("LeapR")
        self._title.setObjectName("TitleText")
        self._title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._title.setMinimumWidth(40)
        layout.addWidget(self._title, 1)

        def add(text: str, tip: str, signal, name: str = "") -> QPushButton:
            btn = QPushButton(text)
            btn.setToolTip(tip)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(signal.emit)
            if name:
                btn.setObjectName(name)
            self._buttons[text] = btn
            layout.addWidget(btn)
            return btn

        # 按钮文字只用中文/ASCII，避免符号字体缺字渲染成方块
        add("目录", "章节目录（Ctrl+J）", self.drawer_clicked)
        add("上章", "上一章（←）", self.prev_clicked)

        self._progress = QLabel("—/—")
        layout.addWidget(self._progress)

        add("下章", "下一章（→）", self.next_clicked)
        add("打开", "打开 TXT（Ctrl+O）", self.open_clicked)
        add("A-", "缩小字号（Ctrl+滚轮）", self.font_smaller)
        add("A+", "放大字号（Ctrl+滚轮）", self.font_larger)
        add("设置", "阅读设置 / 字体颜色（Ctrl+,）", self.settings_clicked)
        add("隐藏", "隐藏到托盘（Esc / 老板键）", self.hide_clicked)
        add("退出", "退出程序", self.close_clicked, name="CloseBtn")

        # 窗口窄下来时，放不下的按钮收进这里，而不是凭空消失。
        # 之前是把它们直接 hide()，用户会觉得"功能没了"。
        self._more_btn = QPushButton("更多")
        self._more_btn.setToolTip("窗口放不下的操作都收在这里")
        self._more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._more_btn.clicked.connect(self._show_more_menu)
        self._more_btn.hide()
        layout.addWidget(self._more_btn)
        self._collapsed: list[str] = []

    # ------------------------------------------------------------------ 状态
    def set_title(self, text: str) -> None:
        self._full_title = text or "LeapR"
        self._apply_elide()

    def set_progress(self, text: str) -> None:
        self._progress.setText(text or "—/—")

    # ------------------------------------------------------------------ 布局
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._bg.setGeometry(0, 0, self.width(), self.height())
        self._bg.lower()
        self._apply_elide()
        self._fit_buttons()

    def showEvent(self, event):
        super().showEvent(event)
        self._bg.setGeometry(0, 0, self.width(), self.height())
        self._bg.lower()

    def _required_width(self, extra: int = 0) -> int:
        return (
            sum(b.sizeHint().width() for b in self._buttons.values())
            + self._progress.sizeHint().width()
            + BASE_WIDTH
            + (len(self._buttons) + 2) * 2
            + extra
        )

    def _fit_buttons(self) -> None:
        """宽度不够时把次要按钮收进「更多」菜单。

        不要直接 hide()：按钮凭空消失，用户会以为功能被砍了。
        收进菜单至少还能点得到。

        注意这里判断的是 `isHidden()` 而不是 `isVisible()`：边框栏平时是隐藏的
        （只在鼠标悬停时出现），父控件不可见时所有子控件的 isVisible() 都会返回
        False，用 isVisible() 会导致收起逻辑整个失效。
        """
        for btn in self._buttons.values():
            btn.show()
        self._more_btn.hide()
        self._collapsed = []

        avail = self.width()
        if self._required_width() <= avail:
            return

        more_w = self._more_btn.sizeHint().width() + 2
        need = self._required_width(more_w)
        for name in COLLAPSE_ORDER:
            if need <= avail:
                break
            btn = self._buttons.get(name)
            if btn is None or btn.isHidden():
                continue
            btn.hide()
            self._collapsed.append(name)
            need -= btn.sizeHint().width() + 2

        if self._collapsed:
            self._more_btn.show()

    def _show_more_menu(self) -> None:
        """把收起来的操作弹出来。"""
        if not self._collapsed:
            return

        # 菜单经常会伸出窗口之外，鼠标一移过去，主窗口就判定"鼠标离开"而隐藏，
        # 菜单跟着消失 —— 表现就是"点了没反应"。所以弹出期间要冻结淡出。
        win = self.window()
        frozen = hasattr(win, "_interacting") and not win._interacting
        if frozen:
            win._interacting = True
        try:
            menu = QMenu(self)
            menu.setStyleSheet(theme.menu_qss())
            for name in self._collapsed:
                btn = self._buttons[name]
                action = menu.addAction(btn.text())
                action.setToolTip(btn.toolTip())
                action.triggered.connect(lambda _=False, b=btn: b.click())
            menu.exec(self._more_btn.mapToGlobal(QPoint(0, self._more_btn.height() + 4)))
        finally:
            if frozen:
                win._interacting = False

    def _apply_elide(self) -> None:
        """书名太长时用省略号收尾，而不是被硬裁掉。"""
        metrics = self._title.fontMetrics()
        avail = max(40, self._title.width())
        self._title.setText(
            metrics.elidedText(self._full_title, Qt.TextElideMode.ElideRight, avail)
        )

    # ------------------------------------------------------------------ 绘制
    # 背景由 self._bg（QFrame）负责，这里不再自绘。
