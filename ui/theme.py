"""视觉主题：设计令牌、控件样式、正文排版。

风格取向是苹果式的「内容优先、克制装饰」：
- 单一强调色，其余全是中性灰阶
- 大圆角、细描边、无重阴影
- 控件默认不出现，鼠标靠近才淡入
"""

from PySide6.QtGui import QColor, QTextBlockFormat, QTextCursor

# --------------------------------------------------------------------- 令牌
RADIUS_WINDOW = 14
RADIUS_CARD = 12
RADIUS_PILL = 8

ACCENT = "#0a84ff"          # 苹果系统蓝
DANGER = "#ff453a"

# 悬浮层（浮在文字之上，因此自带毛玻璃感的底色）
PANEL_BG = "rgba(28, 28, 32, 246)"
PANEL_BG_RGB = (28, 28, 32)      # 需要自绘时用的分量
PANEL_FG = "#f2f2f7"
PANEL_HOVER = "rgba(255, 255, 255, 38)"
PANEL_BORDER = "rgba(255, 255, 255, 28)"
PANEL_BORDER_RGB = (255, 255, 255)

# 设置面板（浅色卡片）
CARD_BG = "#ffffff"
CARD_FG = "#1d1d1f"
CARD_SUB = "#86868b"
CARD_LINE = "rgba(0, 0, 0, 22)"
FIELD_BG = "rgba(120, 120, 128, 24)"


def qcolor(value: str, alpha: int = 255) -> QColor:
    """把 #rrggbb 或 rgba() 解析成 QColor，并覆盖 alpha。"""
    c = QColor(value)
    if not c.isValid():
        c = QColor("#000000")
    c.setAlpha(max(0, min(255, alpha)))
    return c


def rgba_css(value: str, opacity_percent: int) -> str:
    """把颜色 + 0-100 的不透明度转成 CSS rgba()。"""
    c = qcolor(value)
    a = round(max(0, min(100, opacity_percent)) / 100 * 255)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {a})"


# --------------------------------------------------------------- 悬浮工具条
def menu_qss() -> str:
    """浅色卡片式菜单：托盘菜单、窗口右键菜单、「更多」菜单共用。"""
    return f"""
    QMenu {{
        background: {CARD_BG};
        border: 1px solid {CARD_LINE};
        border-radius: 10px;
        padding: 6px;
        font-size: 13px;
        color: {CARD_FG};
    }}
    QMenu::item {{
        padding: 7px 26px 7px 14px;
        border-radius: 6px;
    }}
    QMenu::item:selected {{
        background: {ACCENT};
        color: #ffffff;
    }}
    QMenu::separator {{
        height: 1px;
        background: {CARD_LINE};
        margin: 5px 8px;
    }}
    QMenu::item:disabled {{
        color: #b0b0b5;
    }}
    """


def toolbar_qss() -> str:
    return f"""
    QWidget#ToolBar {{
        background: {PANEL_BG};
        border: 1px solid {PANEL_BORDER};
        border-radius: {RADIUS_PILL}px;
    }}
    QWidget#ToolBar QPushButton {{
        background: transparent;
        border: none;
        border-radius: 6px;
        color: {PANEL_FG};
        font-size: 13px;
        padding: 5px 10px;
    }}
    QWidget#ToolBar QPushButton:hover {{
        background: {PANEL_HOVER};
    }}
    QWidget#ToolBar QPushButton:pressed {{
        background: rgba(255, 255, 255, 70);
    }}
    QWidget#ToolBar QLabel {{
        color: rgba(242, 242, 247, 190);
        font-size: 12px;
        padding: 0 6px;
    }}
    QWidget#ToolBar QLabel#TitleText {{
        color: rgba(242, 242, 247, 240);
        font-size: 12px;
        padding: 0 4px;
    }}
    QWidget#ToolBar QPushButton#CloseBtn:hover {{
        background: {DANGER};
        color: #ffffff;
    }}
    """


# ------------------------------------------------------------------ 目录抽屉
def drawer_qss() -> str:
    return f"""
    QWidget#Drawer {{
        background: {PANEL_BG};
        border: 1px solid {PANEL_BORDER};
        border-radius: {RADIUS_CARD}px;
    }}
    QWidget#Drawer QLabel#DrawerTitle {{
        color: rgba(242, 242, 247, 160);
        font-size: 12px;
        font-weight: 600;
        padding: 10px 14px 6px 14px;
    }}
    QWidget#Drawer QListWidget {{
        background: transparent;
        border: none;
        outline: none;
        color: {PANEL_FG};
        font-size: 13px;
        padding: 2px 6px 8px 6px;
    }}
    QWidget#Drawer QListWidget::item {{
        padding: 7px 10px;
        border-radius: 7px;
        margin: 1px 2px;
    }}
    QWidget#Drawer QListWidget::item:hover {{
        background: {PANEL_HOVER};
    }}
    QWidget#Drawer QListWidget::item:selected {{
        background: {ACCENT};
        color: #ffffff;
    }}
    QWidget#Drawer QLineEdit {{
        background: rgba(255, 255, 255, 26);
        border: none;
        border-radius: 7px;
        color: {PANEL_FG};
        padding: 6px 10px;
        margin: 4px 12px 6px 12px;
        font-size: 12px;
    }}
    QWidget#Drawer QLineEdit::placeholder {{
        color: rgba(242, 242, 247, 110);
    }}
    QWidget#Drawer QScrollBar:vertical {{
        background: transparent;
        width: 6px;
        margin: 6px 2px;
    }}
    QWidget#Drawer QScrollBar::handle:vertical {{
        background: rgba(255, 255, 255, 60);
        border-radius: 3px;
        min-height: 24px;
    }}
    QWidget#Drawer QScrollBar::add-line:vertical,
    QWidget#Drawer QScrollBar::sub-line:vertical,
    QWidget#Drawer QScrollBar::add-page:vertical,
    QWidget#Drawer QScrollBar::sub-page:vertical {{
        background: none; height: 0;
    }}
    """


# ------------------------------------------------------------------ 设置面板
def settings_qss() -> str:
    return f"""
    QDialog#Settings {{
        background: transparent;
    }}
    QFrame#SettingsCard {{
        background: {CARD_BG};
        border: 1px solid {CARD_LINE};
        border-radius: {RADIUS_CARD}px;
    }}
    QFrame#SettingsCard QWidget#SettingsBody {{
        background: transparent;
    }}
    QDialog#Settings QLabel {{
        color: {CARD_FG};
        font-size: 13px;
        background: transparent;
    }}
    QDialog#Settings QLabel#SectionTitle {{
        color: {CARD_SUB};
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.6px;
        padding: 14px 0 4px 0;
    }}
    QDialog#Settings QLabel#ValueTag {{
        color: {CARD_SUB};
        font-size: 12px;
    }}
    QDialog#Settings QPushButton {{
        background: {FIELD_BG};
        border: none;
        border-radius: {RADIUS_PILL}px;
        color: {CARD_FG};
        font-size: 13px;
        padding: 7px 14px;
    }}
    QDialog#Settings QPushButton:hover {{
        background: rgba(120, 120, 128, 40);
    }}
    QDialog#Settings QPushButton:checked {{
        background: {ACCENT};
        color: #ffffff;
    }}
    QDialog#Settings QPushButton:checked:hover {{
        background: #0a78e8;
    }}
    QDialog#Settings QPushButton#Primary {{
        background: {ACCENT};
        color: #ffffff;
    }}
    QDialog#Settings QPushButton#Primary:hover {{
        background: #0a78e8;
    }}
    QDialog#Settings QPushButton#Danger {{
        color: {DANGER};
    }}
    QDialog#Settings QComboBox, QDialog#Settings QLineEdit {{
        background: {FIELD_BG};
        border: none;
        border-radius: {RADIUS_PILL}px;
        color: {CARD_FG};
        padding: 7px 10px;
        font-size: 13px;
        min-height: 18px;
    }}
    QDialog#Settings QComboBox::drop-down {{
        border: none;
        width: 22px;
    }}
    QDialog#Settings QComboBox QAbstractItemView {{
        background: #ffffff;
        border: 1px solid {CARD_LINE};
        border-radius: 8px;
        outline: none;
        selection-background-color: {ACCENT};
        selection-color: #ffffff;
        padding: 4px;
    }}
    QDialog#Settings QSlider::groove:horizontal {{
        height: 4px;
        background: rgba(120, 120, 128, 45);
        border-radius: 2px;
    }}
    QDialog#Settings QSlider::sub-page:horizontal {{
        background: {ACCENT};
        border-radius: 2px;
    }}
    QDialog#Settings QSlider::handle:horizontal {{
        background: #ffffff;
        border: 1px solid rgba(0, 0, 0, 40);
        width: 14px;
        height: 14px;
        margin: -6px 0;
        border-radius: 8px;
    }}
    QDialog#Settings QCheckBox {{
        color: {CARD_FG};
        font-size: 13px;
        spacing: 8px;
    }}
    QDialog#Settings QCheckBox::indicator {{
        width: 16px; height: 16px;
        border-radius: 5px;
        border: 1px solid rgba(0, 0, 0, 60);
        background: #ffffff;
    }}
    QDialog#Settings QCheckBox::indicator:checked {{
        background: {ACCENT};
        border: 1px solid {ACCENT};
    }}
    QDialog#Settings QScrollArea {{
        background: transparent;
        border: none;
    }}
    QDialog#Settings QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}
    QDialog#Settings QScrollBar:vertical {{
        background: transparent; width: 6px; margin: 2px;
    }}
    QDialog#Settings QScrollBar::handle:vertical {{
        background: rgba(0, 0, 0, 40);
        border-radius: 3px;
        min-height: 28px;
    }}
    QDialog#Settings QScrollBar::add-line:vertical,
    QDialog#Settings QScrollBar::sub-line:vertical,
    QDialog#Settings QScrollBar::add-page:vertical,
    QDialog#Settings QScrollBar::sub-page:vertical {{
        background: none; height: 0;
    }}
    QDialog#Settings QFrame#Divider {{
        background: {CARD_LINE};
        max-height: 1px;
        border: none;
    }}
    """


# ------------------------------------------------------------------ 正文排版
def apply_document_format(browser, cfg: dict) -> None:
    """对已加载的文档逐段施加格式。

    Qt 的富文本对 CSS 的 line-height / text-indent 支持不稳，用 QTextBlockFormat
    设置才可靠。标题（headingLevel > 0）跳过——它保留 HTML 里给的边距，
    也不会被套上首行缩进。
    """
    doc = browser.document()
    cursor = QTextCursor(doc)
    cursor.beginEditBlock()

    body_fmt = QTextBlockFormat()
    try:
        body_fmt.setLineHeight(
            max(100, int(cfg.get("line_height", 185))),
            QTextBlockFormat.LineHeightTypes.ProportionalHeight.value,
        )
    except Exception:
        pass

    body_fmt.setBottomMargin(int(cfg.get("paragraph_spacing", 12)))
    body_fmt.setTextIndent(
        float(cfg.get("font_size", 17)) * 2 if cfg.get("first_line_indent") else 0
    )

    block = doc.begin()
    while block.isValid():
        if block.blockFormat().headingLevel() == 0:
            QTextCursor(block).setBlockFormat(body_fmt)
        block = block.next()

    cursor.endEditBlock()


def build_range_html(cfg: dict, chapters: list) -> str:
    """把连续若干章拼成一个 HTML 文档，用于无缝滚动阅读。

    每章都生成一个 <h2>：一是视觉上把章节分开，二是渲染完成后可以靠
    headingLevel 把正文 block 归回各自的章节（见 main_window._tag_chapter_blocks）。
    不要靠"数 <p> 标签"来推算 block 序号——Qt 排版时会插入额外 block，对不上。
    """
    size = int(cfg.get("font_size", 17))
    color = qcolor(
        cfg.get("text_color", "#1d1d1f"),
        round(cfg.get("text_opacity", 100) / 100 * 255),
    )
    family = cfg.get("font_family", "Microsoft YaHei UI")
    weight = "600" if cfg.get("font_bold") else "400"
    spacing = int(cfg.get("letter_spacing", 0))

    body_style = (
        f"font-family:'{family}';"
        f"font-size:{size}px;"
        f"font-weight:{weight};"
        f"color:rgba({color.red()},{color.green()},{color.blue()},{color.alpha()});"
        f"letter-spacing:{spacing}px;"
    )

    parts = [f'<div style="{body_style}">']
    for i, chapter in enumerate(chapters):
        # 章与章之间留出足够空白，滚动时读起来仍然是一篇连贯的文
        gap = int(size * 2.6) if i > 0 else 0
        title_size = size + 4
        label = chapter.title or "&nbsp;"
        parts.append(
            f'<h2 style="font-size:{title_size}px;font-weight:600;'
            f'margin-top:{gap}px;margin-bottom:{size}px;">'
            f"{label}</h2>"
        )
        parts.append(chapter.content)
    parts.append("</div>")
    return "".join(parts)
