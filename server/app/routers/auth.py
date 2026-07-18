from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from app.utils.wx_api import code2session
from app.models.user import find_or_create
from app.models.session import create as create_session, delete as delete_session

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])

class LoginReq(BaseModel): code: str

class LoginResp(BaseModel):
    token: str
    user_id: int
    openid: str
    is_new: bool

@router.post("/login", response_model=LoginResp)
async def login(req: LoginReq):
    try:
        wx = await code2session(req.code)
    except Exception as e:
        raise HTTPException(400, str(e))
    user = find_or_create(wx["openid"], wx.get("unionid"))
    is_new = not user.get("nickname")
    token = create_session(user["id"], wx["session_key"])
    return LoginResp(token=token, user_id=user["id"], openid=wx["openid"], is_new=is_new)

@router.post("/logout")
async def logout(auth: str = Header(None)):
    if auth and auth.startswith("Bearer "):
        delete_session(auth[7:])
    return {"msg": "ok"}
