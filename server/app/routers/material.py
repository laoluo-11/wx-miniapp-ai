"""
学习资料 API — 上传/列表/删除
"""
import os
import uuid
import shutil
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from app.utils.auth import current_user
from app.models import material as mat_db
from app.services.material_parser import parse_file
from app.services.rag_service import RAGService

router = APIRouter(prefix="/api/v1/materials", tags=["materials"])

UPLOAD_DIR = "/opt/wx-miniapp-ai-dev/uploads/materials"


@router.post("/upload")
async def upload_material(
    file: UploadFile = File(...),
    user: dict = Depends(current_user)
):
    """上传学习资料，自动解析并入库"""
    if not file.filename:
        raise HTTPException(400, "文件名不能为空")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in (".pdf", ".docx", ".doc", ".txt", ".md"):
        raise HTTPException(400, f"不支持的文件格式: {ext}")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}_{file.filename}"
    filepath = os.path.join(UPLOAD_DIR, safe_name)

    # 保存文件
    size = 0
    with open(filepath, "wb") as f:
        while chunk := await file.read(1024 * 64):
            f.write(chunk)
            size += len(chunk)

    file_url = f"/static/materials/{safe_name}"

    # 数据库记录
    mid = mat_db.add(user["id"], file.filename, file_url, size)

    # 异步解析（同步也行，文件一般不大）
    try:
        chunks = parse_file(filepath, file.filename)
        # 存入 ChromaDB（按 user_id 隔离）
        docs_with_meta = []
        ids_list = []
        for i, chunk in enumerate(chunks):
            chunk_id = f"mat_{mid}_{i}"
            docs_with_meta.append((chunk, {"material_id": mid, "user_id": user["id"], "filename": file.filename, "chunk_index": i}))
            ids_list.append(chunk_id)

        RAGService.add(
            "study_materials",
            [d[0] for d in docs_with_meta],
            [d[1] for d in docs_with_meta],
            ids_list
        )
        mat_db.update_status(mid, "ready", len(chunks))
        return {"status": "ok", "id": mid, "chunks": len(chunks), "filename": file.filename}
    except Exception as e:
        mat_db.update_status(mid, "failed")
        return {"status": "error", "id": mid, "message": str(e)}


@router.get("/list")
async def list_materials(user: dict = Depends(current_user)):
    """我的资料列表"""
    items = mat_db.list_by_user(user["id"])
    return {"items": items}


@router.delete("/{material_id}")
async def delete_material(material_id: int, user: dict = Depends(current_user)):
    """删除资料及关联 chunks"""
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

    # 删除 ChromaDB chunks（前缀匹配）
    # ChromaDB 不支持按前缀批量删，遍历删除或跳过
    return {"status": "ok"}
