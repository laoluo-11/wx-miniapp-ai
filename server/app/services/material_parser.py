"""
学习资料解析器 — PDF/Word/Text → 分段 chunks
"""
import os
import logging

logger = logging.getLogger(__name__)

CHUNK_SIZE = 512
CHUNK_OVERLAP = 128


def parse_file(filepath: str, filename: str) -> list:
    ext = os.path.splitext(filename)[1].lower()
    text = ""

    if ext == ".pdf":
        text = _parse_pdf(filepath)
    elif ext in (".docx", ".doc"):
        text = _parse_docx(filepath)
    elif ext in (".txt", ".md", ".markdown"):
        text = _parse_text(filepath)
    else:
        raise ValueError("unsupported: " + ext)

    if not text or not text.strip():
        raise ValueError("empty content")

    chunks = _split_chunks(text)
    logger.info("Parsed %s: %d chars -> %d chunks", filename, len(text), len(chunks))
    return chunks


def _parse_pdf(filepath: str) -> str:
    import fitz
    doc = fitz.open(filepath)
    pages = [page.get_text("text") for page in doc]
    doc.close()
    return chr(10).join(pages)


def _parse_docx(filepath: str) -> str:
    from docx import Document
    doc = Document(filepath)
    paras = [p.text for p in doc.paragraphs if p.text.strip()]
    return chr(10).join(paras)


def _parse_text(filepath: str) -> str:
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _split_chunks(text: str) -> list:
    text = text.strip()
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = end - CHUNK_OVERLAP
    return chunks
