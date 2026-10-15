from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable

from .models import EvidenceSpan, SourceRecord

PARSER_VERSION = "mwenza-extractor-0.1"


def checksum_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _plain_pages(source_id: str, text: str, method: str = "text") -> list[EvidenceSpan]:
    pages = re.split(r"\f", text)
    spans: list[EvidenceSpan] = []
    offset = 0
    for page_number, page_text in enumerate(pages, start=1):
        cleaned = page_text.strip()
        if cleaned:
            start = text.find(cleaned, offset)
            end = start + len(cleaned)
            spans.append(EvidenceSpan(source_id, page_number, start, end, cleaned, method, 1.0, parser_version=PARSER_VERSION))
            offset = end
    return spans


def extract_text_file(path: Path, source_id: str, data: bytes) -> SourceRecord:
    text = data.decode("utf-8", errors="replace")
    pages = _plain_pages(source_id, text)
    return SourceRecord(source_id, path.name, "text/plain", checksum_bytes(data), "ready", pages=pages)


def _ocr_page(page, source_id: str, page_number: int) -> EvidenceSpan | None:
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return None
    pixmap = page.get_pixmap(matrix=page.derotation_matrix, alpha=False)
    image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
    text = pytesseract.image_to_string(image).strip()
    if not text:
        return None
    return EvidenceSpan(source_id, page_number, 0, len(text), text, "ocr", 0.72, parser_version=PARSER_VERSION)


def extract_pdf(path: Path, source_id: str, data: bytes) -> SourceRecord:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PDF extraction requires PyMuPDF. Install backend dependencies first.") from exc

    document = fitz.open(stream=data, filetype="pdf")
    spans: list[EvidenceSpan] = []
    text_pages = 0
    for index, page in enumerate(document):
        text = page.get_text("text").strip()
        if text:
            text_pages += 1
            spans.append(EvidenceSpan(source_id, index + 1, 0, len(text), text, "text", 1.0, parser_version=PARSER_VERSION))
        else:
            ocr_span = _ocr_page(page, source_id, index + 1)
            if ocr_span:
                spans.append(ocr_span)
    status = "ready" if spans else "ocr_required"
    metadata = {"page_count": len(document), "text_pages": text_pages, "ocr_pages": len(spans) - text_pages}
    return SourceRecord(source_id, path.name, "application/pdf", checksum_bytes(data), status, pages=spans, metadata=metadata)


def ingest_path(path: str | Path, source_id: str | None = None) -> SourceRecord:
    file_path = Path(path)
    data = file_path.read_bytes()
    source_id = source_id or f"src-{checksum_bytes(data)[:16]}"
    if file_path.suffix.lower() == ".pdf":
        return extract_pdf(file_path, source_id, data)
    return extract_text_file(file_path, source_id, data)
