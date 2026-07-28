from fastapi import Header, HTTPException
from app.models.session import validate as validate_token

async def current_user(authorization: str = Header(None)) -> dict:
    if not authorization:
        raise HTTPException(401, "缺少 Authorization 头")
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "格式错误，应为 Bearer <token>")
    user = validate_token(authorization[7:])
    if not user:
        raise HTTPException(401, "Token 无效或已过期")
    # VIP 自动降级
    if user.get("role") == "vip" and user.get("vip_expires_at"):
        from datetime import datetime
        from app.database import get_db
        if user["vip_expires_at"] < datetime.now():
            with get_db() as db:
                db.cursor().execute(
                    "UPDATE wx_users SET role='user', vip_expires_at=NULL WHERE id=%s",
                    (user["id"],)
                )
            user["role"] = "user"
            user["vip_expires_at"] = None
    return user