from app.database import get_db
from datetime import datetime
import os as _os

RECEIVE_DIR = "/opt/wx-miniapp-ai/receive"
_os.makedirs(RECEIVE_DIR, exist_ok=True)

FILE_URL_PREFIX = "https://luois-james.xyz/receive/"


def save(user_id: int, filename: str, file_url: str, file_size: int = 0,
         file_type: str = "file", conversation_id: int = None) -> int:
    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            "INSERT INTO user_files (user_id, conversation_id, filename, file_type, file_url, file_size) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, conversation_id, filename, file_type, file_url, file_size)
        )
        return cur.lastrowid


def list_by_user(uid: int, limit: int = 50) -> list:
    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            "SELECT * FROM user_files WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
            (uid, limit)
        )
        return cur.fetchall()


def list_by_conversation(cid: int) -> list:
    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            "SELECT * FROM user_files WHERE conversation_id = %s ORDER BY created_at DESC",
            (cid,)
        )
        return cur.fetchall()


def delete(file_id: int) -> bool:
    with get_db() as db:
        cur = db.cursor()
        cur.execute("SELECT file_url FROM user_files WHERE id = %s", (file_id,))
        row = cur.fetchone()
        if row:
            _cleanup_file(row["file_url"])
            cur.execute("DELETE FROM user_files WHERE id = %s", (file_id,))
            return True
    return False


def delete_by_conversation(cid: int):
    with get_db() as db:
        cur = db.cursor()
        cur.execute("SELECT file_url FROM user_files WHERE conversation_id = %s", (cid,))
        for row in cur.fetchall():
            _cleanup_file(row["file_url"])
        cur.execute("DELETE FROM user_files WHERE conversation_id = %s", (cid,))


def _cleanup_file(url: str):
    if url.startswith(FILE_URL_PREFIX):
        filename = url[len(FILE_URL_PREFIX):]
        filepath = _os.path.join(RECEIVE_DIR, filename)
        if _os.path.exists(filepath):
            try:
                _os.remove(filepath)
                print(f"[FileCleanup] Deleted: {filepath}")
            except Exception as e:
                print(f"[FileCleanup] Failed: {filepath}: {e}")
