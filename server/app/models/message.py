from app.database import get_db
from datetime import datetime

def save(cid: int, role: str, content: str) -> int:
    with get_db() as db:
        cur = db.cursor()
        cur.execute("INSERT INTO messages (conversation_id, role, content) VALUES (%s, %s, %s)",
                    (cid, role, content))
        return cur.lastrowid

def get_history(cid: int, before: int = None, limit: int = 40) -> list:
    with get_db() as db:
        cur = db.cursor()
        if before:
            before_dt = datetime.fromtimestamp(before / 1000)
            cur.execute("""SELECT id, role, content, created_at FROM messages
                           WHERE conversation_id = %s AND created_at < %s
                           ORDER BY id DESC LIMIT %s""", (cid, before_dt, limit))
        else:
            cur.execute("""SELECT id, role, content, created_at FROM messages
                           WHERE conversation_id = %s
                           ORDER BY id DESC LIMIT %s""", (cid, limit))
        rows = cur.fetchall()
        rows.reverse()
        return rows

def get_recent_pairs(cid: int, rounds: int = 10) -> list:
    with get_db() as db:
        cur = db.cursor()
        cur.execute("""SELECT role, content FROM messages
                       WHERE conversation_id = %s ORDER BY id DESC LIMIT %s""",
                    (cid, rounds * 2))
        rows = cur.fetchall()
        rows.reverse()
        return rows
import os as _os

_STATIC_PREFIX = "https://luois-james.xyz/static/"
_UPLOAD_DIR = _os.path.join(_os.path.dirname(__file__), "..", "..", "..", "uploads")


def _cleanup_static_files(contents: list):
    """Clean up static files (images, SVG diagrams, files) referenced in messages."""
    urls = set()
    prefix = _STATIC_PREFIX
    # Regex to find markdown images: ![alt](STATIC_PREFIX...)
    import re as _re
    md_re = _re.compile(r'!\\[.*?\\]\\(' + _re.escape(prefix) + r'[^)]+\\)')
    for c in contents:
        if not c or not isinstance(c, str):
            continue
        if c.startswith(prefix):
            urls.add(c)
        for m in md_re.finditer(c):
            urls.add(m.group(1))
    for url in urls:
        filename = url[len(prefix):]
        filepath = _os.path.join(_UPLOAD_DIR, filename)
        if _os.path.exists(filepath):
            try:
                _os.remove(filepath)
                print(f"[Cleanup] Deleted: {filepath}")
            except Exception as e:
                print(f"[Cleanup] Failed to delete {filepath}: {e}")



def delete_by_ids(cid: int, ids: list) -> int:
    """批量删除消息，返回删除条数。同时清理关联的静态文件。"""
    if not ids:
        return 0
    with get_db() as db:
        cur = db.cursor()
        # 先查内容以便清理文件
        placeholders = ','.join(['%s'] * len(ids))
        cur.execute(
            f"SELECT content FROM messages WHERE conversation_id = %s AND id IN ({placeholders})",
            [cid] + ids
        )
        contents = [row['content'] for row in cur.fetchall()]
        # 删除记录
        cur.execute(
            f"DELETE FROM messages WHERE conversation_id = %s AND id IN ({placeholders})",
            [cid] + ids
        )
        # 清理关联的静态文件
        _cleanup_static_files(contents)
        return cur.rowcount
