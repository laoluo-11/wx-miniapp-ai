from app.database import get_db

def find_or_create(openid: str, unionid: str = None) -> dict:
    with get_db() as db:
        cur = db.cursor()
        cur.execute("SELECT * FROM wx_users WHERE openid = %s", (openid,))
        u = cur.fetchone()
        if u:
            if unionid and not u.get("unionid"):
                cur.execute("UPDATE wx_users SET unionid = %s WHERE id = %s", (unionid, u["id"]))
            return u
        cur.execute("INSERT INTO wx_users (openid, unionid) VALUES (%s, %s)", (openid, unionid))
        return {"id": cur.lastrowid, "openid": openid, "unionid": unionid,
                "nickname": None, "avatar_url": None, "phone": None}

def get_by_id(uid: int) -> dict:
    with get_db() as db:
        cur = db.cursor()
        cur.execute("SELECT * FROM wx_users WHERE id = %s", (uid,))
        return cur.fetchone()

def update(uid: int, **kw) -> bool:
    if not kw: return False
    sets = ", ".join(f"{k} = %s" for k in kw)
    vals = list(kw.values()) + [uid]
    with get_db() as db:
        cur = db.cursor()
        cur.execute(f"UPDATE wx_users SET {sets} WHERE id = %s", vals)
        return cur.rowcount > 0
