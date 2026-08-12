from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.routers import auth, user, chat, voice, latex_proxy, admin, knowledge, mistake, oral_question, material
import os

app = FastAPI(title="AI Chat API", version="1.0", docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

# 静态文件服务（上传文件访问）
UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)
# User uploads mounted BEFORE /static to avoid prefix conflict
RECEIVE_DIR = "/opt/wx-miniapp-ai-dev/receive"
os.makedirs(RECEIVE_DIR, exist_ok=True)
app.mount("/receive", StaticFiles(directory=RECEIVE_DIR), name="receive")

app.mount("/static", StaticFiles(directory=UPLOAD_DIR), name="static")


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code, content={"message": exc.detail})

app.include_router(auth.router)
app.include_router(user.router)
app.include_router(chat.router)
app.include_router(voice.router)
app.include_router(latex_proxy.router)
app.include_router(admin.router)
app.include_router(knowledge.router)
app.include_router(mistake.router)
app.include_router(oral_question.router)
app.include_router(material.router)

@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    with open("/opt/wx-miniapp-ai-dev/admin/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/")
async def root(): return {"service": "AI Chat Server", "version": "1.0"}


@app.on_event("startup")
async def startup_rag():
    """启动时初始化 RAG 知识库服务"""
    from app.services.rag_service import RAGService
    RAGService.initialize()

@app.get("/health")
async def health(): return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    from app.config import HOST, PORT, DEBUG
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=DEBUG)