"""
学习资料 API — 上传/列表/删除（上传异步：秒返，后台解析+向量化）
"""
import os
import uuid
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks
from app.utils.auth import current_user
from app.models import material as mat_db
from app.services.material_parser import parse_file
from app.services.rag_service import RAGService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/materials", tags=["materials"])

UPLOAD_DIR = "/opt/wx-miniapp-ai-dev/uploads/materials"


@router.post("/upload")
async def upload_material(
    file: UploadFile = File(...),
    user: dict = Depends(current_user),
    background_tasks: BackgroundTasks = None
):
    """上传学习资料，秒返 processing，后台解析+向量化"""
    if not file.filename:
        raise HTTPException(400, "文件名不能为空")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".pdf", ".docx", ".doc", ".txt", ".md"):
        raise HTTPException(400, f"不支持的文件格式: {ext}")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}_{file.filename}"
    filepath = os.path.join(UPLOAD_DIR, safe_name)

    # 保存文件（快）
    size = 0
    with open(filepath, "wb") as f:
        while chunk := await file.read(1024 * 64):
            f.write(chunk)
            size += len(chunk)

    file_url = f"/static/materials/{safe_name}"

    # 数据库记录（状态 processing）
    mid = mat_db.add(user["id"], file.filename, file_url, size)

    # 后台：解析 + 向量化 + 更新状态
    background_tasks.add_task(_process_material, mid, filepath, file.filename, user["id"])

    return {"status": "processing", "id": mid, "filename": file.filename}


def _process_material(mid: int, filepath: str, filename: str, user_id: int):
    """后台处理：解析分段 → 向量化 → 更新状态（复用进程内 RAGService 单例，不重复加载模型）"""
    try:
        chunks = parse_file(filepath, filename)
        if not chunks:
            mat_db.update_status(mid, "failed")
            return
        docs = []
        metas = []
        ids_list = []
        for i, chunk in enumerate(chunks):
            docs.append(chunk)
            metas.append({"material_id": mid, "user_id": user_id,
                          "filename": filename, "chunk_index": i})
            ids_list.append(f"mat_{mid}_{i}")
        RAGService.add("study_materials", documents=docs, metadatas=metas, ids=ids_list)
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
        filepath = os.path.join("/opt/wx-miniapp-ai-dev", file_url.lstrip("/"))
        if os.path.exists(filepath):
            os.remove(filepath)
    except Exception:
        pass

    return {"status": "ok"}
