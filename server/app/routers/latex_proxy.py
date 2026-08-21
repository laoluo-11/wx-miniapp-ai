"""
LaTeX 公式渲染代理 — 本地 MathJax 常驻服务，毫秒级渲染
"""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
import os, hashlib, urllib.parse, httpx

router = APIRouter(prefix="/api/latex", tags=["LaTeX"])

RENDER_URL = "http://127.0.0.1:9123/render"
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "uploads", "latex")
os.makedirs(CACHE_DIR, exist_ok=True)
STATIC_BASE = "https://yyzhilingweilai.com/static/latex/"


async def _render_latex(tex: str) -> str:
    """调用常驻 MathJax 服务渲染"""
    async with httpx.AsyncClient(timeout=5) as c:
        r = await c.post(RENDER_URL, content=tex)
        if r.status_code != 200:
            raise Exception(f"MathJax error: {r.text[:200]}")
        return r.text


@router.get("")
async def render(request: Request):
    """代理 LaTeX 渲染 → 302 到缓存静态文件"""
    tex = request.url.query.replace("tex=", "", 1)
    if not tex:
        raise HTTPException(400, "缺少 tex 参数")

    key = hashlib.md5((tex + "|v2").encode()).hexdigest()
    cached = os.path.join(CACHE_DIR, f"{key}.svg")

    if not os.path.exists(cached) or os.path.getsize(cached) < 100:
        try:
            decoded = urllib.parse.unquote(tex)
            svg = await _render_latex(decoded)
            with open(cached, "w", encoding="utf-8") as f:
                f.write(svg)
        except Exception:
            err = (
                '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="22">'
                '<rect width="100%" height="100%" fill="transparent"/>'
                '<text y="16" fill="red" font-size="10">render error</text></svg>'
            )
            with open(cached, "w", encoding="utf-8") as f:
                f.write(err)

    return RedirectResponse(url=f"{STATIC_BASE}{key}.svg")
