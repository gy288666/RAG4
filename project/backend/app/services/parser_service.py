"""文档解析服务（PRD 3.4 / 4.2.2）。

支持 PDF（电子版 + 扫描版 OCR）、DOCX、TXT、Markdown。
统一输出 ``list[TextBlock]``：PDF 逐页返回并携带页码，其余格式 ``page=None``。
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

from app.services import ocr_service

logger = logging.getLogger(__name__)

#: 判定「扫描版 PDF」的文本密度阈值：单页有效字符数低于该值即视为图片页
SCANNED_PAGE_CHAR_THRESHOLD = 40
#: OCR 渲染缩放倍数，2.0 ≈ 144 DPI，兼顾识别率与耗时
OCR_RENDER_ZOOM = 2.0


class ParseError(RuntimeError):
    """文档解析失败（格式损坏、依赖缺失、内容为空等）。"""


@dataclass(slots=True)
class TextBlock:
    """一段带来源信息的文本。"""

    text: str
    page: int | None = None


@dataclass(slots=True)
class ParseResult:
    blocks: list[TextBlock]
    used_ocr: bool = False
    page_count: int = 0

    @property
    def total_chars(self) -> int:
        return sum(len(b.text) for b in self.blocks)


# ------------------------------------------------------------
# 文本清洗
# ------------------------------------------------------------

_WS_RE = re.compile(r"[ \t ]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WS_RE.sub(" ", text)
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


# ------------------------------------------------------------
# 各格式解析器
# ------------------------------------------------------------


def _parse_pdf(path: str) -> ParseResult:
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover
        raise ParseError("服务器缺少 PyMuPDF 依赖，无法解析 PDF 文件") from exc

    blocks: list[TextBlock] = []
    used_ocr = False
    try:
        with fitz.open(path) as pdf:
            page_count = pdf.page_count
            for page_no in range(page_count):
                page = pdf.load_page(page_no)
                text = clean_text(page.get_text("text") or "")

                # PRD 4.2.2：文本为空或密度极低 → 判定为扫描页，启用 OCR
                if len(text) < SCANNED_PAGE_CHAR_THRESHOLD:
                    ocr_text = _ocr_pdf_page(page)
                    if ocr_text:
                        used_ocr = True
                        text = ocr_text

                if text:
                    blocks.append(TextBlock(text=text, page=page_no + 1))
    except ParseError:
        raise
    except Exception as exc:
        raise ParseError(f"PDF 文件解析失败：{exc}") from exc

    if not blocks:
        # 电子版提取为空且 OCR 也没有结果 → 尝试 pdfplumber 兜底
        fallback = _parse_pdf_with_pdfplumber(path)
        if fallback.blocks:
            return fallback
        raise ParseError("未能从该 PDF 中提取到任何文本内容")

    return ParseResult(blocks=blocks, used_ocr=used_ocr, page_count=page_count)


def _ocr_pdf_page(page) -> str:
    """将 PDF 页面渲染为图像后交给 OCR 引擎识别。"""
    import fitz

    try:
        pixmap = page.get_pixmap(matrix=fitz.Matrix(OCR_RENDER_ZOOM, OCR_RENDER_ZOOM))
        return clean_text(ocr_service.image_to_text(pixmap.tobytes("png")))
    except ocr_service.OCRUnavailableError:
        raise ParseError(
            "该文件疑似扫描版 PDF，但服务器未安装 OCR 引擎（PaddleOCR / Tesseract），无法识别"
        )
    except Exception as exc:
        logger.warning("OCR 识别第 %s 页失败: %s", page.number + 1, exc)
        return ""


def _parse_pdf_with_pdfplumber(path: str) -> ParseResult:
    try:
        import pdfplumber  # type: ignore
    except ImportError:  # pragma: no cover
        return ParseResult(blocks=[])

    blocks: list[TextBlock] = []
    try:
        with pdfplumber.open(path) as pdf:
            for idx, page in enumerate(pdf.pages):
                text = clean_text(page.extract_text() or "")
                if text:
                    blocks.append(TextBlock(text=text, page=idx + 1))
            return ParseResult(blocks=blocks, page_count=len(pdf.pages))
    except Exception:  # pragma: no cover
        return ParseResult(blocks=[])


def _parse_docx(path: str) -> ParseResult:
    try:
        import docx  # python-docx
    except ImportError as exc:  # pragma: no cover
        raise ParseError("服务器缺少 python-docx 依赖，无法解析 DOCX 文件") from exc

    try:
        document = docx.Document(path)
    except Exception as exc:
        raise ParseError(f"DOCX 文件解析失败：{exc}") from exc

    parts = [p.text for p in document.paragraphs if p.text and p.text.strip()]
    # 表格文本同样纳入知识库
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text and c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))

    text = clean_text("\n".join(parts))
    if not text:
        raise ParseError("未能从该 DOCX 中提取到任何文本内容")
    return ParseResult(blocks=[TextBlock(text=text)])


def _parse_txt(path: str) -> ParseResult:
    raw = open(path, "rb").read()
    text = _decode_bytes(raw)
    text = clean_text(text)
    if not text:
        raise ParseError("该文本文件内容为空")
    return ParseResult(blocks=[TextBlock(text=text)])


def _parse_markdown(path: str) -> ParseResult:
    raw = _decode_bytes(open(path, "rb").read())
    text = clean_text(_markdown_to_text(raw))
    if not text:
        raise ParseError("该 Markdown 文件内容为空")
    return ParseResult(blocks=[TextBlock(text=text)])


def _markdown_to_text(md_text: str) -> str:
    """保留标题层级语义，去除纯排版符号（PRD 3.4）。"""
    lines: list[str] = []
    in_code_block = False
    for line in md_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            lines.append(line)
            continue
        # 标题：# 号去掉但保留文字，作为独立段落，便于切片时保留上下文
        line = re.sub(r"^\s{0,3}#{1,6}\s+", "", line)
        line = re.sub(r"^\s{0,3}>\s?", "", line)           # 引用
        line = re.sub(r"^\s*[-*+]\s+", "• ", line)          # 无序列表
        line = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", line)    # 图片
        line = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line)  # 链接保留文字
        line = re.sub(r"(\*\*|__|\*|_|`)", "", line)        # 强调与行内代码
        lines.append(line)
    return "\n".join(lines)


#: 按优先级排列的候选字符集。本系统面向中英文学术资料，
#: 因此在得分相同时优先采用中文编码——通用检测库对短中文样本
#: 常误判为 EUC-KR / Shift-JIS 等同族多字节编码。
_CANDIDATE_ENCODINGS = ("utf-8", "gb18030", "big5", "utf-16", "cp1252", "latin-1")


def _text_plausibility(text: str) -> float:
    """文本可读性打分：中日韩汉字、ASCII 与常见中文标点占比越高越可信。"""
    if not text:
        return 0.0
    good = 0
    for ch in text:
        code = ord(ch)
        if (
            0x4E00 <= code <= 0x9FFF  # CJK 汉字
            or 0x3000 <= code <= 0x303F  # 中文标点
            or 0xFF00 <= code <= 0xFF65  # 全角字符
            or code < 0x80  # ASCII
        ):
            good += 1
    return good / len(text)


def _decode_bytes(raw: bytes) -> str:
    """字符集自动识别（UTF-8 / GBK / Big5 / ...）。"""
    if not raw:
        return ""

    # UTF-8 严格解码成功即可直接采信，无需再猜
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass

    candidates: list[str] = list(_CANDIDATE_ENCODINGS)
    try:
        from charset_normalizer import from_bytes  # type: ignore

        detected = from_bytes(raw).best()
        if detected is not None and detected.encoding:
            candidates.append(detected.encoding)  # 检测结果作为末位候选参与打分
    except Exception:  # pragma: no cover
        pass

    best_text, best_score = "", -1.0
    for encoding in candidates:
        try:
            text = raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
        score = _text_plausibility(text)
        if score > best_score:  # 严格大于：同分时保留优先级更高的编码
            best_text, best_score = text, score

    return best_text or raw.decode("utf-8", errors="ignore")


_PARSERS = {
    ".pdf": _parse_pdf,
    ".docx": _parse_docx,
    ".txt": _parse_txt,
    ".md": _parse_markdown,
    ".markdown": _parse_markdown,
}


def supported_extensions() -> set[str]:
    return set(_PARSERS)


def parse(path: str, file_name: str | None = None) -> ParseResult:
    """按扩展名分发到对应解析器。"""
    name = file_name or os.path.basename(path)
    ext = os.path.splitext(name)[1].lower()
    parser = _PARSERS.get(ext)
    if parser is None:
        raise ParseError(f"暂不支持的文件格式：{ext or '未知'}")
    if not os.path.exists(path):
        raise ParseError("文件不存在或已被清理")
    return parser(path)
