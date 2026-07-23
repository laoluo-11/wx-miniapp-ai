"""
LaTeX 公式渲染代理
"""
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
import httpx, os, hashlib
from urllib.parse import quote

router = APIRouter(prefix="/api/latex", tags=["LaTeX"])

CODEGOGS = "https://latex.codecogs.com/svg.latex?%5Ccolor%7Bwhite%7D%20"
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "uploads", "latex")
os.makedirs(CACHE_DIR, exist_ok=True)
STATIC_BASE = "https://luois-james.xyz/static/latex/"


@router.get("")
async def render(request: Request):
    """代理 LaTeX 渲染"""
    # 获取原始查询字符串（保持编码）
    tex = request.url.query.replace("tex=", "", 1)
    if not tex:
        return RedirectResponse(url=CODEGOGS)

    key = hashlib.md5(tex.encode()).hexdigest()
    cached = os.path.join(CACHE_DIR, f"{key}.svg")

    if not os.path.exists(cached):
        url = CODEGOGS + tex
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return RedirectResponse(url=url)
            with open(cached, "wb") as f:
                f.write(r.content)

    return RedirectResponse(url=f"{STATIC_BASE}{key}.svg")
