from fastapi import APIRouter, HTTPException, Query, Header, UploadFile, File, BackgroundTasks
from pydantic import BaseModel
import tempfile, os as _os
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
                "SELECT id, openid, nickname, phone, role, vip_expires_at, avatar_url, created_at, updated_at "
                "FROM wx_users WHERE nickname LIKE %s OR openid LIKE %s OR phone LIKE %s "
                "ORDER BY id DESC LIMIT %s OFFSET %s",
                (like, like, like, limit, offset)
            )
        else:
            cur.execute("SELECT COUNT(*) as cnt FROM wx_users")
            total = cur.fetchone()["cnt"]
            cur.execute(
                "SELECT id, openid, nickname, phone, role, vip_expires_at, avatar_url, created_at, updated_at "
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
    if req.role is not None and req.role in ("user", "vip"):
        kw["role"] = req.role
        if req.vip_days and req.vip_days > 0:
            from datetime import datetime, timedelta
            kw["vip_expires_at"] = (datetime.now() + timedelta(days=req.vip_days)).strftime("%Y-%m-%d %H:%M:%S")
        else:
            kw["role"] = "user"
            kw["vip_expires_at"] = None
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
@router.get("/users/{uid}/usage")
async def admin_user_usage(uid: int, days: int = Query(7, ge=1, le=30), authorization: str = Header(None)):
    _verify_token(authorization)
    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            "SELECT metric, SUM(count) as total FROM usage_stats "
            "WHERE user_id=%s AND date >= DATE_SUB(CURDATE(), INTERVAL %s DAY) "
            "GROUP BY metric", (uid, days)
        )
        return cur.fetchall()

# ── 口语题库管理 ──

from app.routers.oral_question import (
    oral_create_bank, oral_update_bank, oral_delete_bank,
    oral_create_question, oral_update_question, oral_delete_question
)
from pydantic import BaseModel

class OralBankCreate(BaseModel):
    name: str
    icon: str = "📚"
    description: str = ""
    sort_order: int = 0
    type: str = "oral"

class OralBankUpdate(BaseModel):
    name: str | None = None
    icon: str | None = None
    description: str | None = None
    sort_order: int | None = None

class OralQuestionCreate(BaseModel):
    bank_id: int
    question: str
    topic: str = ""
    difficulty: int = 3
    reference_answer: str = ""
    keywords: str = ""

class BatchDelete(BaseModel):
    ids: list[int]

class BatchDeleteKB(BaseModel):
    ids: list[str]

class OralQuestionUpdate(BaseModel):
    question: str | None = None
    topic: str | None = None
    difficulty: int | None = None
    reference_answer: str | None = None
    keywords: str | None = None

@router.get("/oral/banks")
async def admin_oral_banks(authorization: str = Header(None)):
    _verify_token(authorization)
    with get_db() as db:
        cur = db.cursor()
        cur.execute("SELECT id, name, icon, description, sort_order, type FROM oral_question_banks ORDER BY sort_order")
        banks = cur.fetchall()
        for b in banks:
            cur.execute("SELECT COUNT(*) as cnt FROM oral_questions WHERE bank_id=%s", (b["id"],))
            b["question_count"] = cur.fetchone()["cnt"]
        return {"banks": banks}

@router.post("/oral/banks")
async def admin_oral_create_bank(req: OralBankCreate, authorization: str = Header(None)):
    _verify_token(authorization)
    return oral_create_bank(req.name, req.icon, req.description, req.sort_order, req.type)

@router.put("/oral/banks/{bank_id}")
async def admin_oral_update_bank(bank_id: int, req: OralBankUpdate, authorization: str = Header(None)):
    _verify_token(authorization)
    kw = req.model_dump(exclude_none=True)
    if not kw: raise HTTPException(400, "no fields")
    if not oral_update_bank(bank_id, **kw): raise HTTPException(404, "not found")
    return {"ok": True}

@router.delete("/oral/banks/{bank_id}")
async def admin_oral_delete_bank(bank_id: int, authorization: str = Header(None)):
    _verify_token(authorization)
    deleted = oral_delete_bank(bank_id)
    return {"ok": True, "questions_deleted": deleted}

@router.get("/oral/questions")
async def admin_oral_questions(
    bank_id: int = Query(None), limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0), authorization: str = Header(None)):
    _verify_token(authorization)
    with get_db() as db:
        cur = db.cursor()
        sql = "SELECT id, bank_id, topic, difficulty, question, reference_answer, keywords FROM oral_questions WHERE 1=1"
        params = []
        if bank_id: sql += " AND bank_id=%s"; params.append(bank_id)
        sql += " ORDER BY id DESC LIMIT %s OFFSET %s"; params.extend([limit, offset])
        cur.execute(sql, params)
        return {"questions": cur.fetchall()}

@router.post("/oral/questions")
async def admin_oral_create_question(req: OralQuestionCreate, authorization: str = Header(None)):
    _verify_token(authorization)
    return oral_create_question(req.bank_id, req.question, req.topic, req.difficulty, req.reference_answer, req.keywords)

@router.put("/oral/questions/{qid}")
async def admin_oral_update_question(qid: int, req: OralQuestionUpdate, authorization: str = Header(None)):
    _verify_token(authorization)
    kw = req.model_dump(exclude_none=True)
    if not kw: raise HTTPException(400, "no fields")
    if not oral_update_question(qid, **kw): raise HTTPException(404, "not found")
    return {"ok": True}

@router.delete("/oral/questions/{qid}")
async def admin_oral_delete_question(qid: int, authorization: str = Header(None)):
    _verify_token(authorization)
    if not oral_delete_question(qid): raise HTTPException(404, "not found")
    return {"ok": True}

@router.post("/oral/questions/batch-delete")
async def admin_oral_batch_delete(req: BatchDelete, authorization: str = Header(None)):
    _verify_token(authorization)
    deleted = 0
    for qid in req.ids:
        if oral_delete_question(qid):
            deleted += 1
    return {"ok": True, "deleted": deleted}


# ── 知识库管理 ──

from app.services.rag_service import RAGService

class KBImport(BaseModel):
    text: str
    metadata: dict = {}

@router.get("/knowledge/collections")
async def admin_kb_collections(authorization: str = Header(None)):
    _verify_token(authorization)
    return {"collections": RAGService.list_collections()}

@router.get("/knowledge/{collection}/items")
async def admin_kb_items(collection: str, limit: int = Query(100, ge=1, le=500),
                          offset: int = Query(0, ge=0), authorization: str = Header(None)):
    _verify_token(authorization)
    return RAGService.list_items(collection, limit, offset)

@router.post("/knowledge/{collection}/items")
async def admin_kb_import(collection: str, items: list[KBImport], bg: BackgroundTasks,
                          authorization: str = Header(None)):
    _verify_token(authorization)
    docs = [it.text for it in items]; metas = [it.metadata for it in items]
    if not docs:
        raise HTTPException(400, "内容不能为空")
    # 异步：后台 BGE 向量化（慢），秒返 processing，避免前端阻塞
    bg.add_task(_do_embed, collection, docs, metas, "manual")
    return {"ok": True, "imported": len(docs), "status": "processing"}

@router.delete("/knowledge/{collection}/{item_id}")
async def admin_kb_delete_item(collection: str, item_id: str, authorization: str = Header(None)):
    _verify_token(authorization)
    RAGService.delete(collection, [item_id])
    return {"ok": True}

@router.post("/knowledge/{collection}/batch-delete")
async def admin_kb_batch_delete(collection: str, req: BatchDeleteKB, authorization: str = Header(None)):
    _verify_token(authorization)
    if req.ids:
        RAGService.delete(collection, req.ids)
    return {"ok": True, "deleted": len(req.ids)}

@router.post("/knowledge/{collection}/create")
async def admin_kb_create_collection(collection: str, authorization: str = Header(None)):
    _verify_token(authorization)
    if not RAGService.create_collection(collection):
        raise HTTPException(500, "创建集合失败")
    return {"ok": True, "collection": collection}

@router.delete("/knowledge/{collection}")
async def admin_kb_delete_collection(collection: str, authorization: str = Header(None)):
    _verify_token(authorization)
    if not RAGService.delete_collection(collection): raise HTTPException(404, "cannot delete")
    return {"ok": True}

@router.post("/knowledge/{collection}/search")
async def admin_kb_search(collection: str, query: str = Query(...),
                           top_k: int = Query(10, ge=1, le=50), authorization: str = Header(None)):
    _verify_token(authorization)
    results = RAGService.search(collection, query, top_k=top_k)
    return {"collection": collection, "query": query, "results": results}

@router.post("/knowledge/{collection}/upload")
async def admin_kb_upload(collection: str, bg: BackgroundTasks,
                           file: UploadFile = File(...), authorization: str = Header(None)):
    _verify_token(authorization)
    suffix = _os.path.splitext(file.filename or "doc.txt")[1] or ".txt"
    fname = file.filename or "upload"+suffix
    bytes_data = await file.read()

    # 保存临时文件（快）；解析 + 向量化全部后台执行，避免大 PDF 同步解析超时（nginx 504）
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(bytes_data)
        tmp_path = tmp.name

    bg.add_task(_process_kb_upload, collection, tmp_path, fname)

    return {"ok": True, "filename": fname, "collection": collection, "status": "processing"}


def _process_kb_upload(collection: str, tmp_path: str, fname: str):
    """后台：解析文档 + 分批向量化（防大 PDF OOM）+ 清理临时文件"""
    try:
        from app.services.material_parser import parse_file
        chunks = parse_file(tmp_path, fname)
        if chunks:
            BATCH = 8
            for i in range(0, len(chunks), BATCH):
                batch = chunks[i:i+BATCH]
                metas = [{"source": fname, "chunk_index": i+j} for j in range(len(batch))]
                RAGService.add(collection, documents=batch, metadatas=metas)
            logger = __import__("logging").getLogger(__name__)
            logger.info("KB upload done: %s -> %s, %d chunks", fname, collection, len(chunks))
    except Exception as e:
        logger = __import__("logging").getLogger(__name__)
        logger.error("KB upload failed: %s -> %s: %s", fname, collection, e)
    finally:
        try: _os.unlink(tmp_path)
        except: pass

def _do_embed(collection: str, chunks: list, metas: list, fname: str):
    """Background: embed + insert into ChromaDB"""
    try:
        RAGService.add(collection, documents=chunks, metadatas=metas)
        logger = __import__("logging").getLogger(__name__)
        logger.info("KB upload done: %s -> %s, %d chunks", fname, collection, len(chunks))
    except Exception as e:
        logger = __import__("logging").getLogger(__name__)
        logger.error("KB upload failed: %s -> %s: %s", fname, collection, e)

