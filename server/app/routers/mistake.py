"""
错题本 API — 增删查 + SM-2 评分复习
"""
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Depends
from app.models import mistake as mistake_db
from app.utils.auth import current_user

router = APIRouter(prefix="/api/v1/mistakes", tags=["mistakes"])


class AddRequest(BaseModel):
    question: str
    answer: str = ""
    tags: str = ""
    source: str = "chat"
    source_id: int = None


class RateRequest(BaseModel):
    rating: int  # 1-5


@router.post("/add")
async def add_mistake(req: AddRequest, user: dict = Depends(current_user)):
    """添加错题"""
    try:
        mid = mistake_db.add(
            user_id=user["id"],
            question=req.question,
            answer=req.answer,
            tags=req.tags,
            source=req.source,
            source_id=req.source_id,
        )
        return {"status": "ok", "id": mid}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/review")
async def get_review(user: dict = Depends(current_user)):
    """获取今日待复习错题列表"""
    items = mistake_db.review_today(user["id"])
    return {"count": len(items), "items": items}


@router.get("/review-count")
async def get_review_count(user: dict = Depends(current_user)):
    """获取今日待复习数量（个人中心红点）"""
    return {"count": mistake_db.review_count(user["id"])}


@router.get("/list")
async def list_mistakes(user: dict = Depends(current_user)):
    """获取全部错题列表"""
    return {"items": mistake_db.list_all(user["id"])}


@router.post("/{mistake_id}/rate")
async def rate_mistake(mistake_id: int, req: RateRequest, user: dict = Depends(current_user)):
    """评分 1-5，更新 SM-2 间隔"""
    if req.rating < 1 or req.rating > 5:
        raise HTTPException(400, "评分范围为 1-5")
    try:
        result = mistake_db.sm2_update(mistake_id, req.rating)
        return {"status": "ok", **result}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.delete("/{mistake_id}")
async def delete_mistake(mistake_id: int, user: dict = Depends(current_user)):
    """删除错题"""
    ok = mistake_db.delete(mistake_id, user["id"])
    if not ok:
        raise HTTPException(404, "错题不存在")
    return {"status": "ok"}
