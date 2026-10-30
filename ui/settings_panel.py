"""设置面板：背景 / 文字 / 窗口 三组，改动即时预览。

苹果式 Preferences 的布局思路：左边一列标签、右边控件、分组之间用细分隔线，
没有确定/取消的来回，改完就是改完了（关闭时若要回滚由调用方决定）。
"""

import copy

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from core.config import DEFAULTS
from ui import theme

FONT_FILTER = "字体文件 (*.ttf *.otf *.ttc *.otc)"


def _divider() -> QFrame:
    line = QFrame()
    line.setObjectName("Divider")
    line.setFixedHeight(1)
    return line


def _section(title: str) -> QLabel:
    label = QLabel(title)
    label.setObjectName("SectionTitle")
    return label


class SettingsPanel(QDialog):
    """设置面板。config_changed 实时抛出草案配置；fonts_changed 抛出字体文件列表。"""

    config_changed = Signal(dict)
    fonts_changed = Signal(list)

    def __init__(self, cfg: dict, font_manager, parent=None):
        super().__init__(parent)
        self.setObjectName("Settings")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(theme.settings_qss())
        self.setModal(True)
        # 高度跟着屏幕走，避免小屏上把底部按钮挤出去
        screen = QApplication.primaryScreen()
        avail_h = screen.availableGeometry().height() if screen else 900
        self.resize(436, min(660, int(avail_h * 0.82)))

        self._cfg = copy.deepcopy(cfg)
        self._fonts = font_manager
        self._updating = False
        self._drag_offset: QPoint | None = None
        self._w: dict = {}

        self._build()

    # ------------------------------------------------------------------ 构建
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("SettingsCard")
        outer.addWidget(card)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        card_layout.addWidget(self._build_header())

        body = QWidget()
        body.setObjectName("SettingsBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(22, 4, 22, 12)
        body_layout.setSpacing(9)

        self._build_background(body_layout)
        self._build_typography(body_layout)
        self._build_window(body_layout)
        body_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        card_layout.addWidget(scroll, 1)

        card_layout.addWidget(_divider())
        card_layout.addWidget(self._build_footer())

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setFixedHeight(50)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(22, 0, 14, 0)

        title = QLabel("阅读设置")
        title.setStyleSheet("font-size:15px; font-weight:600;")
        layout.addWidget(title)
        layout.addStretch(1)

        close = QPushButton("✕")
        close.setFixedSize(28, 28)
        close.clicked.connect(self.reject)
        layout.addWidget(close)
        return header

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        footer.setFixedHeight(58)
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(22, 0, 22, 0)

        reset = QPushButton("恢复默认")
        reset.setObjectName("Danger")
        reset.clicked.connect(self._reset_defaults)
        layout.addWidget(reset)
        layout.addStretch(1)

        done = QPushButton("完成")
        done.setObjectName("Primary")
        done.setFixedWidth(96)
        done.clicked.connect(self.accept)
        layout.addWidget(done)
        return footer

    # ------------------------------------------------------------- 背景分组
    def _build_background(self, root: QVBoxLayout) -> None:
        root.addWidget(_section("背景"))

        # 模式：三段式
        row = QHBoxLayout()
        row.setSpacing(6)
        self._w["mode_group"] = QButtonGroup(self)
        self._w["mode_group"].setExclusive(True)
        for key, text in (("transparent", "全透明"), ("color", "纯色"), ("image", "图片")):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setChecked(self._cfg.get("bg_mode") == key)
            btn.clicked.connect(lambda _=False, k=key: self._touch(bg_mode=k))
            self._w["mode_group"].addButton(btn)
            self._w[f"mode_{key}"] = btn
            row.addWidget(btn)
        row.addStretch(1)
        root.addLayout(row)

        # 底色
        row = QHBoxLayout()
        row.addWidget(QLabel("底色"))
        row.addStretch(1)
        self._w["bg_color_btn"] = self._color_button(
            self._cfg.get("bg_color", "#1c1c1e"), lambda c: self._touch(bg_color=c)
        )
        row.addWidget(self._w["bg_color_btn"])
        root.addLayout(row)

        # 底色不透明度
        self._w["bg_opacity"] = self._slider_row(
            root, "不透明度", 0, 100, self._cfg.get("bg_opacity", 80),
            lambda v: self._touch(bg_opacity=v), suffix="%",
        )

        # 图片
        row = QHBoxLayout()
        row.addWidget(QLabel("背景图"))
        self._w["bg_image_edit"] = QLineEdit(self._cfg.get("bg_image", ""))
        self._w["bg_image_edit"].setReadOnly(True)
        self._w["bg_image_edit"].setPlaceholderText("未选择")
        row.addWidget(self._w["bg_image_edit"], 1)
        pick = QPushButton("选择")
        pick.clicked.connect(self._pick_bg_image)
        row.addWidget(pick)
        self._w["bg_image_pick"] = pick
        root.addLayout(row)

        self._w["text_shadow"] = QCheckBox("文字衬底（全透明时垫一层极淡的底）")
        self._w["text_shadow"].setChecked(bool(self._cfg.get("text_shadow", True)))
        self._w["text_shadow"].toggled.connect(lambda v: self._touch(text_shadow=v))
        root.addWidget(self._w["text_shadow"])

        root.addWidget(_divider())

    # ------------------------------------------------------------- 文字分组
    def _build_typography(self, root: QVBoxLayout) -> None:
        root.addWidget(_section("文字"))

        row = QHBoxLayout()
        row.addWidget(QLabel("字体"))
        self._w["font_family"] = QComboBox()
        self._w["font_family"].setMinimumWidth(180)
        self._reload_fonts()
        self._w["font_family"].currentTextChanged.connect(
            lambda t: self._touch(font_family=t)
        )
        row.addWidget(self._w["font_family"], 1)
        load_btn = QPushButton("加载字体文件")
        load_btn.clicked.connect(self._load_font_files)
        row.addWidget(load_btn)
        root.addLayout(row)

        self._w["font_size"] = self._slider_row(
            root, "字号", 10, 40, self._cfg.get("font_size", 17),
            lambda v: self._touch(font_size=v), suffix="px",
        )
        self._w["line_height"] = self._slider_row(
            root, "行高", 120, 260, self._cfg.get("line_height", 185),
            lambda v: self._touch(line_height=v), suffix="%",
        )
        self._w["letter_spacing"] = self._slider_row(
            root, "字间距", -2, 8, self._cfg.get("letter_spacing", 0),
            lambda v: self._touch(letter_spacing=v), suffix="px",
        )
        self._w["paragraph_spacing"] = self._slider_row(
            root, "段间距", 0, 36, self._cfg.get("paragraph_spacing", 12),
            lambda v: self._touch(paragraph_spacing=v), suffix="px",
        )

        row = QHBoxLayout()
        row.addWidget(QLabel("字色"))
        row.addStretch(1)
        self._w["text_color_btn"] = self._color_button(
            self._cfg.get("text_color", "#1d1d1f"), lambda c: self._touch(text_color=c)
        )
        row.addWidget(self._w["text_color_btn"])
        root.addLayout(row)

        self._w["text_opacity"] = self._slider_row(
            root, "字不透明度", 10, 100, self._cfg.get("text_opacity", 100),
            lambda v: self._touch(text_opacity=v), suffix="%",
        )

        row = QHBoxLayout()
        self._w["font_bold"] = QCheckBox("加粗")
        self._w["font_bold"].setChecked(bool(self._cfg.get("font_bold", False)))
        self._w["font_bold"].toggled.connect(lambda v: self._touch(font_bold=v))
        row.addWidget(self._w["font_bold"])

        self._w["first_line_indent"] = QCheckBox("首行缩进两字")
        self._w["first_line_indent"].setChecked(bool(self._cfg.get("first_line_indent", False)))
        self._w["first_line_indent"].toggled.connect(
            lambda v: self._touch(first_line_indent=v)
        )
        row.addWidget(self._w["first_line_indent"])
        row.addStretch(1)
        root.addLayout(row)

        root.addWidget(_divider())

    # ------------------------------------------------------------- 窗口分组
    def _build_window(self, root: QVBoxLayout) -> None:
        root.addWidget(_section("窗口"))

        self._w["window_opacity"] = self._slider_row(
            root, "窗口不透明度", 20, 100, self._cfg.get("window_opacity", 100),
            lambda v: self._touch(window_opacity=v), suffix="%",
        )
        self._w["idle_opacity"] = self._slider_row(
            root, "鼠标移开后", 0, 100, self._cfg.get("idle_opacity", 0),
            lambda v: self._touch(idle_opacity=v), suffix="%",
        )
        self._w["idle_delay"] = self._slider_row(
            root, "移开后延迟", 0, 3000, self._cfg.get("idle_delay_ms", 0),
            lambda v: self._touch(idle_delay_ms=v), suffix="ms", step=50,
        )
        self._w["preload_chapters"] = self._slider_row(
            root, "连续阅读预加载", 1, 5, self._cfg.get("preload_chapters", 2),
            lambda v: self._touch(preload_chapters=v), suffix=" 章",
        )

        row = QHBoxLayout()
        self._w["always_on_top"] = QCheckBox("窗口置顶")
        self._w["always_on_top"].setChecked(bool(self._cfg.get("always_on_top", True)))
        self._w["always_on_top"].toggled.connect(lambda v: self._touch(always_on_top=v))
        row.addWidget(self._w["always_on_top"])
        row.addStretch(1)
        root.addLayout(row)

        # 可见性开关：标题栏 / 边框是"能看见窗口"的线索，托盘是"能确认程序在跑"的线索
        row = QHBoxLayout()
        for key, text in (
            ("show_titlebar", "显示标题栏"),
            ("show_border", "显示窗口边框"),
        ):
            box = QCheckBox(text)
            box.setChecked(bool(self._cfg.get(key, True)))
            box.toggled.connect(lambda v, k=key: self._touch(**{k: v}))
            self._w[key] = box
            row.addWidget(box)
        row.addStretch(1)
        root.addLayout(row)

        row = QHBoxLayout()
        for key, text in (
            ("show_tray", "显示托盘图标"),
            ("notify_on_start", "启动时提示"),
        ):
            box = QCheckBox(text)
            box.setChecked(bool(self._cfg.get(key, True)))
            box.toggled.connect(lambda v, k=key: self._touch(**{k: v}))
            self._w[key] = box
            row.addWidget(box)
        row.addStretch(1)
        root.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("老板键"))
        self._w["hotkey"] = QLineEdit(self._cfg.get("hotkey", "ctrl+shift+x"))
        self._w["hotkey"].setPlaceholderText("例如 ctrl+shift+x")
        self._w["hotkey"].editingFinished.connect(
            lambda: self._touch(hotkey=self._w["hotkey"].text().strip() or "ctrl+shift+x")
        )
        row.addWidget(self._w["hotkey"], 1)
        root.addLayout(row)

    # ------------------------------------------------------------- 控件工厂
    def _slider_row(self, root, label, minimum, maximum, value, on_change,
                    suffix="", step=1) -> QSlider:
        row = QHBoxLayout()
        row.addWidget(QLabel(label))

        tag = QLabel(f"{value}{suffix}")
        tag.setObjectName("ValueTag")
        tag.setMinimumWidth(56)
        tag.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setSingleStep(step)
        slider.setPageStep(max(step, (maximum - minimum) // 10))
        slider.setValue(int(value))
        slider.valueChanged.connect(
            lambda v, t=tag, s=suffix, cb=on_change: (t.setText(f"{v}{s}"), cb(v))
        )
        slider.setMinimumWidth(150)

        row.addStretch(1)
        row.addWidget(tag)
        row.addWidget(slider, 2)
        root.addLayout(row)
        return slider

    def _color_button(self, value: str, on_change) -> QPushButton:
        btn = QPushButton()
        btn.setFixedSize(54, 26)
        btn.setProperty("color_value", value)
        self._paint_color_button(btn, value)

        def choose():
            current = QColor(btn.property("color_value") or "#000000")
            picked = QColorDialog.getColor(current, self, "选择颜色")
            if picked.isValid():
                hex_value = picked.name()
                btn.setProperty("color_value", hex_value)
                self._paint_color_button(btn, hex_value)
                on_change(hex_value)

        btn.clicked.connect(choose)
        return btn

    @staticmethod
    def _paint_color_button(btn: QPushButton, value: str) -> None:
        btn.setStyleSheet(
            f"QPushButton {{ background:{value}; border:1px solid rgba(0,0,0,45);"
            f" border-radius:7px; }}"
        )
        btn.setText("")

    # ------------------------------------------------------------------ 交互
    def _touch(self, **changes) -> None:
        if self._updating:
            return
        self._cfg.update(changes)
        self._update_mode_states()
        self.config_changed.emit(copy.deepcopy(self._cfg))

    def _update_mode_states(self) -> None:
        """按背景模式灰掉不相关的控件。"""
        mode = self._cfg.get("bg_mode", "transparent")
        color_enabled = mode in ("color", "image")
        self._w["bg_color_btn"].setEnabled(color_enabled)
        self._w["bg_opacity"].setEnabled(color_enabled)
        self._w["bg_image_edit"].setEnabled(mode == "image")
        self._w["bg_image_pick"].setEnabled(mode == "image")
        self._w["text_shadow"].setEnabled(True)

    def _pick_bg_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择背景图", "", "图片 (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if not path:
            return
        self._cfg["bg_image"] = path
        self._w["bg_image_edit"].setText(path)
        self._touch(bg_mode="image")

    def _reload_fonts(self) -> None:
        combo = self._w["font_family"]
        self._updating = True
        combo.clear()

        external = self._fonts.external_families()
        if external:
            combo.addItem("— 已加载字体 —")
            combo.model().item(combo.count() - 1).setEnabled(False)
            for fam in external:
                combo.addItem(fam)
            combo.insertSeparator(combo.count())

        for fam in self._fonts.available_families():
            combo.addItem(fam)

        target = self._cfg.get("font_family", "")
        idx = combo.findText(target)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        self._updating = False

    def _load_font_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "加载字体文件", "", FONT_FILTER)
        if not paths:
            return

        added: list[str] = []
        for path in paths:
            families = self._fonts.load_file(path)
            added.extend(families)

        if not added:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "加载失败",
                "这些文件没有可用的字体，或不是受支持的 .ttf/.otf 字体。",
            )
            return

        self._reload_fonts()
        combo = self._w["font_family"]
        idx = combo.findText(added[0])
        if idx >= 0:
            combo.setCurrentIndex(idx)

        self.fonts_changed.emit(self._fonts.files)
        self._touch(font_family=added[0])

    def _reset_defaults(self) -> None:
        keep = {"window_x", "window_y", "window_width", "window_height",
                "recent_files", "font_files"}
        self._cfg.update({k: v for k, v in DEFAULTS.items() if k not in keep})
        self._updating = True
        self._w["font_size"].setValue(self._cfg["font_size"])
        self._w["line_height"].setValue(self._cfg["line_height"])
        self._w["letter_spacing"].setValue(self._cfg["letter_spacing"])
        self._w["paragraph_spacing"].setValue(self._cfg["paragraph_spacing"])
        self._w["text_opacity"].setValue(self._cfg["text_opacity"])
        self._w["bg_opacity"].setValue(self._cfg["bg_opacity"])
        self._w["window_opacity"].setValue(self._cfg["window_opacity"])
        self._w["idle_opacity"].setValue(self._cfg["idle_opacity"])
        self._w["idle_delay"].setValue(self._cfg["idle_delay_ms"])
        self._w["preload_chapters"].setValue(self._cfg["preload_chapters"])
        self._w["font_bold"].setChecked(self._cfg["font_bold"])
        self._w["first_line_indent"].setChecked(self._cfg["first_line_indent"])
        self._w["always_on_top"].setChecked(self._cfg["always_on_top"])
        self._w["text_shadow"].setChecked(self._cfg["text_shadow"])
        for key in ("show_titlebar", "show_tray", "show_border", "notify_on_start"):
            self._w[key].setChecked(self._cfg[key])
        self._w["hotkey"].setText(self._cfg["hotkey"])
        for key, btn in (
            ("transparent", self._w["mode_transparent"]),
            ("color", self._w["mode_color"]),
            ("image", self._w["mode_image"]),
        ):
            btn.setChecked(self._cfg["bg_mode"] == key)
        self._updating = False

        self._paint_color_button(self._w["bg_color_btn"], self._cfg["bg_color"])
        self._paint_color_button(self._w["text_color_btn"], self._cfg["text_color"])
        self._update_mode_states()
        self.config_changed.emit(copy.deepcopy(self._cfg))

    # ------------------------------------------------------------------ 拖动
    def showEvent(self, event):
        super().showEvent(event)
        self._update_mode_states()
        # 居中到父窗口
        if self.parent() is not None:
            parent = self.parent()
            self.move(
                parent.x() + (parent.width() - self.width()) // 2,
                parent.y() + max(20, (parent.height() - self.height()) // 2),
            )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)
