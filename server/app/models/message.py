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

def delete_by_ids(cid: int, ids: list) -> int:
    """批量删除消息，返回删除条数"""
    if not ids:
        return 0
    with get_db() as db:
        cur = db.cursor()
        placeholders = ','.join(['%s'] * len(ids))
        cur.execute(
            f"DELETE FROM messages WHERE conversation_id = %s AND id IN ({placeholders})",
            [cid] + ids
        )
        return cur.rowcount
