"""
学习资料解析器 — PDF/Word/Text → 分段 chunks
按句子边界切分 + 尽量凑满目标长度（512字符）+ 128字符重叠
"""
import os
import re
import logging

logger = logging.getLogger(__name__)

CHUNK_SIZE = 512
CHUNK_OVERLAP = 128

# 句子结束符：中文句号/问号/感叹号/分号 + 英文标点
_SENT_SPLIT = re.compile(r'(?<=[。！？!?；;.])')


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
    """按句子边界切分，每段尽量接近 CHUNK_SIZE，段间保留 CHUNK_OVERLAP 重叠"""
    text = text.strip()
    n = len(text)
    if n <= CHUNK_SIZE:
        return [text] if text else []

    # 所有句子结束位置（切分点）
    boundaries = [m.end() for m in _SENT_SPLIT.finditer(text)]
    if not boundaries:
        # 无句子边界（整段无标点），退回固定长度滑动窗口
        chunks = []
        start = 0
        while start < n:
            chunks.append(text[start:start + CHUNK_SIZE].strip())
            if start + CHUNK_SIZE >= n:
                break
            start += CHUNK_SIZE - CHUNK_OVERLAP
        return [c for c in chunks if c]

    chunks = []
    start = 0
    while start < n:
        target = min(start + CHUNK_SIZE, n)
        # 在 [start, target] 区间内找最靠后的句子边界作为切点
        end = target
        for b in boundaries:
            if b > target:
                break
            if b > start:
                end = b
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        # 重叠：新起点 = 当前切点往前 CHUNK_OVERLAP 字符处，再对齐到最近的句子边界
        new_start = end - CHUNK_OVERLAP
        start = new_start
        for b in reversed(boundaries):
            if b <= new_start:
                start = b
                break
        # 防死循环 / 回退过多
        if start <= 0 or start >= end:
            start = end
    return chunks
