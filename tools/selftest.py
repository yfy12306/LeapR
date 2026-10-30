"""自测脚本：分章、编码识别、无标题分页、字体枚举。

用法： .venv\\Scripts\\python.exe tools\\selftest.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.reader_engine import ReaderEngine  # noqa: E402

BOOKS = ROOT / "books"
PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(("  [OK]   " if ok else "  [FAIL] ") + name + ("  " + detail if detail else ""))


# ---------------------------------------------------------------- 测试素材
def make_fixtures() -> None:
    BOOKS.mkdir(parents=True, exist_ok=True)

    plain = BOOKS / "无章节片段.txt"
    if not plain.exists():
        paras = []
        for i in range(1, 121):
            paras.append(f"这是第{i}段没有章节标题的正文，用来验证在没有章节标记时按字数自动分页。"
                         f"管道里的水流过一段又一段，句子也跟着往前走。")
        plain.write_text("\n\n".join(paras), encoding="utf-8")

    gbk = BOOKS / "编码测试_GBK.txt"
    if not gbk.exists():
        text = "第一章 春汛\n\n" + "临江的春天来得早。\n\n" * 30 \
               + "第二章 秋收\n\n" + "稻子黄的时候，风里都是甜的。\n\n" * 30
        gbk.write_bytes(text.encode("gbk"))


# ---------------------------------------------------------------- 1 分章
def test_chapters() -> None:
    print("\n[1] 分章（有章节标题）")
    path = BOOKS / "长夜书店.txt"
    if not path.exists():
        check("找到长夜书店.txt", False, str(path))
        return
    engine = ReaderEngine()
    chapters = engine.load_file(str(path))
    check("章节数 >= 8", len(chapters) >= 8, f"实际 {len(chapters)} 章")
    check("编码识别为 utf-8 系", "utf" in engine.encoding.lower(), engine.encoding)
    titles = [c.title for c in chapters]
    print("      章节：", " | ".join(titles))
    check("含『第一章 打烊之后』",
          any("打烊之后" in t for t in titles))
    check("含『第八章』", any("第八章" in t for t in titles))
    check("每章正文非空", all(c.char_count > 0 for c in chapters))
    check("总字数 > 3000", engine.total_chars > 3000, f"{engine.total_chars} 字")


# ---------------------------------------------------------------- 2 分页
def test_pagination() -> None:
    print("\n[2] 分页（无章节标题）")
    engine = ReaderEngine(chars_per_page=3000)
    chapters = engine.load_file(str(BOOKS / "无章节片段.txt"))
    check("自动分成了多页", len(chapters) > 1, f"{len(chapters)} 页")
    check("页标题形如『片段 N』", all("片段" in c.title for c in chapters),
          str(chapters[0].title))
    sizes = [c.char_count for c in chapters]
    full_pages = sizes[:-1]      # 末页是余数，天然会短
    check("除末页外每页都达到阈值", bool(full_pages) and all(s >= 2000 for s in full_pages),
          f"页字数 {sizes}")


# ---------------------------------------------------------------- 3 编码
def test_encoding() -> None:
    print("\n[3] 编码识别（GBK 文件）")
    engine = ReaderEngine()
    chapters = engine.load_file(str(BOOKS / "编码测试_GBK.txt"))
    check("识别为 gb 系编码", "gb" in engine.encoding.lower(), engine.encoding)
    check("切出 2 章", len(chapters) == 2, f"{len(chapters)} 章")
    joined = engine.plain_text(chapters[0])
    check("中文未乱码", "临江的春天来得早" in joined)
    check("无替换符", "\ufffd" not in joined)


# ---------------------------------------------------------------- 4 字体
def test_fonts() -> None:
    print("\n[4] 字体枚举（需要 QApplication）")
    from PySide6.QtWidgets import QApplication

    from core.fonts import FontManager

    app = QApplication.instance() or QApplication(sys.argv)
    fm = FontManager()
    fams = fm.available_families()
    check("能列出系统字体", len(fams) > 5, f"{len(fams)} 款")
    print("      优先候选：", " | ".join(fams[:8]))

    # 找一个真实存在的 ttf/otf 验证外部加载
    candidates = list(Path(r"C:\Windows\Fonts").glob("*.ttf"))[:60]
    loaded = []
    for f in candidates:
        got = fm.load_file(str(f))
        if got:
            loaded = got
            check("外部字体加载成功", True, f"{f.name} -> {got}")
            break
    if not loaded:
        check("外部字体加载成功", False, "C:\\Windows\\Fonts 未找到可加载的 ttf")

    if loaded:
        check("加载后出现在候选列表", loaded[0] in fm.available_families())


def main() -> int:
    print("=" * 62)
    print("LeapR · 自测")
    print("=" * 62)
    make_fixtures()
    test_chapters()
    test_pagination()
    test_encoding()
    test_fonts()

    print("\n" + "=" * 62)
    print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        print("失败项：")
        for name in FAIL:
            print("  - " + name)
    print("=" * 62)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
