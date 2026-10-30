"""后台加载 TXT。

解析放到子线程：几 MB 的文本 + 正则分章会占用几百毫秒到几秒，
放在主线程会让窗口卡住、也来不及显示"正在加载"。
"""

from PySide6.QtCore import QThread, Signal

from core.reader_engine import ReaderEngine


class FileLoader(QThread):
    """读文件 + 分章，完成后把 ReaderEngine 交回主线程。"""

    loaded = Signal(object)     # ReaderEngine
    failed = Signal(str)

    def __init__(self, path: str, chars_per_page: int = 3000, parent=None):
        super().__init__(parent)
        self._path = path
        self._chars_per_page = chars_per_page

    def run(self) -> None:
        try:
            engine = ReaderEngine(chars_per_page=self._chars_per_page)
            engine.load_file(self._path)
        except Exception as exc:                      # noqa: BLE001
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.loaded.emit(engine)
