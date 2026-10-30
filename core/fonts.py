"""字体管理：系统字体枚举 + 外部 .ttf/.otf 加载。

Qt 的 QFontDatabase.addApplicationFont() 可以直接把字体文件注册进当前进程，
不需要做格式转换，也不需要装到系统里。
"""

from pathlib import Path

from PySide6.QtGui import QFontDatabase

# 这些是中文阅读体验较好的常见字体，按优先级排序；
# 只有系统里真实存在的才会出现在候选列表里。
PREFERRED_FAMILIES = [
    "PingFang SC",          # 苹方（装了的话最接近苹果观感）
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "微软雅黑",
    "HarmonyOS Sans SC",
    "Source Han Sans SC",
    "思源黑体",
    "Noto Sans CJK SC",
    "DengXian",
    "等线",
    "SimSun",
    "宋体",
    "SimHei",
    "黑体",
    "KaiTi",
    "楷体",
    "FangSong",
    "仿宋",
    "Segoe UI",
    "Georgia",
    "Times New Roman",
    "Consolas",
]

SUPPORTED_SUFFIXES = {".ttf", ".otf", ".ttc", ".otc"}
MAX_FONT_FILE_MB = 80  # 超大字体文件直接拒绝，避免误选


class FontManager:
    """进程级字体注册表。"""

    def __init__(self, font_files: list[str] | None = None):
        self._files: list[str] = []
        self._loaded: dict[str, list[str]] = {}   # 文件路径 -> 它提供的字体名
        if font_files:
            self.restore(font_files)

    # ------------------------------------------------------------------ 查询
    @staticmethod
    def system_families() -> list[str]:
        """系统已安装字体（含本进程注册进去的）。"""
        try:
            return sorted(QFontDatabase.families(), key=str.lower)
        except Exception:
            return []

    def available_families(self) -> list[str]:
        """候选字体列表：优先展示中文友好字体，其余按字母序附在后面。

        注意：某些平台插件（例如 offscreen）拿不到系统字体清单，
        此时直接退回常用字体名，避免下拉框是空的、用户无从选择。
        """
        installed = {f.lower(): f for f in self.system_families()}
        out: list[str] = []
        for fam in PREFERRED_FAMILIES:
            real = installed.get(fam.lower())
            if real and real not in out:
                out.append(real)
        for fam in self.system_families():
            if fam not in out:
                out.append(fam)
        if not out:
            out = list(PREFERRED_FAMILIES)
        return out

    def external_families(self) -> list[str]:
        """仅来自外部字体文件的名字。"""
        out: list[str] = []
        for fams in self._loaded.values():
            for f in fams:
                if f not in out:
                    out.append(f)
        return out

    @property
    def files(self) -> list[str]:
        return list(self._files)

    # ------------------------------------------------------------------ 加载
    def load_file(self, path: str) -> list[str]:
        """注册一个字体文件，返回它提供的字体名。失败返回空列表。"""
        p = Path(path)
        if not p.is_file():
            return []
        if p.suffix.lower() not in SUPPORTED_SUFFIXES:
            return []
        try:
            if p.stat().st_size > MAX_FONT_FILE_MB * 1024 * 1024:
                return []
        except OSError:
            return []

        key = str(p)
        if key in self._loaded:
            return self._loaded[key]

        try:
            font_id = QFontDatabase.addApplicationFont(key)
        except Exception:
            return []
        if font_id < 0:
            return []

        families = QFontDatabase.applicationFontFamilies(font_id) or []
        self._loaded[key] = list(families)
        if key not in self._files:
            self._files.append(key)
        return list(families)

    def restore(self, paths: list[str]) -> None:
        """启动时恢复上次加载过的外部字体。"""
        for path in paths:
            self.load_file(path)

    def remove_file(self, path: str) -> None:
        """从记录里移除（进程内已注册的字体无法卸载，重启后生效）。"""
        key = str(path)
        self._loaded.pop(key, None)
        if key in self._files:
            self._files.remove(key)

    # ------------------------------------------------------------------ 校验
    @staticmethod
    def resolve(family: str, fallback: str = "") -> str:
        """确保字体名在当前环境可用，否则回退。"""
        installed = {f.lower() for f in FontManager.system_families()}
        if family and family.lower() in installed:
            return family
        if fallback and fallback.lower() in installed:
            return fallback
        for fam in ("Microsoft YaHei UI", "Microsoft YaHei", "微软雅黑", "SimSun", "宋体"):
            if fam.lower() in installed:
                return fam
        return family or fallback
