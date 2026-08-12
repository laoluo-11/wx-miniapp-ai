"""
错题本数据层 — 增删查 + SM-2 间隔重复
"""
from datetime import date, timedelta
from app.database import get_db


def add(user_id: int, question: str, answer: str = "", tags: str = "",
        source: str = "chat", source_id: int = None) -> int:
    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            """INSERT INTO mistake_books (user_id,question,answer,tags,source,source_id,next_review_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (user_id, question, answer, tags, source, source_id, date.today())
        )
        return cur.lastrowid


def list_all(user_id: int, limit: int = 50) -> list:
    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            """SELECT id,question,answer,tags,source,next_review_at,
                      interval_days,ease_factor,repetitions,last_rating,created_at
               FROM mistake_books WHERE user_id=%s ORDER BY next_review_at ASC LIMIT %s""",
            (user_id, limit)
        )
        return cur.fetchall()


def review_today(user_id: int) -> list:
    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            """SELECT id,question,answer,tags,source,next_review_at,
                      interval_days,ease_factor,repetitions,last_rating,created_at
               FROM mistake_books WHERE user_id=%s AND next_review_at <= %s
               ORDER BY next_review_at ASC""",
            (user_id, date.today())
        )
        return cur.fetchall()


def review_count(user_id: int) -> int:
    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM mistake_books WHERE user_id=%s AND next_review_at <= %s",
            (user_id, date.today())
        )
        return cur.fetchone()["COUNT(*)"]


def sm2_update(mistake_id: int, rating: int) -> dict:
    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            "SELECT interval_days,ease_factor,repetitions FROM mistake_books WHERE id=%s",
            (mistake_id,)
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("not found")

        interval = row["interval_days"]
        ease = float(row["ease_factor"])
        reps = row["repetitions"]

        if rating >= 3:
            ease = ease + (0.1 - (5 - rating) * (0.08 + (5 - rating) * 0.02))
            if ease < 1.3:
                ease = 1.3
            reps += 1
            if reps == 1:
                interval = 1
            elif reps == 2:
                interval = 6
            else:
                interval = round(interval * ease)
        else:
            reps = 0
            interval = 1

        next_review = date.today() + timedelta(days=interval)
        cur.execute(
            """UPDATE mistake_books SET interval_days=%s,ease_factor=%s,repetitions=%s,
               next_review_at=%s,last_rating=%s WHERE id=%s""",
            (interval, ease, reps, next_review, rating, mistake_id)
        )
        return {"interval_days": interval, "ease_factor": round(ease, 2),
                "repetitions": reps, "next_review_at": str(next_review)}


def delete(mistake_id: int, user_id: int) -> bool:
    with get_db() as db:
        cur = db.cursor()
        cur.execute("DELETE FROM mistake_books WHERE id=%s AND user_id=%s", (mistake_id, user_id))
        return cur.rowcount > 0
