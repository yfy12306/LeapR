"""验证分章正则的各种场景。

用法： .venv\\Scripts\\python.exe tools\\chaptercheck.py
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.reader_engine import ReaderEngine            # noqa: E402

PASS, FAIL = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(("  [OK]   " if ok else "  [FAIL] ") + name + ("  " + detail if detail else ""))


def split(text: str) -> list[str]:
    """把文本交给引擎解析，返回章节标题列表。"""
    fd, name = tempfile.mkstemp(suffix=".txt")
    os.close(fd)                      # 不关掉的话文件一直被占着，最后删不掉
    tmp = Path(name)
    try:
        tmp.write_text(text, encoding="utf-8")
        engine = ReaderEngine()
        engine.load_file(str(tmp))
        return [c.title for c in engine.chapters]
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def main() -> int:
    print("=== 场景 1：标准章节标题 ===")
    text = "".join(
        "第%d章 标题%d\n%s\n\n" % (i + 1, i + 1, "正文内容。" * 200) for i in range(5)
    )
    titles = split(text)
    check("切成 5 章", len(titles) == 5, str(len(titles)))
    check("标题正确", titles and titles[0].startswith("第1章"),
          titles[0] if titles else "(空)")

    print("\n=== 场景 2：正文里大量【技能名】【法宝名】 ===")
    print("   （这就是你遇到的情况：这些【】不该被当成章节）")
    body = "".join(
        "他抬手打出【技能%d】，又取出【法宝%d】，【灵草%d】随即炸开。\n%s\n\n"
        % (i, i, i, "这是正文内容。" * 60)
        for i in range(30)
    )
    text = "第一章 开端\n" + body + "第二章 续章\n" + body
    titles = split(text)
    check("只切成 2 章", len(titles) == 2,
          "%d 章: %s" % (len(titles), titles[:4]))

    print("\n=== 场景 3：【第一章】这种带序号的括号标题 ===")
    text = "".join("【第%d章】标题\n%s\n\n" % (i + 1, "正文。" * 200) for i in range(4))
    titles = split(text)
    check("仍能识别【第X章】", len(titles) == 4, str(len(titles)))

    print("\n=== 场景 4：独立成行的 楔子 / 序章 ===")
    text = "楔子\n" + "正文。" * 250 + "\n\n第一章 正式\n" + "正文。" * 250
    titles = split(text)
    check("识别「楔子」", len(titles) >= 2, str(titles[:3]))

    print("\n=== 场景 5：误切兜底（切得又碎又短）===")
    text = "".join("第%d章 x\n短句。\n\n" % (i + 1) for i in range(400))
    titles = split(text)
    check("退回按字数分页", bool(titles) and all(t.startswith("片段") for t in titles),
          "%d 项，首项 %s" % (len(titles), titles[0] if titles else "(空)"))

    print("\n=== 场景 6：原来的测试书不受影响 ===")
    book = ROOT / "books" / "长夜书店.txt"
    if book.exists():
        engine = ReaderEngine()
        engine.load_file(str(book))
        check("长夜书店仍是 8 章", engine.chapter_count == 8, str(engine.chapter_count))
    else:
        print("  (跳过，测试书不存在)")

    print("\n" + "=" * 56)
    print("通过 %d 项，失败 %d 项" % (len(PASS), len(FAIL)))
    for name in FAIL:
        print("  -", name)
    print("=" * 56)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
