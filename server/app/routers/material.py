"""
学习资料 API — 上传/列表/删除（上传异步：秒返，后台解析+向量化）
"""
import os
import uuid
import logging
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, BackgroundTasks
from app.utils.auth import current_user
from app.models import material as mat_db
from app.services.material_parser import parse_file
from app.services.rag_service import RAGService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/materials", tags=["materials"])

UPLOAD_DIR = "/opt/wx-miniapp-ai/uploads/materials"


@router.post("/upload")
async def upload_material(
    file: UploadFile = File(...),
    user: dict = Depends(current_user),
    background_tasks: BackgroundTasks = None,
    filename: str = Form("")
):
    """上传学习资料，秒返 processing，后台解析+向量化"""
    # 优先用前端 formData 传的原始文件名，否则用 multipart 的 file.filename（可能是临时路径哈希名）
    original_name = (filename or "").strip() or file.filename
    if not original_name:
        raise HTTPException(400, "文件名不能为空")

    ext = os.path.splitext(original_name)[1].lower()
    if ext not in (".pdf", ".docx", ".doc", ".txt", ".md"):
        raise HTTPException(400, f"不支持的文件格式: {ext}")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    # 磁盘文件名清洗路径分隔符，防注入；数据库仍存原始名（显示友好）
    safe_disk = original_name.replace("/", "_").replace("\\", "_")
    safe_name = f"{uuid.uuid4().hex}_{safe_disk}"
    filepath = os.path.join(UPLOAD_DIR, safe_name)

    # 保存文件（快）
    size = 0
    with open(filepath, "wb") as f:
        while chunk := await file.read(1024 * 64):
            f.write(chunk)
            size += len(chunk)

    file_url = f"/static/materials/{safe_name}"

    # 数据库记录（状态 processing）
    mid = mat_db.add(user["id"], original_name, file_url, size)

    # 后台：解析 + 向量化 + 更新状态
    background_tasks.add_task(_process_material, mid, filepath, original_name, user["id"])

    return {"status": "processing", "id": mid, "filename": original_name}


def _process_material(mid: int, filepath: str, filename: str, user_id: int):
    """后台处理：解析分段 → 向量化 → 更新状态（复用进程内 RAGService 单例，不重复加载模型）"""
    try:
        chunks = parse_file(filepath, filename)
        if not chunks:
            mat_db.update_status(mid, "failed")
            return
        BATCH = 8
        for i in range(0, len(chunks), BATCH):
            batch = chunks[i:i+BATCH]
            metas = [{"material_id": mid, "user_id": user_id,
                      "filename": filename, "chunk_index": i+j} for j in range(len(batch))]
            ids_list = [f"mat_{mid}_{i+j}" for j in range(len(batch))]
            RAGService.add("study_materials", documents=batch, metadatas=metas, ids=ids_list)
        mat_db.update_status(mid, "ready", len(chunks))
        logger.info("Material %d processed: %d chunks", mid, len(chunks))
    except Exception as e:
        logger.error("Material %d failed: %s", mid, e)
        mat_db.update_status(mid, "failed")


@router.get("/list")
async def list_materials(user: dict = Depends(current_user)):
    """我的资料列表"""
    items = mat_db.list_by_user(user["id"])
    return {"items": items}


@router.delete("/{material_id}")
async def delete_material(material_id: int, user: dict = Depends(current_user)):
    """删除资料及关联文件"""
    result = mat_db.delete(material_id, user["id"])
    if not result:
        raise HTTPException(404, "资料不存在")
    ok, file_url = result

    # 删除文件
    try:
        filepath = os.path.join("/opt/wx-miniapp-ai", file_url.lstrip("/"))
        if os.path.exists(filepath):
            os.remove(filepath)
    except Exception:
        pass

    return {"status": "ok"}
