import httpx
from app.config import WX_APPID, WX_SECRET

WX_URL = "https://api.weixin.qq.com/sns/jscode2session"

async def code2session(code: str) -> dict:
    params = {"appid": WX_APPID, "secret": WX_SECRET, "js_code": code, "grant_type": "authorization_code"}
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(WX_URL, params=params)
        data = r.json()
    if "errcode" in data and data["errcode"] != 0:
        raise Exception(f"微信API错误: {data.get('errmsg')} (code={data['errcode']})")
    return data
