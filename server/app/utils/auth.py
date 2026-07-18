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
    return user
