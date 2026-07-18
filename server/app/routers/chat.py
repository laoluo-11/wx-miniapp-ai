from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel
from app.utils.auth import current_user
from app.utils.llm_client import chat as llm_chat, gen_title
from app.models import conversation as conv_db
from app.models import message as msg_db
import os, uuid, shutil

router = APIRouter(prefix="/api/v1/chat", tags=["Chat"])
UPLOAD_DIR = "/home/dfzz/wx-miniapp-ai/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

class SendReq(BaseModel):
    conversation_id: int | None = None
    message: str

class SendResp(BaseModel):
    conversation_id: int
    reply: str
    title: str | None = None

class RenameReq(BaseModel):
    title: str

@router.post("/send", response_model=SendResp)
async def send(req: SendReq, user: dict = Depends(current_user)):
    uid = user["id"]
    cid = req.conversation_id
    is_new = cid is None
    title = None

    if is_new:
        cid = conv_db.create(uid)
    else:
        conv = conv_db.get_by_id(cid, uid)
        if not conv:
            raise HTTPException(404, "对话不存在")

    msg_db.save(cid, "user", req.message)
    history = msg_db.get_recent_pairs(cid, rounds=10)
    messages = [{"role": h["role"], "content": h["content"]} for h in history]

    try:
        reply = await llm_chat(messages)
    except Exception as e:
        raise HTTPException(500, f"AI服务异常: {str(e)}")

    msg_db.save(cid, "assistant", reply)
    conv_db.touch(cid)

    if is_new:
        try:
            title = await gen_title(req.message)
            conv_db.update_title(cid, title)
        except Exception:
            title = req.message[:20]

    return SendResp(conversation_id=cid, reply=reply, title=title)

@router.get("/conversations")
async def list_conversations(user: dict = Depends(current_user)):
    return conv_db.list_by_user(user["id"])

@router.get("/conversations/{cid}/messages")
async def get_messages(
    cid: int,
    user: dict = Depends(current_user),
    limit: int = Query(40, ge=1, le=100),
    before: int = Query(None),
):
    conv = conv_db.get_by_id(cid, user["id"])
    if not conv:
        raise HTTPException(404, "对话不存在")
    messages = msg_db.get_history(cid, before=before, limit=limit)
    # 前端期望扁平数组，每条带 time 字段
    return [{"role": m["role"], "content": m["content"], "time": str(m.get("created_at", ""))} for m in messages]

@router.put("/conversations/{cid}")
async def rename_conversation(cid: int, req: RenameReq, user: dict = Depends(current_user)):
    conv = conv_db.get_by_id(cid, user["id"])
    if not conv:
        raise HTTPException(404, "对话不存在")
    conv_db.update_title(cid, req.title)
    return {"msg": "ok"}

@router.delete("/conversations/{cid}")
async def delete_conversation(cid: int, user: dict = Depends(current_user)):
    ok = conv_db.delete(cid, user["id"])
    if not ok:
        raise HTTPException(404, "对话不存在")
    return {"msg": "ok"}

@router.post("/upload")
async def upload_file(file: UploadFile = File(...), user: dict = Depends(current_user)):
    ext = os.path.splitext(file.filename or "file")[1] or ".dat"
    name = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(UPLOAD_DIR, name)
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    url = f"https://luois-james.xyz/static/{name}"
    return {"url": url}

