"""阅读进度与最近书目管理。"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class ReadingProgress:
    """某本书的阅读进度。"""

    file_path: str
    chapter_index: int
    scroll_position: int
    timestamp: str
    scroll_ratio: float = 0.0   # 章节内滚动百分比，换窗口尺寸后仍能定位


class BookmarkManager:
    """进度管理：落在 config/bookmarks.json。"""

    def __init__(self, config_dir: Path):
        self._file = Path(config_dir) / "bookmarks.json"
        self._items: dict[str, ReadingProgress] = {}
        self._load()

    # ------------------------------------------------------------------ 存取
    def _load(self) -> None:
        if not self._file.exists():
            return
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return
        if not isinstance(data, dict):
            return
        for key, value in data.items():
            if not isinstance(value, dict):
                continue
            try:
                self._items[key] = ReadingProgress(**value)
            except TypeError:
                # 兼容旧格式（缺 scroll_ratio）
                try:
                    self._items[key] = ReadingProgress(
                        file_path=value.get("file_path", key),
                        chapter_index=int(value.get("chapter_index", 0)),
                        scroll_position=int(value.get("scroll_position", 0)),
                        timestamp=value.get("timestamp", ""),
                    )
                except (TypeError, ValueError):
                    continue

    def _save(self) -> None:
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            payload = {k: asdict(v) for k, v in self._items.items()}
            self._file.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass

    # ------------------------------------------------------------------ 接口
    def save_progress(
        self,
        file_path: str,
        chapter_index: int,
        scroll_position: int,
        scroll_ratio: float = 0.0,
    ) -> None:
        self._items[file_path] = ReadingProgress(
            file_path=file_path,
            chapter_index=int(chapter_index),
            scroll_position=int(scroll_position),
            timestamp=datetime.now().isoformat(timespec="seconds"),
            scroll_ratio=float(scroll_ratio),
        )
        self._save()

    def get_progress(self, file_path: str) -> ReadingProgress | None:
        return self._items.get(file_path)

    def get_last_file(self) -> str | None:
        if not self._items:
            return None
        latest = max(self._items.values(), key=lambda p: p.timestamp)
        return latest.file_path if Path(latest.file_path).exists() else None

    def get_all_sorted(self) -> list[ReadingProgress]:
        return sorted(self._items.values(), key=lambda p: p.timestamp, reverse=True)

    def delete_progress(self, file_path: str) -> None:
        if file_path in self._items:
            del self._items[file_path]
            self._save()
