"""OCR 引擎适配层（PRD 3.2 / 4.2.2 扫描版 PDF）。

优先使用 PaddleOCR，未安装时回退 Tesseract；两者都不可用时抛出
``OCRUnavailableError``，由上层将文档标记为 ``failed`` 并给出明确中文提示，
同时进入管理后台的「OCR 失败队列」。
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_engine: "_BaseOCR | None" = None
_probed = False


class OCRUnavailableError(RuntimeError):
    """服务器未安装任何可用的 OCR 引擎。"""


class _BaseOCR:
    name = "base"

    def image_to_text(self, image_bytes: bytes) -> str:  # pragma: no cover - 抽象
        raise NotImplementedError


class _PaddleOCR(_BaseOCR):
    name = "paddleocr"

    def __init__(self) -> None:
        from paddleocr import PaddleOCR  # type: ignore

        # 中英混排；关闭方向分类器以提升吞吐，扫描件通常方向正确
        self._ocr = PaddleOCR(use_angle_cls=False, lang="ch", show_log=False)

    def image_to_text(self, image_bytes: bytes) -> str:
        import io

        import numpy as np  # type: ignore
        from PIL import Image  # type: ignore

        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        result = self._ocr.ocr(np.array(image), cls=False)
        lines: list[str] = []
        for page in result or []:
            for item in page or []:
                try:
                    lines.append(str(item[1][0]))
                except (IndexError, TypeError):
                    continue
        return "\n".join(lines)


class _TesseractOCR(_BaseOCR):
    name = "tesseract"

    def __init__(self) -> None:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore  # noqa: F401  提前校验依赖存在

        self._pytesseract = pytesseract
        # 触发一次调用以确认系统级 tesseract 可执行文件存在
        pytesseract.get_tesseract_version()

    def image_to_text(self, image_bytes: bytes) -> str:
        import io

        from PIL import Image  # type: ignore

        image = Image.open(io.BytesIO(image_bytes))
        return self._pytesseract.image_to_string(image, lang="chi_sim+eng")


def get_engine() -> _BaseOCR:
    """惰性探测并返回可用的 OCR 引擎（进程内单例）。"""
    global _engine, _probed
    with _lock:
        if _engine is not None:
            return _engine
        if _probed:
            raise OCRUnavailableError(
                "服务器未安装 OCR 引擎（PaddleOCR / Tesseract），无法解析扫描版 PDF"
            )
        _probed = True
        for factory in (_PaddleOCR, _TesseractOCR):
            try:
                _engine = factory()
                logger.info("OCR 引擎已就绪: %s", _engine.name)
                return _engine
            except Exception as exc:  # 依赖缺失或初始化失败 → 尝试下一个
                logger.info("OCR 引擎 %s 不可用: %s", factory.name, exc)
        raise OCRUnavailableError(
            "服务器未安装 OCR 引擎（PaddleOCR / Tesseract），无法解析扫描版 PDF"
        )


def is_available() -> bool:
    try:
        get_engine()
        return True
    except OCRUnavailableError:
        return False


def image_to_text(image_bytes: bytes) -> str:
    return get_engine().image_to_text(image_bytes)
