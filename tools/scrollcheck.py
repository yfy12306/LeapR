"""验证连续阅读（章节无缝衔接）的核心逻辑。

用法： .venv\\Scripts\\python.exe tools\\scrollcheck.py
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt                              # noqa: E402
from PySide6.QtWidgets import QApplication                 # noqa: E402

from core.config import load_config                        # noqa: E402
from core.fonts import FontManager                         # noqa: E402
from ui.main_window import ReaderWindow                    # noqa: E402

BOOK = ROOT / "books" / "长夜书店.txt"
PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(("  [OK]   " if ok else "  [FAIL] ") + name + ("  " + detail if detail else ""))


def wait_loaded(win, path: str, timeout_s: float = 15.0) -> bool:
    """异步加载，等到章节出来为止。"""
    win.load_file(path)
    waited = 0.0
    while win._reader.chapter_count == 0 and waited < timeout_s:
        QApplication.processEvents()
        time.sleep(0.05)
        waited += 0.05
    return win._reader.chapter_count > 0


def main() -> int:
    app = QApplication(sys.argv)
    cfg = load_config()
    cfg["window_width"], cfg["window_height"] = 900, 560
    cfg["preload_chapters"] = 2

    win = ReaderWindow(cfg, FontManager())
    win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    win.resize(900, 560)
    win.show()
    app.processEvents()

    print("=== 加载 ===")
    ok = wait_loaded(win, str(BOOK))
    check("文件加载完成", ok)
    if not ok:
        print("!! 加载失败，后面不用测了")
        return 1

    total = win._reader.chapter_count
    print("  总章数:", total)
    check("章节数正确", total == 8, str(total))

    print("\n=== 初始渲染窗口 ===")
    print("  window = [%d, %d]" % (win._window_lo, win._window_hi))
    print("  已量出像素范围的章节:", sorted(win._chapter_y))
    check("窗口从第 1 章起、覆盖 3 章左右",
          win._window_lo == 0 and 2 <= win._window_hi <= 3,
          "[%d,%d]" % (win._window_lo, win._window_hi))
    check("量出了每章的像素范围", len(win._chapter_y) >= 3, str(sorted(win._chapter_y)))

    doc_h = win._browser.document().size().height()
    print("  文档高度: %.0f px" % doc_h)
    check("文档里确实是多章的连续内容", doc_h > 0 and len(win._chapter_y) >= 3)

    # 直接查渲染出来的文本顺序，比看截图可靠
    text = win._browser.toPlainText()
    pos_first = text.find("第一章 打烊之后")
    pos_second = text.find("第二章 第三个书架")
    check("章标题按顺序出现", 0 <= pos_first < pos_second,
          "第一章@%d 第二章@%d" % (pos_first, pos_second))

    seg_a = text.find("书店叫长夜")
    seg_b = text.find("他沿着书架走了一圈")
    check("章内段落顺序正确", 0 <= seg_a < seg_b, "段3@%d 段4@%d" % (seg_a, seg_b))
    check("文档里没有占位/加载提示",
          "加载下一章" not in text and "点击加载" not in text)

    print("\n=== 滚到下方边界：窗口应滑动且位置不跳变 ===")
    bar = win._browser.verticalScrollBar()
    before_idx, before_ratio = win._current_position()
    before_window = (win._window_lo, win._window_hi)
    bar.setValue(bar.maximum())
    app.processEvents()
    after_idx, after_ratio = win._current_position()
    after_window = (win._window_lo, win._window_hi)
    print("  window: %s -> %s" % (before_window, after_window))
    print("  位置: %d@%.2f -> %d@%.2f" % (before_idx, before_ratio, after_idx, after_ratio))
    check("窗口向后滑动（后边界推进）", after_window[1] > before_window[1],
          "%s -> %s" % (before_window, after_window))
    check("当前章前进了", after_idx > before_idx)
    check("滑动后没有跳回文档顶部", bar.value() > 0, str(bar.value()))
    check("滑动后不在文档最底部", bar.value() < bar.maximum(), "%d/%d" % (bar.value(), bar.maximum()))

    print("\n=== 目录跳章 ===")
    win._goto_chapter(7)
    app.processEvents()
    lay = win._browser.verticalScrollBar()
    print("  _chapter_y:", {k: (round(v[0]), round(v[1])) for k, v in sorted(win._chapter_y.items())})
    print("  bar = %d / %d, viewport_h = %d" % (lay.value(), lay.maximum(), win._browser.viewport().height()))
    print("  window = [%d, %d], cur = %d" % (win._window_lo, win._window_hi, win._chapter_index))
    check("当前章 = 第 8 章", win._chapter_index == 7, str(win._chapter_index))
    check("窗口覆盖第 8 章", win._window_lo <= 7 <= win._window_hi,
          "[%d,%d]" % (win._window_lo, win._window_hi))
    idx_at_top, _ = win._current_position()
    bar_last = win._browser.verticalScrollBar()
    at_bottom = bar_last.value() >= bar_last.maximum() - 5
    check("第 8 章可见（顶部落在它，或已滚到文档底）",
          idx_at_top == 7 or at_bottom,
          "top_ch=%d at_bottom=%s" % (idx_at_top, at_bottom))

    print("\n=== 跳回第 1 章 ===")
    win._goto_chapter(0)
    app.processEvents()
    check("当前章 = 第 1 章", win._chapter_index == 0, str(win._chapter_index))
    check("滚动条回到顶部附近", win._browser.verticalScrollBar().value() < 40,
          str(win._browser.verticalScrollBar().value()))

    print("\n=== 翻章按钮 ===")
    win._next_chapter()
    app.processEvents()
    check("下一章 -> 第 2 章", win._chapter_index == 1, str(win._chapter_index))
    win._prev_chapter()
    app.processEvents()
    check("上一章 -> 第 1 章", win._chapter_index == 0, str(win._chapter_index))

    # ---------------- 加载提示（需要一个够大的文件才看得到） ----------------
    print("\n=== 加载提示（大文件）===")
    big = ROOT / "books" / "大文件测试.txt"
    if not big.exists():
        src = (ROOT / "books" / "长夜书店.txt").read_text(encoding="utf-8")
        big.write_text(src * 400, encoding="utf-8")
        print("  已生成测试文件: %.1f MB" % (big.stat().st_size / 1024 / 1024))

    win.load_file(str(big))
    QApplication.processEvents()
    immediate = win._browser.toPlainText().strip()
    check("加载过程中显示『正在打开』提示", "正在打开" in immediate, immediate[:24])

    loaded = False
    waited = 0.0
    while waited < 40.0:
        QApplication.processEvents()
        time.sleep(0.05)
        waited += 0.05
        if win._reader.chapter_count > 8:
            loaded = True
            break
    check("大文件加载完成", loaded, "章数 %d" % win._reader.chapter_count)
    check("加载完成后提示被正文替换",
          "正在打开" not in win._browser.toPlainText())
    check("大文件切出大量章节", win._reader.chapter_count >= 3000,
          str(win._reader.chapter_count))
    check("渲染窗口仍然只有几章（内存可控）",
          (win._window_hi - win._window_lo) <= 6,
          "[%d, %d]" % (win._window_lo, win._window_hi))

    print("\n" + "=" * 56)
    print("通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
    for name in FAIL:
        print("  - " + name)
    print("=" * 56)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
