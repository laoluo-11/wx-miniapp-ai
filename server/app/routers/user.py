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


from pydantic import BaseModel
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
import base64 as _b64

class BindPhoneReq(BaseModel):
    encrypted_data: str
    iv: str

def _decrypt_phone(session_key: str, encrypted_data: str, iv: str) -> str:
    """解密微信加密的手机号"""
    key = _b64.b64decode(session_key)
    iv_bytes = _b64.b64decode(iv)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv_bytes))
    decryptor = cipher.decryptor()
    raw = decryptor.update(_b64.b64decode(encrypted_data)) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    result = unpadder.update(raw) + unpadder.finalize()
    import json
    data = json.loads(result.decode())
    return data.get("purePhoneNumber", "")

@router.post("/bind-phone")
async def bind_phone(req: BindPhoneReq, user: dict = Depends(current_user)):
    """绑定手机号（解密微信 getPhoneNumber 数据）"""
    try:
        phone = _decrypt_phone(user["session_key"], req.encrypted_data, req.iv)
        if not phone:
            raise HTTPException(400, "解密失败")
        # 检查手机号是否已被其他账号绑定
        from app.database import get_db
        with get_db() as db:
            cur = db.cursor()
            cur.execute("SELECT id FROM wx_users WHERE phone = %s AND id != %s", (phone, user["id"]))
            if cur.fetchone():
                raise HTTPException(400, "该手机号已被其他账号绑定")
        update(user["id"], phone=phone)
        return {"msg": "ok", "phone": phone}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"手机号绑定失败: {str(e)[:100]}")

