import secrets
from datetime import datetime, timedelta
from app.database import get_db

def create(uid: int, session_key: str) -> str:
    token = secrets.token_hex(32)
    exp = datetime.now() + timedelta(hours=72)
    with get_db() as db:
        cur = db.cursor()
        cur.execute("INSERT INTO user_sessions (user_id, token, session_key, expires_at) VALUES (%s,%s,%s,%s)",
                    (uid, token, session_key, exp))
    return token

def validate(token: str) -> dict | None:
    with get_db() as db:
        cur = db.cursor()
        cur.execute("""SELECT u.*, s.session_key FROM user_sessions s
                       JOIN wx_users u ON s.user_id = u.id
                       WHERE s.token = %s AND s.expires_at > NOW()""", (token,))
        return cur.fetchone()

def delete(token: str):
    with get_db() as db:
        cur = db.cursor()
        cur.execute("DELETE FROM user_sessions WHERE token = %s", (token,))
