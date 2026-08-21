"""
学习资料解析器 — PDF/Word/Text → 分段 chunks
按句子边界切分 + 尽量凑满目标长度（512字符）
"""
import os
import re
import logging

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1000

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
    """按句子边界切分，每段尽量接近 CHUNK_SIZE。

    实现为 O(n) 单次遍历：先一次正则 split 切成句子，再贪心累积凑满 512 字。
    避免旧版「重叠回退 + 边界对齐」算法在无标点长段处 start 回退到原点导致的死循环
    （表现为切分 8 万字文本 90 秒跑不完、内存涨到 2GB+）。
    """
    text = text.strip()
    n = len(text)
    if n <= CHUNK_SIZE:
        return [text] if text else []

    # 一次 split 切成句子（句尾标点保留在前一句末尾）
    sentences = [s for s in _SENT_SPLIT.split(text) if s.strip()]

    chunks = []
    cur = ""
    for sent in sentences:
        if len(cur) + len(sent) <= CHUNK_SIZE:
            cur += sent
        else:
            if cur.strip():
                chunks.append(cur.strip())
            if len(sent) > CHUNK_SIZE:
                # 超长单句（无标点）硬切
                for i in range(0, len(sent), CHUNK_SIZE):
                    piece = sent[i:i + CHUNK_SIZE].strip()
                    if piece:
                        chunks.append(piece)
                cur = ""
            else:
                cur = sent
    if cur.strip():
        chunks.append(cur.strip())
    return [c for c in chunks if c]
