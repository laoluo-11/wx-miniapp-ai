"""
口语题库 API — 场景列表 + 题目检索 + CRUD helpers
"""
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from app.database import get_db
from app.services.rag_service import RAGService

router = APIRouter(prefix="/api/v1/oral", tags=["oral"])


@router.get("/banks")
async def list_banks(type: str = Query(None)):
    """获取题库分类。type=oral(对练) / voice(测评) / None(全部)"""
    with get_db() as db:
        cur = db.cursor()
        sql = "SELECT id, name, icon, description, type FROM oral_question_banks"
        if type:
            sql += " WHERE type=%s"
            cur.execute(sql, (type,))
        else:
            sql += " ORDER BY sort_order"
            cur.execute(sql)
        return {"banks": cur.fetchall()}


@router.get("/questions")
async def list_questions(
    bank_id: int = Query(None),
    difficulty: int = Query(None),
    limit: int = Query(50, ge=1, le=100)
):
    with get_db() as db:
        cur = db.cursor()
        sql = "SELECT id, bank_id, topic, difficulty, question, reference_answer, keywords FROM oral_questions WHERE 1=1"
        params = []
        if bank_id:
            sql += " AND bank_id=%s"; params.append(bank_id)
        if difficulty:
            sql += " AND difficulty=%s"; params.append(difficulty)
        sql += " ORDER BY id LIMIT %s"; params.append(limit)
        cur.execute(sql, params)
        return {"questions": cur.fetchall()}


@router.get("/search")
async def search_questions(
    q: str = Query(...),
    bank_id: int = Query(None),
    top_k: int = Query(5, ge=1, le=20)
):
    filters = None
    if bank_id: filters = {"bank_id": bank_id}
    results = RAGService.search("oral_questions", q, top_k=top_k, where=filters)
    return {"query": q, "results": results}


# ── Admin CRUD helpers ──

def oral_create_bank(name: str, icon: str = "📚", description: str = "", sort_order: int = 0, bank_type: str = "oral") -> dict:
    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            "INSERT INTO oral_question_banks (name, icon, description, sort_order, type) VALUES (%s,%s,%s,%s,%s)",
            (name, icon, description, sort_order, bank_type))
        return {"id": cur.lastrowid, "name": name}

def oral_update_bank(bank_id, **kw):
    with get_db() as db:
        cur = db.cursor()
        fields = []; params = []
        for k in ["name","icon","description","sort_order"]:
            if k in kw and kw[k] is not None:
                fields.append(f"{k}=%s"); params.append(kw[k])
        if not fields: return False
        params.append(bank_id)
        cur.execute(f"UPDATE oral_question_banks SET {','.join(fields)} WHERE id=%s", params)
        return cur.rowcount > 0

def oral_delete_bank(bank_id: int) -> int:
    with get_db() as db:
        cur = db.cursor()
        cur.execute("SELECT id FROM oral_questions WHERE bank_id=%s", (bank_id,))
        qids = [str(row["id"]) for row in cur.fetchall()]
        if qids:
            try: RAGService.delete("oral_questions", qids)
            except: pass
        cur.execute("DELETE FROM oral_questions WHERE bank_id=%s", (bank_id,))
        deleted_q = cur.rowcount
        cur.execute("DELETE FROM oral_question_banks WHERE id=%s", (bank_id,))
        return deleted_q

def oral_create_question(bank_id, question, topic="", difficulty=3, reference_answer="", keywords="") -> dict:
    with get_db() as db:
        cur = db.cursor()
        cur.execute(
            "INSERT INTO oral_questions (bank_id,topic,difficulty,question,reference_answer,keywords) VALUES (%s,%s,%s,%s,%s,%s)",
            (bank_id, topic, difficulty, question, reference_answer, keywords))
        qid = cur.lastrowid
        try:
            RAGService.add("oral_questions", [question],
                metadatas=[{"bank_id":bank_id,"topic":topic,"difficulty":difficulty,"db_id":qid}],
                ids=[str(qid)])
        except: pass
        return {"id": qid, "question": question[:50]}

def oral_update_question(qid, **kw):
    with get_db() as db:
        cur = db.cursor()
        fields = []; params = []
        for k in ["question","topic","difficulty","reference_answer","keywords"]:
            if k in kw and kw[k] is not None:
                fields.append(f"{k}=%s"); params.append(kw[k])
        if not fields: return False
        params.append(qid)
        cur.execute(f"UPDATE oral_questions SET {','.join(fields)} WHERE id=%s", params)
        if "question" in kw and kw["question"] is not None:
            try:
                RAGService.delete("oral_questions", [str(qid)])
                cur.execute("SELECT bank_id, topic, difficulty FROM oral_questions WHERE id=%s", (qid,))
                row = cur.fetchone()
                if row:
                    RAGService.add("oral_questions", [kw["question"]],
                        metadatas=[{"bank_id":row["bank_id"],"topic":row["topic"] or "","difficulty":row["difficulty"] or 3,"db_id":qid}],
                        ids=[str(qid)])
            except: pass
        return cur.rowcount > 0

def oral_delete_question(qid: int) -> bool:
    with get_db() as db:
        cur = db.cursor()
        cur.execute("DELETE FROM oral_questions WHERE id=%s", (qid,))
        if cur.rowcount > 0:
            try: RAGService.delete("oral_questions", [str(qid)])
            except: pass
            return True
        return False
