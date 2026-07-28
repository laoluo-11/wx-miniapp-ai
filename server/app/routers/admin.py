from fastapi import APIRouter, HTTPException, Query, Header
from pydantic import BaseModel
from app.config import ADMIN_PASSWORD
from app.database import get_db
import secrets, hashlib

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])

class AdminLogin(BaseModel):
    password: str

class UserUpdate(BaseModel):
    nickname: str | None = None
    avatar_url: str | None = None
    phone: str | None = None
    role: str | None = None
    vip_days: int | None = None

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def _verify_token(authorization: str):
    if not authorization:
        raise HTTPException(401, "\u672a\u6388\u6743")
    token = authorization.replace("Bearer ", "")
    htoken = _hash_token(token)
    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            "SELECT id FROM admin_sessions WHERE token_hash = %s AND expires_at > NOW()",
            (htoken,)
        )
        if not cur.fetchone():
            raise HTTPException(401, "\u672a\u6388\u6743\u6216\u5df2\u8fc7\u671f")

@router.post("/login")
async def login(req: AdminLogin):
    if req.password != ADMIN_PASSWORD:
        raise HTTPException(403, "\u5bc6\u7801\u9519\u8bef")
    token = secrets.token_hex(32)
    htoken = _hash_token(token)
    with get_db() as db:
        cur = db.cursor()
        cur.execute("DELETE FROM admin_sessions WHERE expires_at < NOW()")
        cur.execute(
            "INSERT INTO admin_sessions (token_hash, expires_at) VALUES (%s, NOW() + INTERVAL 8 HOUR)",
            (htoken,)
        )
    return {"token": token}

@router.get("/users")
async def list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: str = "",
    authorization: str = Header(None)
):
    _verify_token(authorization)
    offset = (page - 1) * limit
    with get_db() as db:
        cur = db.cursor()
        if search:
            like = f"%{search}%"
            cur.execute(
                "SELECT COUNT(*) as cnt FROM wx_users WHERE nickname LIKE %s OR openid LIKE %s OR phone LIKE %s",
                (like, like, like)
            )
            total = cur.fetchone()["cnt"]
            cur.execute(
                "SELECT id, openid, nickname, phone, avatar_url, created_at, updated_at "
                "FROM wx_users WHERE nickname LIKE %s OR openid LIKE %s OR phone LIKE %s "
                "ORDER BY id DESC LIMIT %s OFFSET %s",
                (like, like, like, limit, offset)
            )
        else:
            cur.execute("SELECT COUNT(*) as cnt FROM wx_users")
            total = cur.fetchone()["cnt"]
            cur.execute(
                "SELECT id, openid, nickname, phone, avatar_url, created_at, updated_at "
                "FROM wx_users ORDER BY id DESC LIMIT %s OFFSET %s",
                (limit, offset)
            )
        users = cur.fetchall()
        return {"users": users, "total": total, "page": page, "limit": limit}

@router.get("/users/{uid}")
async def get_user(uid: int, authorization: str = Header(None)):
    _verify_token(authorization)
    from app.models.user import get_by_id
    user = get_by_id(uid)
    if not user:
        raise HTTPException(404, "\u7528\u6237\u4e0d\u5b58\u5728")
    with get_db() as db:
        cur = db.cursor()
        cur.execute("SELECT COUNT(*) as cnt FROM conversations WHERE user_id = %s", (uid,))
        conv_cnt = cur.fetchone()["cnt"]
        cur.execute("SELECT COUNT(*) as cnt FROM messages m JOIN conversations c ON m.conversation_id = c.id WHERE c.user_id = %s", (uid,))
        msg_cnt = cur.fetchone()["cnt"]
        cur.execute("SELECT COUNT(*) as cnt FROM voice_assessments WHERE user_id = %s", (uid,))
        assess_cnt = cur.fetchone()["cnt"]
        cur.execute("SELECT COUNT(*) as cnt FROM user_memories WHERE user_id = %s", (uid,))
        mem_cnt = cur.fetchone()["cnt"]
        cur.execute("SELECT COUNT(*) as cnt FROM user_sessions WHERE user_id = %s", (uid,))
        sess_cnt = cur.fetchone()["cnt"]
    user["stats"] = {
        "conversations": conv_cnt,
        "messages": msg_cnt,
        "assessments": assess_cnt,
        "memories": mem_cnt,
        "sessions": sess_cnt
    }
    return user

@router.put("/users/{uid}")
async def update_user(uid: int, req: UserUpdate, authorization: str = Header(None)):
    _verify_token(authorization)
    from app.models.user import update
    kw = {}
    if req.nickname is not None: kw["nickname"] = req.nickname
    if req.avatar_url is not None: kw["avatar_url"] = req.avatar_url
    if req.phone is not None: kw["phone"] = req.phone
    if not kw:
        raise HTTPException(400, "\u65e0\u66f4\u65b0\u5b57\u6bb5")
    update(uid, **kw)
    return {"msg": "ok"}

@router.delete("/users/{uid}")
async def delete_user(uid: int, authorization: str = Header(None)):
    _verify_token(authorization)
    with get_db() as db:
        cur = db.cursor()
        cur.execute("SELECT id FROM conversations WHERE user_id = %s", (uid,))
        cids = [row["id"] for row in cur.fetchall()]
        if cids:
            ph = ",".join(["%s"] * len(cids))
            cur.execute(f"DELETE FROM messages WHERE conversation_id IN ({ph})", cids)
            cur.execute(f"DELETE FROM conversations WHERE id IN ({ph})", cids)
        cur.execute("DELETE FROM user_sessions WHERE user_id = %s", (uid,))
        cur.execute("DELETE FROM voice_assessments WHERE user_id = %s", (uid,))
        cur.execute("DELETE FROM user_memories WHERE user_id = %s", (uid,))
        cur.execute("DELETE FROM user_files WHERE user_id = %s", (uid,))
        cur.execute("DELETE FROM wx_users WHERE id = %s", (uid,))
        if cur.rowcount == 0:
            raise HTTPException(404, "\u7528\u6237\u4e0d\u5b58\u5728")
    return {"msg": "ok", "deleted_uid": uid}

@router.get("/stats")
async def admin_stats(authorization: str = Header(None)):
    _verify_token(authorization)
    with get_db() as db:
        cur = db.cursor()
        stats = {}
        cur.execute("SELECT COUNT(*) as cnt FROM wx_users")
        stats["users"] = cur.fetchone()["cnt"]
        cur.execute("SELECT COUNT(*) as cnt FROM conversations")
        stats["conversations"] = cur.fetchone()["cnt"]
        cur.execute("SELECT COUNT(*) as cnt FROM messages")
        stats["messages"] = cur.fetchone()["cnt"]
        cur.execute("SELECT COUNT(*) as cnt FROM voice_assessments")
        stats["assessments"] = cur.fetchone()["cnt"]
        cur.execute("SELECT COUNT(*) as cnt FROM user_memories")
        stats["memories"] = cur.fetchone()["cnt"]
        cur.execute("SELECT COUNT(*) as cnt FROM user_files")
        stats["files"] = cur.fetchone()["cnt"]
    return stats

@router.get("/users/{uid}/conversations")
async def admin_user_conversations(uid: int, limit: int = Query(50, ge=1, le=100), authorization: str = Header(None)):
    _verify_token(authorization)
    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            "SELECT id, title, created_at, updated_at, "
            "(SELECT COUNT(*) FROM messages WHERE conversation_id = c.id) as msg_count "
            "FROM conversations c WHERE user_id = %s ORDER BY updated_at DESC LIMIT %s",
            (uid, limit)
        )
        return cur.fetchall()

@router.get("/conversations/{cid}/messages")
async def admin_conversation_messages(cid: int, limit: int = Query(50, ge=1, le=200), authorization: str = Header(None)):
    _verify_token(authorization)
    from app.models.message import get_history
    msgs = get_history(cid, limit=limit)
    return [{"id": m["id"], "role": m["role"], "content": m["content"], "time": str(m.get("created_at", ""))} for m in msgs]

@router.delete("/conversations/{cid}")
async def admin_delete_conversation(cid: int, authorization: str = Header(None)):
    _verify_token(authorization)
    from app.models.message import _cleanup_static_files
    with get_db() as db:
        cur = db.cursor()
        # Get messages content for file cleanup
        cur.execute("SELECT content FROM messages WHERE conversation_id = %s", (cid,))
        contents = [row["content"] for row in cur.fetchall()]
        cur.execute("DELETE FROM messages WHERE conversation_id = %s", (cid,))
        cur.execute("DELETE FROM conversations WHERE id = %s", (cid,))
        if cur.rowcount == 0:
            raise HTTPException(404, "对话不存在")
        # Cleanup files
        _cleanup_static_files(contents)
        from app.models.file import delete_by_conversation
        delete_by_conversation(cid)
    return {"msg": "ok", "deleted_cid": cid}
"""Admin 后台管理系统 — 用户数据 CRUD"""


@router.get("/users/{uid}/assessments")
async def admin_user_assessments(uid: int, limit: int = Query(50, ge=1, le=100), authorization: str = Header(None)):
    _verify_token(authorization)
    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            "SELECT id, text, score, accuracy, fluency, integrity, standard, created_at "
            "FROM voice_assessments WHERE user_id = %s ORDER BY id DESC LIMIT %s",
            (uid, limit)
        )
        return cur.fetchall()

@router.get("/users/{uid}/memories")
async def admin_user_memories(uid: int, limit: int = Query(50, ge=1, le=100), authorization: str = Header(None)):
    _verify_token(authorization)
    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            "SELECT id, content, `key`, importance, created_at "
            "FROM user_memories WHERE user_id = %s ORDER BY importance DESC, created_at DESC LIMIT %s",
            (uid, limit)
        )
        return cur.fetchall()

@router.get("/users/{uid}/files")
async def admin_user_files(uid: int, limit: int = Query(50, ge=1, le=100), authorization: str = Header(None)):
    _verify_token(authorization)
    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            "SELECT id, filename, file_type, file_url, file_size, conversation_id, created_at "
            "FROM user_files WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
            (uid, limit)
        )
        return cur.fetchall()


@router.delete("/assessments/{aid}")
async def admin_delete_assessment(aid: int, authorization: str = Header(None)):
    _verify_token(authorization)
    with get_db() as db:
        cur = db.cursor()
        cur.execute("DELETE FROM voice_assessments WHERE id = %s", (aid,))
        if cur.rowcount == 0:
            raise HTTPException(404, "记录不存在")
    return {"msg": "ok"}

@router.delete("/memories/{mid}")
async def admin_delete_memory(mid: int, authorization: str = Header(None)):
    _verify_token(authorization)
    from app.utils.memory_manager import delete as del_mem
    if not del_mem(mid):
        raise HTTPException(404, "记录不存在")
    return {"msg": "ok"}

@router.delete("/files/{fid}")
async def admin_delete_file(fid: int, authorization: str = Header(None)):
    _verify_token(authorization)
    from app.models.file import delete as del_file
    if not del_file(fid):
        raise HTTPException(404, "记录不存在")
    return {"msg": "ok"}