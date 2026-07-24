from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.utils.auth import current_user
from app.utils.llm_client import chat as llm_chat, chat_stream, gen_title
from app.utils.deep_agent import chat_deep
from app.utils.image_gen import generate_image
from app.utils.svg_render import svg_save
from app.utils.diagram_prompt import DIAGRAM_SYSTEM_PROMPT
from app.utils.memory_manager import build_context, get_all as get_memories, add as add_memory, delete as delete_memory, maybe_compress
from app.models import conversation as conv_db, stats as stats_db
from app.models import message as msg_db
import os, uuid, shutil, json as json_mod, asyncio, re

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

class RenameReq(BaseModel):
    title: str


# ── Diagram ──

DIAGRAM_RE = re.compile(r'<<<(SVG|IMAGE)>>>(.*?)<<<END>>>', re.DOTALL)


# Regex to strip unterminated markers (everything from <<<SVG>>> or <<<IMAGE>>> to end of text)



def _parse_diagrams(text: str) -> tuple:
    """Parse <<<SVG>>>...<<<END>>> / <<<IMAGE>>>...<<<END>>> from LLM reply.
    Also handles unterminated blocks (missing <<<END>>>)."""
    diagrams = []
    # First try complete blocks
    for match in DIAGRAM_RE.finditer(text):
        dtype = match.group(1).lower()
        body = match.group(2).strip()
        if dtype == "svg":
            diagrams.append({"type": "svg", "content": body})
        elif dtype == "image":
            diagrams.append({"type": "image", "prompt": body})
    # Also handle unterminated <<<IMAGE>>> — only when no <<<END>>> exists anywhere
    if not diagrams and "<<<END>>>" not in text:
        for match in re.finditer(r"<<<IMAGE>>>\s*(.+?)$", text, re.DOTALL):
            prompt = match.group(1).strip()
            if prompt:
                diagrams.append({"type": "image", "prompt": prompt})
    # Strip all markers
    clean = DIAGRAM_RE.sub("", text).strip()
    clean = re.sub(r"<<<IMAGE>>>\s*", "", clean).strip()
    clean = re.sub(r"<<<SVG>>>\s*", "", clean).strip()
    return clean, diagrams


async def _process_diagrams(diagrams: list) -> list:
    urls = []
    for d in diagrams:
        try:
            if d["type"] == "svg":
                url = svg_save(d["content"])
                if url:
                    urls.append(url)
                    print(f"[Diagram] SVG saved: {url}")
            elif d["type"] == "image":
                url = await generate_image(d["prompt"])
                if url:
                    urls.append(url)
                    print(f"[Diagram] Image generated: {url}")
        except Exception as e:
            print(f"[Diagram] failed ({d['type']}): {e}")
    return urls


# ── File resolution ──

async def _resolve_file_message(msg: str) -> str:
    RECEIVE_PREFIX_V2 = "https://luois-james.xyz/receive/"
    STATIC_PREFIX = FILE_URL_PREFIX
    if not (msg.startswith(STATIC_PREFIX) or msg.startswith(RECEIVE_PREFIX_V2)):
        return msg
    filename = msg[len(FILE_URL_PREFIX):]
    # receive/ files go to /opt/wx-miniapp-ai/receive/
    RECEIVE_PREFIX = "receive/"
    if msg.startswith("https://luois-james.xyz/receive/"):
        filename = msg[len("https://luois-james.xyz/receive/"):]
        filepath = os.path.join("/opt/wx-miniapp-ai/receive", filename)
        # Handle this as a special case below
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
            try:
                from app.utils.llm_client import _vision_call
                desc = await _vision_call(f"https://luois-james.xyz/receive/{filename}", "详细描述这张图片的内容")
                if desc:
                    return f"[用户上传了图片: {filename}]{NL}图片内容描述:{NL}{desc}{NL}{NL}请根据图片内容回答用户的问题。"
            except Exception:
                pass
            return f"[用户上传了图片: {filename} ({size} bytes)]{NL}图片未能识别，请重试或手动描述。"
        return f"[用户上传了文件: {filename} ({size} bytes, 类型: {ext})]{NL}二进制文件，无法读取内容。请告知用户。"

    # Legacy: static/receive/ prefix
    OLD_RECEIVE = "receive/"
    if filename.startswith(RECEIVE_PREFIX):
        filepath = os.path.join("/opt/wx-miniapp-ai/receive", filename[len(RECEIVE_PREFIX):])
    else:
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
        try:
            from app.utils.llm_client import _vision_call
            desc = await _vision_call(f"https://luois-james.xyz/static/{filename}", "详细描述这张图片的内容")
            if desc:
                return f"[用户上传了图片: {filename}]{NL}图片内容描述:{NL}{desc}{NL}{NL}请根据图片内容回答用户的问题。"
        except Exception:
            pass
        return f"[用户上传了图片: {filename} ({size} bytes)]{NL}图片未能识别，请重试或手动描述。"
    return f"[用户上传了文件: {filename} ({size} bytes, 类型: {ext})]{NL}二进制文件，无法读取内容。请告知用户。"


def _build_system_prompt() -> str:
    return DIAGRAM_SYSTEM_PROMPT


# ── Main send ──

@router.post("/send")
async def send(req: SendReq, user: dict = Depends(current_user)):
    uid = user["id"]
    cid = req.conversation_id
    is_new = cid is None

    if is_new:
        cid = conv_db.create(uid)
    else:
        conv = conv_db.get_by_id(cid, uid)
        if not conv:
            raise HTTPException(404, "对话不存在")

    msg_db.save(cid, "user", req.message)
    processed = await _resolve_file_message(req.message)

    history = msg_db.get_recent_pairs(cid, rounds=10)
    messages = []
    last_idx = len(history) - 1
    for i, h in enumerate(history):
        content = processed if (h["role"] == "user" and i == last_idx) else h["content"]
        messages.append({"role": h["role"], "content": content})

    title = None

    async def generate():
        nonlocal title
        full_reply = ""
        buf = ""          # small buffer for marker detection
        in_diagram = False

        # Phase 1: Stream LLM (filter diagram blocks)
        try:
            async for chunk in chat_stream(messages, uid=uid, system=_build_system_prompt()):
                full_reply += chunk
                buf += chunk

                while True:
                    if in_diagram:
                        # Looking for <<<END>>>
                        end_idx = buf.find("<<<END>>>")
                        if end_idx != -1:
                            buf = buf[end_idx + 9:]  # skip the end marker
                            in_diagram = False
                            continue  # re-check for another start marker
                        else:
                            # Still in diagram, keep 8 chars for partial <<<END>>> detection
                            buf = buf[-8:] if len(buf) > 8 else buf
                            break
                    else:
                        # Looking for <<<SVG>>> or <<<IMAGE>>>
                        svg_idx = buf.find("<<<SVG>>>")
                        img_idx = buf.find("<<<IMAGE>>>")
                        marker_idx = min(svg_idx if svg_idx != -1 else 99999,
                                         img_idx if img_idx != -1 else 99999)
                        if marker_idx != 99999:
                            # Yield everything before the marker
                            if marker_idx > 0:
                                yield buf[:marker_idx]
                            marker_len = 9 if svg_idx == marker_idx else 11
                            marker_type = "SVG" if svg_idx == marker_idx else "IMAGE"
                            buf = buf[marker_idx + marker_len:]
                            in_diagram = True
                            # IMAGE type: silent, just the image will appear
                            continue  # re-check with updated buf
                        else:
                            # No marker found. Yield all but last 11 chars (safety for split <<<IMAGE>>>)
                            safe = max(0, len(buf) - 11)
                            if safe > 0:
                                yield buf[:safe]
                                buf = buf[safe:]
                            break

        except Exception as e:
            yield f"\n[AI服务异常: {str(e)}]"
            return

        # Yield remaining non-diagram buffer
        if not in_diagram and buf:
            yield buf

        # Phase 2: Parse & render diagrams from full_reply
        clean_text, diagrams = _parse_diagrams(full_reply)
        image_urls = await _process_diagrams(diagrams)

        # Phase 3: Save
        save_text = clean_text.strip() or ""
        # SVG diagrams embedded in markdown; creative images saved separately
        for url in image_urls:
            if "/diagram_" in url or url.endswith(".svg"):
                save_text += f"\n\n![diagram]({url})"
            else:
                msg_db.save(cid, "assistant", url)
        if save_text.strip():
            msg_db.save(cid, "assistant", save_text.strip())
        conv_db.touch(cid)

        try:
            asyncio.create_task(_extract_user_memories(uid, messages, save_text.strip() or full_reply))
        except Exception:
            pass

        if is_new:
            try:
                title = await gen_title(processed, uid=uid)
                conv_db.update_title(cid, title)
            except Exception:
                title = req.message[:20]
                conv_db.update_title(cid, title)  # fallback title

        # Phase 4: Meta
        # SVG 示意图已嵌入 markdown 文本，只有创意图片才放入 image_url
        creative_urls = [url for url in image_urls if not ("/diagram_" in url or url.endswith(".svg"))]
        meta = json_mod.dumps({
            "conversation_id": cid,
            "reply": save_text.strip(),
            "title": title,
            "image_url": creative_urls[0] if creative_urls else ""
        }, ensure_ascii=False)
        yield f"\n__META__{meta}"

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")


@router.post("/send-deep")
async def send_deep(req: SendReq, user: dict = Depends(current_user)):
    uid = user["id"]
    cid = req.conversation_id
    is_new = cid is None
    if is_new:
        cid = conv_db.create(uid)
    else:
        conv = conv_db.get_by_id(cid, uid)
        if not conv:
            raise HTTPException(404, "not found")
    msg_db.save(cid, "user", req.message)
    processed = await _resolve_file_message(req.message)
    history = msg_db.get_recent_pairs(cid, rounds=6)
    messages = []
    last_idx = len(history) - 1
    for i, h in enumerate(history):
        content = processed if (h["role"] == "user" and i == last_idx) else h["content"]
        messages.append({"role": h["role"], "content": content})
    try:
        full_reply = await chat_deep(messages, uid=uid, system=_build_system_prompt())
    except Exception as e:
        full_reply = f"[Deep error: {str(e)}]"
    clean_text, diagrams = _parse_diagrams(full_reply)
    image_urls = await _process_diagrams(diagrams)
    save_text = clean_text.strip() or ""
    for url in image_urls:
        if "/diagram_" in url or url.endswith(".svg"):
            save_text += "\n\n![diagram](" + url + ")"
        else:
            msg_db.save(cid, "assistant", url)
    if save_text.strip():
        msg_db.save(cid, "assistant", save_text.strip())
    conv_db.touch(cid)
    title = None
    if is_new:
        try:
            title = await gen_title(processed, uid=uid)
            conv_db.update_title(cid, title)
        except Exception:
            title = req.message[:20]
            conv_db.update_title(cid, title)
    try:
        asyncio.create_task(_extract_user_memories(uid, messages, save_text.strip() or full_reply))
    except Exception:
        pass
    creative_urls = [url for url in image_urls if not ("/diagram_" in url or url.endswith(".svg"))]
    return {
        "conversation_id": cid,
        "reply": save_text.strip(),
        "title": title,
        "image_url": creative_urls[0] if creative_urls else ""
    }

# ── Conversations ──

@router.get("/conversations")
async def list_conversations(user: dict = Depends(current_user)):
    return conv_db.list_by_user(user["id"])

@router.get("/conversations/{cid}/messages")
async def get_messages(cid: int, user: dict = Depends(current_user), limit: int = Query(40, ge=1, le=100), before: int = Query(None)):
    conv = conv_db.get_by_id(cid, user["id"])
    if not conv:
        raise HTTPException(404, "对话不存在")
    messages = msg_db.get_history(cid, before=before, limit=limit)
    return [{"id": m["id"], "role": m["role"], "content": m["content"], "time": str(m.get("created_at", ""))} for m in messages]

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


class BatchDeleteReq(BaseModel):
    ids: list

@router.post("/conversations/{cid}/messages/batch_remove")
async def delete_messages(cid: int, req: BatchDeleteReq, user: dict = Depends(current_user)):
    conv = conv_db.get_by_id(cid, user["id"])
    if not conv:
        raise HTTPException(404, "对话不存在")
    count = msg_db.delete_by_ids(cid, req.ids)
    conv_db.touch(cid)
    return {"deleted": count}


# Legacy DELETE endpoint (may be blocked by Cloudflare)
@router.delete("/conversations/{cid}/messages")
async def delete_messages(cid: int, req: BatchDeleteReq, user: dict = Depends(current_user)):
    conv = conv_db.get_by_id(cid, user["id"])
    if not conv:
        raise HTTPException(404, "对话不存在")
    count = msg_db.delete_by_ids(cid, req.ids)
    conv_db.touch(cid)
    return {"deleted": count}


@router.post("/upload")
async def upload_file(file: UploadFile = File(...), user: dict = Depends(current_user),
                      conversation_id: int = Query(None)):
    uid = user["id"]
    ext = os.path.splitext(file.filename or "file")[1] or ".dat"
    name = f"{uuid.uuid4().hex}{ext}"
    # Save to receive/ directory
    from app.models.file import RECEIVE_DIR, save as file_save
    receive_path = os.path.join(RECEIVE_DIR, name)
    os.makedirs(RECEIVE_DIR, exist_ok=True)
    with open(receive_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    # Determine type
    img_exts = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico"}
    file_type = "image" if ext.lower() in img_exts else "file"
    file_size = os.path.getsize(receive_path) if os.path.exists(receive_path) else 0
    url = f"https://luois-james.xyz/receive/{name}"
    # Record in DB
    file_save(uid, file.filename or name, url, file_size, file_type, conversation_id)
    return {"url": url}


@router.get("/stats")
async def get_stats(user: dict = Depends(current_user)):
    return stats_db.user_stats(user["id"])


# ── Memory ──

async def _extract_user_memories(uid: int, messages: list, reply: str):
    combined = messages[-4:] + [{"role": "assistant", "content": reply}]
    recent = "\n".join(f"{m['role']}: {str(m['content'])[:300]}" for m in combined)
    prompt = f"""从以下对话中提取关于用户的重要新信息（偏好、个人信息、需求等）。
只提取明确陈述的事实，不要推测。每个事实一行。没有新信息时回复"无"。

对话:
{recent}"""
    try:
        from app.utils.llm_client import _call_llm
        result = await _call_llm([{"role": "user", "content": prompt}], model=None,
            system="你是一个事实提取器。只输出事实，每行一条。没有新信息时回复：无",
            temperature=0.1, max_tokens=200, timeout=25)
    except Exception:
        return 0
    lines = [l.strip("- \u2022\u00b71234567890. \t").strip() for l in result.split("\n")]
    facts = [l for l in lines if l and l != "无" and 3 < len(l) < 200]
    count = 0
    existing = get_memories(uid)
    existing_texts = [m["content"][:30] for m in existing]
    for fact in facts[:3]:
        if not any(fact[:20] in ex for ex in existing_texts):
            add_memory(uid, fact)
            count += 1
    if count:
        print(f"[Memory] 为用户 {uid} 提取了 {count} 条新记忆")
    try:
        await maybe_compress(uid, _call_llm)
    except Exception:
        pass


class MemoryReq(BaseModel):
    content: str

@router.get("/memories")
async def list_memories(user: dict = Depends(current_user)):
    return get_memories(user["id"])

@router.post("/memories")
async def create_memory(req: MemoryReq, user: dict = Depends(current_user)):
    mid = add_memory(user["id"], req.content)
    return {"id": mid, "msg": "ok"}

@router.delete("/memories/{mid}")
async def remove_memory(mid: int, user: dict = Depends(current_user)):
    all_mem = get_memories(user["id"])
    if not any(m["id"] == mid for m in all_mem):
        raise HTTPException(404, "记忆不存在")
    delete_memory(mid)
    return {"msg": "ok"}
