"""配置管理：默认值、读写、路径解析。"""

import json
import sys
from pathlib import Path


def base_path() -> Path:
    """exe 所在目录（打包后）或项目根目录（开发时）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_path(relative: str) -> Path:
    """只读资源（打包进 exe 的东西）。"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / relative
    return base_path() / relative


CONFIG_DIR = base_path() / "config"
CONFIG_PATH = CONFIG_DIR / "settings.json"

CONFIG_VERSION = 4

DEFAULTS: dict = {
    # ---------- 窗口 ----------
    "window_width": 760,
    "window_height": 480,
    "window_x": None,              # None = 启动时居中偏上
    "window_y": None,
    "window_opacity": 100,         # 鼠标在窗口内时的不透明度，0-100
    "idle_opacity": 0,             # 鼠标离开窗口后的不透明度。0 = 完全消失
    "idle_delay_ms": 0,            # 鼠标移开后多久生效。0 = 立即（不做动画）
    "always_on_top": True,
    "show_titlebar": True,         # 显示顶部标题栏（书名 + 拖动 + 按钮）
    "show_tray": True,             # 显示托盘图标
    "show_border": True,           # 显示窗口描边
    "notify_on_start": True,       # 启动时弹一次托盘气泡，明确告知程序已在运行

    # ---------- 背景 ----------
    "bg_mode": "transparent",      # transparent | color | image
    "bg_color": "#1c1c1e",
    "bg_opacity": 80,              # color / image 模式下底色的不透明度
    "bg_image": "",
    "text_shadow": False,          # 全透明模式下是否垫一层极淡的衬底，提升可读性

    # ---------- 文字 ----------
    "font_family": "Microsoft YaHei UI",
    "font_size": 17,
    "font_bold": False,
    "line_height": 185,            # 行高百分比
    "letter_spacing": 0,           # 字间距 px
    "text_color": "#1d1d1f",
    "text_opacity": 100,
    "first_line_indent": False,    # 首行缩进两字
    "paragraph_spacing": 12,       # 段间距 px
    "page_padding": 30,            # 正文四周留白 px
    "content_width": 640,          # 正文最大宽度（0 = 跟随窗口）

    # ---------- 行为 ----------
    "hotkey": "ctrl+shift+x",      # 老板键
    "auto_save_interval": 3000,
    "preload_chapters": 2,         # 连续阅读时前后各预加载几章（内存换流畅）
    "font_files": [],              # 用户加载的外部字体文件（.ttf/.otf）
    "recent_files": [],
    "chars_per_page": 3000,        # 无章节标题时按字数分页
}


def load_config() -> dict:
    """读配置，缺失的键用默认值补齐。"""
    data = {}
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            data = {}
    if not isinstance(data, dict):
        data = {}
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in data.items() if k in DEFAULTS})
    # 保留未知键，便于向后兼容
    for k, v in data.items():
        cfg.setdefault(k, v)

    # --- 迁移 ---
    # v3：idle 语义定为"鼠标离开后整个窗口淡出"，默认完全透明（0）。
    # v4：显示/隐藏改为瞬间生效（不再有淡入淡出动画），延迟默认 0。
    # 这两项语义都改过，老配置一律重置到新默认值。
    version = int(data.get("config_version", 1) or 1)
    if version < 3:
        cfg["idle_opacity"] = DEFAULTS["idle_opacity"]
    if version < 4:
        cfg["idle_delay_ms"] = DEFAULTS["idle_delay_ms"]
    cfg["config_version"] = CONFIG_VERSION

    return cfg


def save_config(config: dict) -> None:
    """写配置（静默失败，不打断阅读）。"""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def add_recent(config: dict, file_path: str, keep: int = 8) -> None:
    """把文件置顶到最近列表。"""
    recent = [p for p in config.get("recent_files", []) if p != file_path]
    recent.insert(0, file_path)
    config["recent_files"] = recent[:keep]
