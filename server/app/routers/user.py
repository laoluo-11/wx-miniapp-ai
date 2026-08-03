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
            "role": user.get("role", "user"), "vip_expires_at": str(user.get("vip_expires_at")) if user.get("vip_expires_at") else None,
            "created_at": str(user.get("created_at", ""))}

@router.put("/profile")
async def profile(req: UpdateReq, user: dict = Depends(current_user)):
    kw = {}
    if req.nickname is not None: kw["nickname"] = req.nickname
    if req.avatar_url is not None: kw["avatar_url"] = req.avatar_url
    if not kw: raise HTTPException(400, "no fields")
    update(user["id"], **kw)
    return {"msg": "ok"}

@router.get("/usage")
async def my_usage(user: dict = Depends(current_user)):
    from app.utils.usage import get_today, get_limits
    return {
        "usage": get_today(user["id"]),
        "limits": get_limits(user.get("role", "user")),
        "role": user.get("role", "user"),
        "vip_expires_at": str(user.get("vip_expires_at")) if user.get("vip_expires_at") else None
    }


# --- Phone binding (WeChat new code-based API) ---

import httpx
from app.config import WX_APPID, WX_SECRET

class BindPhoneReq(BaseModel):
    code: str | None = None
    encrypted_data: str | None = None
    iv: str | None = None

async def _get_access_token() -> str:
    """Get mini program access_token with simple in-memory cache"""
    import time
    if hasattr(_get_access_token, "_cache"):
        tok, exp = _get_access_token._cache
        if time.time() < exp - 60:
            return tok

    url = "https://api.weixin.qq.com/cgi-bin/token"
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(url, params={
            "grant_type": "client_credential",
            "appid": WX_APPID,
            "secret": WX_SECRET
        })
        data = r.json()
        if "access_token" in data:
            _get_access_token._cache = (data["access_token"], time.time() + data.get("expires_in", 7200))
            return data["access_token"]
        raise Exception(f"get access_token failed: {data}")

async def _get_phone_by_code(code: str) -> str | None:
    """New API: exchange code for phone number"""
    token = await _get_access_token()
    url = "https://api.weixin.qq.com/wxa/business/getuserphonenumber"
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(url, params={"access_token": token}, json={"code": code})
        data = r.json()
        if data.get("errcode") == 0:
            return data["phone_info"]["phoneNumber"]
        print(f"[Phone] getuserphonenumber failed: {data}")
        return None

# Old AES decrypt (fallback)
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
import base64 as _b64

def _decrypt_phone(session_key: str, encrypted_data: str, iv: str) -> str:
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
    """Bind phone (new code API, fallback old encrypted_data)"""
    try:
        if req.code:
            phone = await _get_phone_by_code(req.code)
        elif req.encrypted_data:
            phone = _decrypt_phone(user["session_key"], req.encrypted_data, req.iv)
        else:
            raise HTTPException(400, "missing code or encrypted_data")

        if not phone:
            raise HTTPException(400, "failed to get phone number")

        from app.database import get_db
        with get_db() as db:
            cur = db.cursor()
            cur.execute("SELECT id FROM wx_users WHERE phone = %s AND id != %s", (phone, user["id"]))
            if cur.fetchone():
                raise HTTPException(400, "phone already bound to another account")
        update(user["id"], phone=phone)
        return {"msg": "ok", "phone": phone}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"phone bind failed: {str(e)[:100]}")
