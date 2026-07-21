from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel
from app.utils.auth import current_user
from app.utils.llm_client import chat as llm_chat, gen_title
from app.utils.memory_manager import build_context, get_all as get_memories, add as add_memory, delete as delete_memory, maybe_compress
from app.models import conversation as conv_db
from app.models import message as msg_db
import os, uuid, shutil

router = APIRouter(prefix="/api/v1/chat", tags=["Chat"])
UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "..", "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

FILE_URL_PREFIX = "https://luois-james.xyz/static/"

TEXT_EXTENSIONS = {'.txt','.md','.py','.js','.json','.xml','.html','.css',
                   '.csv','.yaml','.yml','.toml','.ini','.cfg','.conf',
                   '.log','.sh','.bat','.sql','.java','.c','.cpp','.h',
                   '.rs','.go','.rb','.php','.ts','.tsx','.jsx','.vue',
                   '.wxml','.wxss','.scss','.less','.env','.gitignore'}

IMAGE_EXTENSIONS = {'.jpg','.jpeg','.png','.gif','.bmp','.webp','.svg','.ico'}


class SendReq(BaseModel):
    conversation_id: int | None = None
    message: str

class SendResp(BaseModel):
    conversation_id: int
    reply: str
    title: str | None = None

class RenameReq(BaseModel):
    title: str


def _resolve_file_message(msg: str) -> str:
    """Detect and resolve file URLs from our own server."""
    if not msg.startswith(FILE_URL_PREFIX):
        return msg

    filename = msg[len(FILE_URL_PREFIX):]
    filepath = os.path.join(UPLOAD_DIR, filename)
    NL = "\n"

    if not os.path.exists(filepath):
        return f"[用户上传了文件: {filename}，但文件未找到]{NL}请告知用户文件可能已过期。"

    size = os.path.getsize(filepath)
    ext = os.path.splitext(filename)[1].lower()

    if ext in TEXT_EXTENSIONS:
        content = None
        for enc in ('utf-8', 'gbk', 'latin-1'):
            try:
                with open(filepath, 'r', encoding=enc) as f:
                    content = f.read()
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
        if content is None:
            return f"[用户上传了文件: {filename} ({size} bytes)]{NL}文件无法解码为文本。"
        limit = 6000
        if len(content) > limit:
            content = content[:limit] + f"{NL}{NL}... (文件共 {len(content)} 字符，仅展示前 {limit})"
        return f"[用户上传了文件: {filename}]{NL}文件内容:{NL}{content}{NL}{NL}请分析这个文件的内容并回答用户。"

    if ext in IMAGE_EXTENSIONS:
        return f"[用户上传了图片: {filename} ({size} bytes)]{NL}我无法直接查看图片内容。请告知用户。"

    return f"[用户上传了文件: {filename} ({size} bytes, 类型: {ext})]{NL}二进制文件，无法读取内容。请告知用户。"


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
    processed = _resolve_file_message(req.message)

    history = msg_db.get_recent_pairs(cid, rounds=10)
    messages = []
    last_idx = len(history) - 1
    for i, h in enumerate(history):
        content = processed if (h["role"] == "user" and i == last_idx) else h["content"]
        messages.append({"role": h["role"], "content": content})

    try:
        reply = await llm_chat(messages, uid=uid)
    except Exception as e:
        raise HTTPException(500, f"AI服务异常: {str(e)}")

    msg_db.save(cid, "assistant", reply)
    conv_db.touch(cid)

    # 异步提取用户记忆（不阻塞回复）
    try:
        import asyncio
        asyncio.create_task(_extract_user_memories(uid, messages, reply))
    except Exception:
        pass  # 记忆提取失败不影响主流程

    if is_new:
        try:
            title = await gen_title(processed if is_new else req.message)
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


# === 用户记忆管理 ===

async def _extract_user_memories(uid: int, messages: list, reply: str):
    """后台提取用户记忆"""
    # 合并对话内容进行分析
    combined = messages[-4:] + [{"role": "assistant", "content": reply}]
    recent = "\n".join(
        f"{m['role']}: {str(m['content'])[:300]}" for m in combined
    )
    prompt = f"""从以下对话中提取关于用户的重要新信息（偏好、个人信息、需求等）。
只提取明确陈述的事实，不要推测。每个事实一行。没有新信息时回复"无"。

对话:
{recent}"""

    try:
        from app.utils.llm_client import _call_llm
        result = await _call_llm(
            [{"role": "user", "content": prompt}],
            model=None,
            system="你是一个事实提取器。只输出事实，每行一条。没有新信息时回复：无", 
            temperature=0.1, max_tokens=200, timeout=25
        )
    except Exception:
        return 0

    lines = [l.strip("- •·1234567890. \t").strip() for l in result.split("\n")]
    facts = [l for l in lines if l and l != "无" and 3 < len(l) < 200]
    
    count = 0
    existing = get_memories(uid)
    existing_texts = [m["content"][:30] for m in existing]
    for fact in facts[:3]:
        # 检查是否重复
        if not any(fact[:20] in ex for ex in existing_texts):
            add_memory(uid, fact)
            count += 1
    if count:
        print(f"[Memory] 为用户 {uid} 提取了 {count} 条新记忆")
    # 如果记忆太多，压缩旧的
    try:
        await maybe_compress(uid, _call_llm)
    except Exception:
        pass


class MemoryReq(BaseModel):
    content: str

@router.get("/memories")
async def list_memories(user: dict = Depends(current_user)):
    """获取当前用户的所有长期记忆"""
    return get_memories(user["id"])

@router.post("/memories")
async def create_memory(req: MemoryReq, user: dict = Depends(current_user)):
    """手动添加一条用户记忆"""
    mid = add_memory(user["id"], req.content)
    return {"id": mid, "msg": "ok"}

@router.delete("/memories/{mid}")
async def remove_memory(mid: int, user: dict = Depends(current_user)):
    """删除一条记忆"""
    # 验证记忆属于当前用户
    all_mem = get_memories(user["id"])
    if not any(m["id"] == mid for m in all_mem):
        raise HTTPException(404, "记忆不存在")
    delete_memory(mid)
    return {"msg": "ok"}
