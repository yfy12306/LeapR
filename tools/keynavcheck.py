# -*- coding: utf-8 -*-
"""LeapR 方向键验证（源码侧）。

覆盖三条真实按键路径：
  A. QTest.keyClick         —— Qt 内部事件
  B. PostMessage + 扩展位    —— 等价于笔记本的独立方向键（mods=NoModifier）
  C. PostMessage 无扩展位    —— 等价于外接键盘的小键盘方向键（mods=KeypadModifier）
  D. Ctrl+方向键            —— 必须放行，保留系统默认

注意：方向键是"扩展键"，PostMessage 的 lParam 必须带 0x01000000，
否则 Qt 会当成小键盘键并附加 KeypadModifier。
"""
import ctypes
import os
import shutil
import sys
import time
from ctypes import wintypes

ROOT = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

CFG = os.path.join(ROOT, "config")
BAK = os.path.join(ROOT, "config.__keybak")
if os.path.exists(BAK):
    shutil.rmtree(BAK)
shutil.copytree(CFG, BAK)

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from core.config import load_config
from core.fonts import FontManager
from ui.main_window import ReaderWindow

u32 = ctypes.windll.user32
u32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                             ctypes.c_size_t, ctypes.c_ssize_t]
u32.PostMessageW.restype = wintypes.BOOL
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
VK = {"down": (0x28, 0x50), "up": (0x26, 0x48), "right": (0x27, 0x4D), "left": (0x25, 0x4B)}
EXT = 1 << 24

results = []


def check(name, got, want, detail=""):
    ok = got == want
    results.append((name, ok))
    print("  %-46s %s   %s" % (name, "PASS" if ok else "FAIL", detail))
    return ok


def press(kind, extended=True, times=1, ctrl=False):
    h = u32.FindWindowW(None, "LeapR")
    vk, sc = VK[kind]
    lp = 1 | (sc << 16) | (EXT if extended else 0)
    for _ in range(times):
        if ctrl:
            u32.PostMessageW(h, WM_KEYDOWN, 0x11, 1 | (0x1D << 16))     # Ctrl down
        u32.PostMessageW(h, WM_KEYDOWN, vk, lp)
        u32.PostMessageW(h, WM_KEYUP, vk, lp | (1 << 30) | (1 << 31))
        if ctrl:
            u32.PostMessageW(h, WM_KEYUP, 0x11, (1 | (0x1D << 16)) | (1 << 30) | (1 << 31))
        time.sleep(0.08)


app = QApplication([])
cfg = load_config()
w = ReaderWindow(cfg, FontManager(cfg.get("font_files", [])))
w.show()
for _ in range(20):
    app.processEvents()
    time.sleep(0.02)

w.load_file(os.path.join(ROOT, "books", "长章书.txt"))
for _ in range(30):
    app.processEvents()
    time.sleep(0.02)

bar = w._browser.verticalScrollBar()
line = w._line_px()
two = int(round(line * 2))
print("章节数=%d  行高=%.2f px  2行=%.0f px  滚动范围 0..%d"
      % (w._reader.chapter_count, line, line * 2, bar.maximum()))
print()


def settle(n=30):
    for _ in range(n):
        app.processEvents()
        time.sleep(0.01)


print("A. QTest.keyClick（Qt 内部事件）")
bar.setValue(bar.maximum() // 2); settle()
v = bar.value(); QTest.keyClick(w, Qt.Key.Key_Down); settle()
check("↓ 位移 = 2 行", bar.value() - v, two)
v = bar.value(); QTest.keyClick(w, Qt.Key.Key_Up); settle()
check("↑ 位移 = -2 行", bar.value() - v, -two)

print()
print("B. PostMessage 带扩展位（= 笔记本独立方向键）")
bar.setValue(bar.maximum() // 2); settle()
v = bar.value(); press("down", extended=True); settle()
check("↓ 位移 = 2 行", bar.value() - v, two)
v = bar.value(); press("up", extended=True); settle()
check("↑ 位移 = -2 行", bar.value() - v, -two)

print()
print("C. PostMessage 无扩展位（= 外接键盘小键盘方向键，带 KeypadModifier）")
bar.setValue(bar.maximum() // 2); settle()
v = bar.value(); press("down", extended=False); settle()
check("↓ 位移 = 2 行（放宽条件后才过）", bar.value() - v, two)
v = bar.value(); press("up", extended=False); settle()
check("↑ 位移 = -2 行", bar.value() - v, -two)

print()
print("D. 带修饰键必须放行（用 QTest 带 modifier 测，PostMessage 伪造不了修饰键状态）")
bar.setValue(bar.maximum() // 2); settle()
v = bar.value()
QTest.keyClick(w, Qt.Key.Key_Down, Qt.KeyboardModifier.ControlModifier)
settle()
check("Ctrl+↓ 位移 = 0（未被吃掉）", bar.value() - v, 0)
v = bar.value()
QTest.keyClick(w, Qt.Key.Key_Down, Qt.KeyboardModifier.ShiftModifier)
settle()
check("Shift+↓ 位移 = 0（未被吃掉）", bar.value() - v, 0)
v = bar.value()
QTest.keyClick(w, Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier)
settle()
check("Alt+↓ 位移 = 0（未被吃掉）", bar.value() - v, 0)

print()
print("E. 左右键翻章")
bar.setValue(bar.maximum() // 2); settle()
c = w._chapter_index
press("right"); settle(40)
check("→ 章节 +1", w._chapter_index, c + 1, "%d -> %d" % (c, w._chapter_index))
c = w._chapter_index
press("left"); settle(40)
check("← 章节 -1", w._chapter_index, c - 1, "%d -> %d" % (c, w._chapter_index))

print()
print("F. 边界")
bar.setValue(0); settle()
press("up", times=4); settle()
check("顶部连按 ↑ 不越界", bar.value(), 0)
c = w._chapter_index
bar.setValue(bar.maximum()); settle()
press("down", times=60); settle()
check("底部连按 ↓ 能跨章前进", w._chapter_index > c, True,
      "章 %d -> %d" % (c, w._chapter_index))

w.close()
shutil.rmtree(CFG, ignore_errors=True)
shutil.move(BAK, CFG)

bad = [n for n, ok in results if not ok]
print()
print("=" * 68)
print("总计 %d 项，%s" % (len(results), "全部 PASS" if not bad else "FAIL: " + ", ".join(bad)))
sys.exit(1 if bad else 0)
