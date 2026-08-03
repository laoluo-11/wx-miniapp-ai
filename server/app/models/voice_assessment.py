from app.database import get_db

def save(uid: int, text: str, score: int, accuracy: int, fluency: int, integrity: int, standard: int) -> int:
    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            "INSERT INTO voice_assessments (user_id, text, score, accuracy, fluency, integrity, standard)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (uid, text, score, accuracy, fluency, integrity, standard)
        )
        return cur.lastrowid

def get_by_user(uid: int, limit: int = 30) -> list:
    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            "SELECT id, text, score, accuracy, fluency, integrity, standard, created_at"
            " FROM voice_assessments WHERE user_id = %s ORDER BY id DESC LIMIT %s",
            (uid, limit)
        )
        return cur.fetchall()

def count_by_user(uid: int) -> int:
    with get_db() as db:
        cur = db.cursor()
        cur.execute("SELECT COUNT(*) as cnt FROM voice_assessments WHERE user_id = %s", (uid,))
        row = cur.fetchone()
        return row["cnt"] if row else 0
