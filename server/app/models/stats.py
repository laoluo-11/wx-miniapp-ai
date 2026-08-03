from app.database import get_db

def user_stats(uid: int) -> dict:
    with get_db() as db:
        cur = db.cursor()
        cur.execute("SELECT COUNT(*) as cnt FROM conversations WHERE user_id = %s", (uid,))
        convs = cur.fetchone()["cnt"]
        cur.execute("SELECT COUNT(*) as cnt FROM messages m JOIN conversations c ON m.conversation_id=c.id WHERE c.user_id=%s", (uid,))
        msgs = cur.fetchone()["cnt"]
        cur.execute("SELECT COUNT(*) as cnt FROM voice_assessments WHERE user_id=%s", (uid,))
        assessments = cur.fetchone()["cnt"]
        return {"conversations": convs, "messages": msgs, "assessments": assessments}
