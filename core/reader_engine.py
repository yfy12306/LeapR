"""TXT 解析引擎：编码识别 + 智能分章 + 无标记按字数分页。

改造自 fish_read_windows/core/reader_engine.py，去掉了 EPUB/MOBI/PDF 分支，
并补上「无章节标题时按字数分页」——原实现在这种情况下会把整本书塞进一章，
几 MB 的文本会让 QTextBrowser 卡住。
"""

import re
from dataclasses import dataclass
from pathlib import Path

import chardet


@dataclass
class Chapter:
    """章节数据。content 为已转义的 HTML 片段。"""

    index: int
    title: str
    content: str
    char_count: int = 0


class ReaderEngine:
    """TXT 解析引擎。"""

    # 章节标题识别。
    #
    # 只保留高置信度的写法。曾经有一条泛化的 `【[^】]{2,30}】`，本意是兼容
    # 「【第一章】」这类标题，结果把正文里的【技能名】【物品名】全切成了章节 ——
    # 一本正常的长篇能被切成两千多章，目录完全没法看。
    # 现在的原则是：宁可少切（退回按字数分页），也不要乱切。
    CHAPTER_PATTERN = re.compile(
        r"^[ \t\u3000]*(?:"
        # 第X章 / 第X节 / 第X回 / 第X卷 ……（中文数字或阿拉伯数字，允许中间带空格）
        r"第[ \t\u3000]*[零一二三四五六七八九十百千万两\d]+[ \t\u3000]*[章节回卷集部篇话]"
        # 卷X
        r"|卷[ \t\u3000]*[零一二三四五六七八九十百千万\d]+"
        # 【第X章】/【卷X】：括号里必须带序号才算
        r"|【[ \t\u3000]*(?:第[ \t\u3000]*[零一二三四五六七八九十百千万两\d]+"
        r"[ \t\u3000]*[章节回卷集部篇话]|卷[ \t\u3000]*[零一二三四五六七八九十百千万\d]+)"
        r"[ \t\u3000]*】"
        # 【楔子】【序章】这类固定叫法
        r"|【[ \t\u3000]*(?:楔子|序章|序言|前言|引子|尾声|终章|后记|番外)[^】\n]{0,10}】"
        # 独立成行的 楔子 / 序章 / 尾声 ……
        r"|(?:楔子|序章|序言|引子|尾声|终章|后记|番外)[ \t\u3000]*[^\n]{0,30}$"
        # Chapter 12 / Part 3
        r"|Chapter[ \t]+\d+"
        r"|Part[ \t]+\d+"
        r")"
        # 标题行本身不能太长，否则会把「第一章里提到……」这类正文句子切出来
        r"[^\n]{0,60}$",
        re.MULTILINE | re.IGNORECASE,
    )

    HTML_ESCAPE_TABLE = str.maketrans({"&": "&amp;", "<": "&lt;", ">": "&gt;"})

    MIN_CHAPTER_GAP = 10          # 两个章节标题之间最少间隔字数，防误切
    MIN_PREAMBLE_CHARS = 60       # 短于这个长度的前言视为书名/作者信息，不单独成章
    MIN_SENSIBLE_CHAPTERS = 300   # 章节数超过这个量就检查平均章长
    MIN_SENSIBLE_AVG_CHARS = 150  # 平均不到这么多字一章，基本可断定是误切
    CHARDET_SAMPLE_SIZE = 200_000  # 编码采样大小
    DEFAULT_CHARS_PER_PAGE = 3000  # 无章节标记时的分页粒度

    def __init__(self, chars_per_page: int = DEFAULT_CHARS_PER_PAGE):
        self._chapters: list[Chapter] = []
        self._file_path: str = ""
        self._encoding: str = ""
        self._chars_per_page = max(500, chars_per_page)

    # ------------------------------------------------------------------ 属性
    @property
    def chapters(self) -> list[Chapter]:
        return self._chapters

    @property
    def chapter_count(self) -> int:
        return len(self._chapters)

    @property
    def file_path(self) -> str:
        return self._file_path

    @property
    def encoding(self) -> str:
        return self._encoding

    @property
    def title(self) -> str:
        return Path(self._file_path).stem if self._file_path else ""

    @property
    def total_chars(self) -> int:
        return sum(c.char_count for c in self._chapters)

    # ------------------------------------------------------------------ 加载
    def load_file(self, file_path: str) -> list[Chapter]:
        """读取 TXT、识别编码、切分章节。"""
        self._file_path = str(file_path)
        text = self._read_with_encoding(file_path)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        self._chapters = self._split_chapters(text)
        for i, ch in enumerate(self._chapters):
            ch.index = i
        return self._chapters

    def get_chapter(self, index: int) -> Chapter | None:
        if 0 <= index < len(self._chapters):
            return self._chapters[index]
        return None

    # ------------------------------------------------------------------ 编码
    def _read_with_encoding(self, file_path: str) -> str:
        """优先按 BOM 判定，其次 chardet 采样，最后逐个编码回退。"""
        raw = Path(file_path).read_bytes()

        # 1) BOM 最可靠
        for bom, enc in (
            (b"\xef\xbb\xbf", "utf-8-sig"),
            (b"\xff\xfe", "utf-16-le"),
            (b"\xfe\xff", "utf-16-be"),
        ):
            if raw.startswith(bom):
                try:
                    self._encoding = enc
                    return raw.decode(enc)
                except UnicodeDecodeError:
                    break

        # 2) chardet 采样
        sample = raw[: self.CHARDET_SAMPLE_SIZE]
        detected = (chardet.detect(sample).get("encoding") or "utf-8")

        # 3) 候选序列：chardet 结果优先，中文环境常客兜底
        candidates: list[str] = []
        for enc in (detected, "utf-8", "gb18030", "gbk", "big5", "utf-16", "latin-1"):
            if enc and enc.lower() not in [c.lower() for c in candidates]:
                candidates.append(enc)

        for enc in candidates:
            try:
                text = raw.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
            # gb18030 几乎能解码任何字节流，用它做最后确认会误判，
            # 所以校验一下乱码比例
            if enc.lower() in ("latin-1",) or self._looks_ok(text, enc):
                self._encoding = enc
                return text

        self._encoding = "utf-8"
        return raw.decode("utf-8", errors="replace")

    @staticmethod
    def _looks_ok(text: str, enc: str) -> bool:
        """粗筛：替换符与私用区字符占比过高说明解码错了。"""
        if not text:
            return False
        head = text[:2000]
        bad = sum(1 for c in head if c == "\ufffd" or "\ue000" <= c <= "\uf8ff")
        if bad / max(len(head), 1) > 0.02:
            return False
        return True

    # ------------------------------------------------------------------ 分章
    def _split_chapters(self, text: str) -> list[Chapter]:
        matches = list(self.CHAPTER_PATTERN.finditer(text))
        if not matches:
            return self._paginate(text)

        # 间隔过滤：太近的标题大概率是正文里的数字，不是章节
        filtered = [matches[0]]
        for m in matches[1:]:
            if m.start() - filtered[-1].start() >= self.MIN_CHAPTER_GAP:
                filtered.append(m)

        if not filtered:
            return self._paginate(text)

        # 兜底：切得又碎又短，说明多半还是把正文里的记号当成了标题。
        # 与其给用户一个两千多章的乱目录，不如退回按字数分页。
        if len(filtered) >= self.MIN_SENSIBLE_CHAPTERS:
            avg = len(text) / len(filtered)
            if avg < self.MIN_SENSIBLE_AVG_CHARS:
                return self._paginate(text)

        chapters: list[Chapter] = []

        # 第一个标题之前的内容：太短的多半是书名、作者这类元信息，直接丢掉；
        # 足够长才当作「序章」保留
        first_start = filtered[0].start()
        if first_start > 0:
            preamble = text[:first_start].strip()
            if len(preamble) >= self.MIN_PREAMBLE_CHARS:
                chapters.append(self._make_chapter(len(chapters), "序章", preamble))

        for i, match in enumerate(filtered):
            start = match.start()
            end = filtered[i + 1].start() if i + 1 < len(filtered) else len(text)
            block = text[start:end].strip()
            lines = block.split("\n", 1)
            title = lines[0].strip()
            body = lines[1].strip() if len(lines) > 1 else ""
            chapters.append(self._make_chapter(len(chapters), title, body))

        return chapters

    def _paginate(self, text: str) -> list[Chapter]:
        """没有章节标记：按空行聚合到约 chars_per_page 字一页。"""
        paragraphs = [p for p in text.split("\n") if p.strip()]
        if not paragraphs:
            return []

        chapters: list[Chapter] = []
        buf: list[str] = []
        size = 0

        def flush() -> None:
            nonlocal buf, size
            if buf:
                chapters.append(self._make_chapter(
                    len(chapters), f"片段 {len(chapters) + 1}", "\n".join(buf)
                ))
                buf, size = [], 0

        for para in paragraphs:
            buf.append(para)
            size += len(para)
            if size >= self._chars_per_page:
                flush()
        flush()

        if len(chapters) == 1:
            chapters[0].title = Path(self._file_path).stem
        return chapters

    def _make_chapter(self, index: int, title: str, body: str) -> Chapter:
        return Chapter(
            index=index,
            title=title,
            content=self._text_to_html(body),
            char_count=len(body),
        )

    # ------------------------------------------------------------------ HTML
    def _text_to_html(self, text: str) -> str:
        """纯文本 → HTML 段落。样式（行高/缩进/间距）由渲染层的 CSS 控制。"""
        if not text:
            return ""
        text = text.translate(self.HTML_ESCAPE_TABLE)
        out = []
        for para in text.split("\n"):
            para = para.strip()
            if para:
                out.append(f"<p>{para}</p>")
        return "\n".join(out)

    def plain_text(self, chapter: Chapter) -> str:
        """取章节纯文本（供搜索/复制用）。"""
        html = chapter.content
        html = html.replace("</p>", "\n").replace("<p>", "")
        return html.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
