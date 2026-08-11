"""
口语题库 API — 场景列表 + 题目检索
"""
from fastapi import APIRouter, Query, HTTPException
from app.database import get_db
from app.services.rag_service import RAGService

router = APIRouter(prefix="/api/v1/oral", tags=["oral"])


@router.get("/banks")
async def list_banks():
    """获取所有题库分类"""
    with get_db() as db:
        cur = db.cursor()
        cur.execute("SELECT id, name, icon, description FROM oral_question_banks ORDER BY sort_order")
        return {"banks": cur.fetchall()}


@router.get("/questions")
async def list_questions(
    bank_id: int = Query(None),
    difficulty: int = Query(None),
    limit: int = Query(50, ge=1, le=100)
):
    """获取题目列表，可按题库和难度筛选"""
    with get_db() as db:
        cur = db.cursor()
        sql = "SELECT id, bank_id, topic, difficulty, question, reference_answer, keywords FROM oral_questions WHERE 1=1"
        params = []
        if bank_id:
            sql += " AND bank_id=%s"
            params.append(bank_id)
        if difficulty:
            sql += " AND difficulty=%s"
            params.append(difficulty)
        sql += " ORDER BY id LIMIT %s"
        params.append(limit)
        cur.execute(sql, params)
        return {"questions": cur.fetchall()}


@router.get("/search")
async def search_questions(
    q: str = Query(...),
    bank_id: int = Query(None),
    top_k: int = Query(5, ge=1, le=20)
):
    """RAG 语义搜索题目"""
    filters = None
    if bank_id:
        filters = {"bank_id": bank_id}
    results = RAGService.search("oral_questions", q, top_k=top_k, where=filters)
    return {"query": q, "results": results}
