"""
知识库 API — RAG 检索接口
"""
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from app.services.rag_service import RAGService

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


# ── Request/Response Models ──

class ImportItem(BaseModel):
    id: Optional[str] = None
    text: str
    metadata: Optional[dict] = None


class ImportRequest(BaseModel):
    collection: str
    items: list[ImportItem]


class SearchRequest(BaseModel):
    collection: str
    query: str
    top_k: int = 5
    filters: Optional[dict] = None


class SearchResult(BaseModel):
    id: str
    text: str
    metadata: dict = {}
    distance: float = 0.0


# ── API Endpoints ──

@router.get("/collections")
async def list_collections():
    """列出所有知识库集合"""
    return {"collections": RAGService.list_collections()}


@router.get("/{collection}/count")
async def get_count(collection: str):
    """获取集合中的文档数量"""
    try:
        return {"collection": collection, "count": RAGService.count(collection)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import")
async def import_knowledge(req: ImportRequest):
    """批量导入知识条目"""
    try:
        docs = [item.text for item in req.items]
        metas = [item.metadata or {} for item in req.items]
        ids = [item.id for item in req.items if item.id] or None

        count = RAGService.add(
            collection_name=req.collection,
            documents=docs,
            metadatas=metas,
            ids=ids,
        )
        return {"status": "ok", "collection": req.collection, "imported": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search")
async def search_knowledge(req: SearchRequest):
    """语义检索"""
    try:
        results = RAGService.search(
            collection_name=req.collection,
            query=req.query,
            top_k=req.top_k,
            where=req.filters,
        )
        return {"collection": req.collection, "query": req.query, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{collection}/{item_id}")
async def delete_item(collection: str, item_id: str):
    """删除单条知识"""
    try:
        RAGService.delete(collection, [item_id])
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
