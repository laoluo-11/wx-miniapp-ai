from app.database import get_db

def create(uid: int, title: str = "新的对话") -> int:
    with get_db() as db:
        cur = db.cursor()
        cur.execute("INSERT INTO conversations (user_id, title) VALUES (%s, %s)", (uid, title))
        return cur.lastrowid

def list_by_user(uid: int, limit: int = 50) -> list:
    with get_db() as db:
        cur = db.cursor()
        cur.execute("""SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) as msg_count
                       FROM conversations c WHERE c.user_id = %s
                       ORDER BY c.updated_at DESC LIMIT %s""", (uid, limit))
        return cur.fetchall()

def get_by_id(cid: int, uid: int) -> dict | None:
    with get_db() as db:
        cur = db.cursor()
        cur.execute("SELECT * FROM conversations WHERE id = %s AND user_id = %s", (cid, uid))
        return cur.fetchone()

def update_title(cid: int, title: str):
    with get_db() as db:
        cur = db.cursor()
        cur.execute("UPDATE conversations SET title = %s, updated_at = NOW() WHERE id = %s", (title, cid))

def touch(cid: int):
    with get_db() as db:
        cur = db.cursor()
        cur.execute("UPDATE conversations SET updated_at = NOW() WHERE id = %s", (cid,))

def delete(cid: int, uid: int) -> bool:
    with get_db() as db:
        cur = db.cursor()
        cur.execute("DELETE FROM conversations WHERE id = %s AND user_id = %s", (cid, uid))
        return cur.rowcount > 0
