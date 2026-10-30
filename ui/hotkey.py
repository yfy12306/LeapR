"""全局热键（老板键）。

基于 pynput 的全局键盘监听，改造自 fish_read_windows/ui/hotkey_manager.py。
原实现在长按组合键时会重复触发，这里用 _fired 标志做了去重：
一次组合只发一次信号，直到所有目标键松手才复位。
"""

from pynput import keyboard
from PySide6.QtCore import QObject, Signal


class HotkeyManager(QObject):
    """监听一个组合键，按下时发 triggered 信号。"""

    triggered = Signal()

    def __init__(self, combo: str = "ctrl+shift+x", parent: QObject | None = None):
        super().__init__(parent)
        self._combo = combo
        self._listener: keyboard.Listener | None = None
        self._pressed: set = set()
        self._modifiers: set = set()
        self._keys: set = set()
        self._fired = False

    # ------------------------------------------------------------------ 解析
    def _parse(self, combo: str) -> tuple[set, set]:
        """把 'ctrl+shift+x' 拆成 (修饰键集合, 普通键集合)。"""
        modifiers: set = set()
        keys: set = set()

        for part in combo.lower().split("+"):
            part = part.strip()
            if not part:
                continue
            if part == "ctrl":
                for name in ("ctrl_l", "ctrl_r", "ctrl"):
                    if hasattr(keyboard.Key, name):
                        modifiers.add(getattr(keyboard.Key, name))
            elif part == "shift":
                for name in ("shift_l", "shift_r", "shift"):
                    if hasattr(keyboard.Key, name):
                        modifiers.add(getattr(keyboard.Key, name))
            elif part == "alt":
                for name in ("alt_l", "alt_r", "alt", "alt_gr"):
                    if hasattr(keyboard.Key, name):
                        modifiers.add(getattr(keyboard.Key, name))
            elif part == "win":
                for name in ("cmd_l", "cmd_r", "cmd"):
                    if hasattr(keyboard.Key, name):
                        modifiers.add(getattr(keyboard.Key, name))
            elif len(part) == 1:
                keys.add(keyboard.KeyCode.from_char(part))
            elif hasattr(keyboard.Key, part):
                keys.add(getattr(keyboard.Key, part))
            else:
                keys.add(keyboard.KeyCode.from_char(part))

        return modifiers, keys

    # ------------------------------------------------------------------ 事件
    @staticmethod
    def _char_of(key) -> str | None:
        """取按键字符。Ctrl 组合下 pynput 给的是控制字符（\x01-\x1a），需要还原。"""
        if isinstance(key, keyboard.KeyCode) and key.char:
            ch = key.char
            if len(ch) == 1 and ord(ch) < 27:
                return chr(ord(ch) + ord("a") - 1)
            return ch
        return None

    def _on_press(self, key) -> None:
        self._pressed.add(key)

        # 修饰键尚未按下时不需要判定
        if not any(k in self._pressed for k in self._modifiers):
            return

        for target in self._keys:
            hit = target in self._pressed
            if not hit:
                # Ctrl+X 在 pynput 里是控制字符，单独比对
                ctrl_char = self._char_of(key)
                if ctrl_char and isinstance(target, keyboard.KeyCode) and target.char == ctrl_char:
                    hit = True
            if not hit:
                return

        if not self._fired:
            self._fired = True
            self.triggered.emit()

    def _on_release(self, key) -> None:
        self._pressed.discard(key)
        # 组合键里任意一个松手，就允许下次再触发
        if self._fired and not (self._keys and self._keys.issubset(self._pressed)):
            self._fired = False

    # ------------------------------------------------------------------ 生命周期
    def start(self) -> None:
        if self._listener is not None:
            return
        self._modifiers, self._keys = self._parse(self._combo)
        if not self._keys:
            return
        try:
            self._listener = keyboard.Listener(
                on_press=self._on_press, on_release=self._on_release
            )
            self._listener.daemon = True
            self._listener.start()
        except Exception:
            self._listener = None

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
        self._pressed.clear()
        self._fired = False

    def update(self, combo: str) -> None:
        self.stop()
        self._combo = combo
        self.start()
