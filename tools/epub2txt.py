# -*- coding: utf-8 -*-
"""epub -> txt：按 spine 顺序提取正文，输出成 LeapR 能直接分章的纯文本。

epub 本质是 zip：META-INF/container.xml 指向 OPF，OPF 的 spine 给出阅读顺序。
只依赖标准库（zipfile + html.parser），不需要额外依赖。

用法： python tools/epub2txt.py <input.epub> [output.txt]
"""
import html
import os
import re
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {
    "c": "urn:oasis:names:tc:opendocument:xmlns:container",
    "opf": "http://www.idpf.org/2007/opf",
}

BLOCK_TAGS = {
    "p", "div", "br", "section", "article", "blockquote", "li", "tr",
    "h1", "h2", "h3", "h4", "h5", "h6", "hr", "figure", "figcaption",
}
SKIP_TAGS = {"script", "style", "head", "title", "svg", "nav"}
HEADING_TAGS = ("h1", "h2", "h3")


class TextExtractor(HTMLParser):
    """把 XHTML 抽成纯文本：块级标签断行，跳过 script/style/head。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.heading: str | None = None
        self._skip = 0
        self._in_heading: str | None = None
        self._heading_buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self._skip += 1
            return
        if self._skip:
            return
        if tag in HEADING_TAGS and self.heading is None:
            self._in_heading = tag
            self._heading_buf = []
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        if tag in HEADING_TAGS and self._in_heading == tag:
            if self.heading is None:
                t = " ".join("".join(self._heading_buf).split())
                if t:
                    self.heading = t
            self._in_heading = None
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_heading is not None:
            self._heading_buf.append(data)
            return
        self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        lines = []
        for ln in raw.split("\n"):
            ln = ln.replace("\u3000", " ").replace("\xa0", " ")
            ln = re.sub(r"[ \t]+", " ", ln).strip()
            lines.append(ln)
        out = "\n".join(lines)
        out = re.sub(r"\n{3,}", "\n\n", out)
        return out.strip()


def read_opf(zf: zipfile.ZipFile) -> tuple[ET.Element, str]:
    root = ET.fromstring(zf.read("META-INF/container.xml"))
    rootfile = root.find(".//c:rootfile", NS)
    opf_path = rootfile.get("full-path")
    opf = ET.fromstring(zf.read(opf_path))
    return opf, opf_path


def spine_docs(zf: zipfile.ZipFile, opf: ET.Element, opf_path: str) -> list[str]:
    base = os.path.dirname(opf_path)
    manifest = {}
    for item in opf.iter():
        if item.tag.endswith("}item") or item.tag == "item":
            manifest[item.get("id")] = item.get("href")
    order = []
    for ref in opf.iter():
        if ref.tag.endswith("}itemref") or ref.tag == "itemref":
            href = manifest.get(ref.get("idref"))
            if href:
                order.append(os.path.normpath(os.path.join(base, href)).replace("\\", "/"))
    if not order:                                   # 没有 spine 就退回 manifest 顺序
        order = [os.path.normpath(os.path.join(base, h)).replace("\\", "/")
                 for h in manifest.values() if h.endswith((".xhtml", ".html", ".htm"))]
    return order


def convert(epub_path: str) -> tuple[str, list[dict]]:
    with zipfile.ZipFile(epub_path) as zf:
        opf, opf_path = read_opf(zf)
        docs = spine_docs(zf, opf, opf_path)

        title_el = opf.find(".//opf:metadata/opf:title", NS)
        book_title = (title_el.text or "").strip() if title_el is not None else ""

        chunks, info = [], []
        for path in docs:
            try:
                raw = zf.read(path)
            except KeyError:
                info.append({"path": path, "title": None, "chars": 0, "missing": True})
                continue
            text_raw = raw.decode("utf-8", "replace")
            ex = TextExtractor()
            ex.feed(text_raw)
            body = ex.text()
            info.append({"path": path, "title": ex.heading, "chars": len(body),
                         "missing": False})
            title = ex.heading or ""
            if body.strip():
                chunks.append((title, body))

    # 拼装：标题独立成行，章节之间空一行
    out_lines = []
    if book_title:
        out_lines += [book_title, ""]
    for title, body in chunks:
        if title:
            out_lines += [title, ""]
        out_lines += [body, ""]
    text = "\n".join(out_lines)
    text = re.sub(r"\n{4,}", "\n\n\n", text).strip() + "\n"
    return text, info


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else str(Path(src).with_suffix(".txt"))
    text, info = convert(src)
    Path(dst).write_text(text, encoding="utf-8")

    print("输入 :", src, "%.2f MB" % (os.path.getsize(src) / 1048576))
    print("输出 :", dst, "%.2f MB" % (os.path.getsize(dst) / 1048576))
    print("文档数: %d  总字数: %d" % (len(info), len(text)))
    print()
    print("前 15 个文档：")
    for i, d in enumerate(info[:15]):
        print("  %2d. %-46s 标题=%-24r %6d 字"
              % (i + 1, os.path.basename(d["path"]), d["title"], d["chars"]))
    miss = [d for d in info if d["missing"] or d["chars"] == 0]
    if miss:
        print("  （空/缺失文档 %d 个）" % len(miss))
    return 0


if __name__ == "__main__":
    sys.exit(main())
