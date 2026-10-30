# -*- coding: utf-8 -*-
"""验证打包后的 exe：方向键是否真的生效。

用 PostMessage 发真实 WM_KEYDOWN。注意方向键是**扩展键**，lParam 必须带
0x01000000，否则 Qt 会当作小键盘方向键并附加 KeypadModifier。
另外 lParam 是 LONG_PTR，不设 argtypes 的话 0xC0xxxxxx 会 OverflowError。

判定方式：发 ↓ 后等 auto_save(3s) 落盘，看 bookmarks 的 scroll_position 是否前移；
再发 ↑ 回到原位。测完结束进程、还原进度、重新启动，保证位置不偏。
"""
import ctypes
import json
import os
import shutil
import subprocess
import time
from ctypes import wintypes

ROOT = str(__import__("pathlib").Path(__file__).resolve().parent.parent)
EXE = os.path.join(ROOT, "dist", "LeapR", "LeapR.exe")
BM = os.path.join(ROOT, "dist", "LeapR", "config", "bookmarks.json")
BAK = BM + ".testbak"

u32 = ctypes.windll.user32
u32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                             ctypes.c_size_t, ctypes.c_ssize_t]
u32.PostMessageW.restype = wintypes.BOOL
WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
EXT = 1 << 24
KEY = {"down": (0x28, 0x50), "up": (0x26, 0x48), "right": (0x27, 0x4D), "left": (0x25, 0x4B)}

results = []


def check(name, ok, detail=""):
    results.append((name, ok))
    print("  %-34s %s   %s" % (name, "PASS" if ok else "FAIL", detail))


def hwnd():
    return u32.FindWindowW(None, "LeapR")


def procs():
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq LeapR.exe", "/NH"],
                       capture_output=True)
    return r.stdout.decode("gbk", "replace").count("LeapR.exe")


def kill_all():
    subprocess.run(["taskkill", "/IM", "LeapR.exe", "/F"], capture_output=True)
    for _ in range(30):
        if procs() == 0:
            return
        time.sleep(0.5)


def press(kind, times, gap=0.12):
    h = hwnd()
    vk, sc = KEY[kind]
    lp = 1 | (sc << 16) | EXT
    for _ in range(times):
        u32.PostMessageW(h, WM_KEYDOWN, vk, lp)
        u32.PostMessageW(h, WM_KEYUP, vk, lp | (1 << 30) | (1 << 31))
        time.sleep(gap)


def state():
    try:
        with open(BM, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        return None, None, None
    b = max(d.values(), key=lambda v: v.get("timestamp", ""))
    return os.path.basename(b["file_path"]), b.get("scroll_position"), b.get("chapter_index")


kill_all()
time.sleep(2)
shutil.copy2(BM, BAK)
print("基线:", state())

print("--- 启动打包版 ---")
t0 = time.time()
os.startfile(EXE)
while time.time() - t0 < 40 and not hwnd():
    time.sleep(0.1)
print("  窗口出现 %.2fs" % (time.time() - t0))
time.sleep(8)
base = state()
print("  加载后:", base)

print("--- 发 6 次 ↓ ---")
press("down", 6)
time.sleep(6)
down = state()
delta_down = (down[1] or 0) - (base[1] or 0)
print("  ↓ 后:", down)
check("↓ 使 scroll_position 前移", delta_down > 0, "变化 %+d" % delta_down)

print("--- 发 6 次 ↑ ---")
press("up", 6)
time.sleep(6)
up = state()
delta_up = (up[1] or 0) - (down[1] or 0)
print("  ↑ 后:", up)
check("↑ 使 scroll_position 回退", delta_up < 0, "变化 %+d" % delta_up)

print("--- 发 1 次 → 翻下一章 ---")
c0 = (up[2] or 0)
press("right", 1)
time.sleep(6)
r1 = state()
print("  → 后:", r1)
# 注意：bookmarks 里的 chapter_index 按"视口顶部"算（_current_position:1198），
# 内存里的 _chapter_index 按"视口中心"算（_on_scroll:1217），两者可能差 1，
# 所以这里判定"前进"而不是严格 +1；严格 +1 已在源码侧 QTest 用例中验证。
check("→ 章节前移", (r1[2] or 0) > c0, "章 %s -> %s" % (c0, r1[2]))

print("--- 发 1 次 ← 回上一章 ---")
c1 = (r1[2] or 0)
press("left", 1)
time.sleep(6)
l1 = state()
print("  ← 后:", l1)
check("← 章节后退", (l1[2] or 0) < c1, "章 %s -> %s" % (c1, l1[2]))

print("--- 收尾：还原进度并重启 ---")
kill_all()
time.sleep(2)
shutil.copy2(BAK, BM)
os.remove(BAK)
print("  已还原:", state())
os.startfile(EXE)
time.sleep(1.5)
check("重启成功", procs() >= 1, "进程数 %d" % procs())

bad = [n for n, ok in results if not ok]
print()
print("总计 %d 项，%s" % (len(results), "全部 PASS" if not bad else "FAIL: " + ", ".join(bad)))
