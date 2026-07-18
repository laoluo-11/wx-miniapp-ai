from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.utils.auth import current_user
from app.models.user import get_by_id, update

router = APIRouter(prefix="/api/v1/user", tags=["User"])

class UpdateReq(BaseModel):
    nickname: str | None = None
    avatar_url: str | None = None

@router.get("/info")
async def info(user: dict = Depends(current_user)):
    return {"id": user["id"], "openid": user["openid"], "nickname": user.get("nickname"),
            "avatar_url": user.get("avatar_url"), "phone": user.get("phone"),
            "created_at": str(user.get("created_at", ""))}

@router.put("/profile")
async def profile(req: UpdateReq, user: dict = Depends(current_user)):
    kw = {}
    if req.nickname is not None: kw["nickname"] = req.nickname
    if req.avatar_url is not None: kw["avatar_url"] = req.avatar_url
    if not kw: raise HTTPException(400, "无更新字段")
    update(user["id"], **kw)
    return {"msg": "ok"}
