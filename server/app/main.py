from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.routers import auth, user, chat, voice
import os

app = FastAPI(title="AI Chat API", version="1.0", docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

# 静态文件服务（上传文件访问）
os.makedirs("/home/dfzz/wx-miniapp-ai/uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="/home/dfzz/wx-miniapp-ai/uploads"), name="static")

@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    return JSONResponse(status_code=exc.status_code, content={"message": exc.detail})

app.include_router(auth.router)
app.include_router(user.router)
app.include_router(chat.router)
app.include_router(voice.router)

@app.get("/")
async def root(): return {"service": "AI Chat Server", "version": "1.0"}

@app.get("/health")
async def health(): return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    from app.config import HOST, PORT, DEBUG
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=DEBUG)

