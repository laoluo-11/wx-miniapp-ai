"""
RAG 知识库检索服务 — 单例模式
基于 ChromaDB + 阿里云 DashScope text-embedding API（零本地模型内存）
"""
import logging
import os
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

logger = logging.getLogger(__name__)

# embedding 走阿里云 DashScope API（复用 QWEN_API_KEY），不再本地加载 torch 模型
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v4")
EMBEDDING_BASE_URL = os.getenv(
    "QWEN_BASE_URL",
    "https://ws-vvchkx3qqa728hg2.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
)
PERSIST_DIR = os.getenv("RAG_PERSIST_DIR", "/opt/wx-miniapp-ai/server/data/chroma_db")


class RAGService:
    """RAG 检索服务单例"""

    _instance: Optional["RAGService"] = None
    _client: Optional[chromadb.PersistentClient] = None

    def __init__(self):
        raise RuntimeError("Use RAGService.initialize() instead of constructor")

    @classmethod
    def initialize(cls, persist_dir: str | None = None) -> "RAGService":
        """初始化 ChromaDB 客户端（embedding 走 API，无需加载模型）"""
        if cls._instance is not None:
            return cls._instance

        cls._instance = super().__new__(cls)
        _dir = persist_dir or PERSIST_DIR
        os.makedirs(_dir, exist_ok=True)

        cls._client = chromadb.PersistentClient(
            path=_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        logger.info(f"RAGService initialized, persist_dir={_dir}")
        return cls._instance

    @classmethod
    def _embed_texts(cls, texts: list[str]) -> list[list[float]]:
        """调用阿里云 DashScope embedding API 编码文本，返回等长向量列表"""
        import httpx

        api_key = os.getenv("QWEN_API_KEY", "")
        if not api_key:
            raise RuntimeError("QWEN_API_KEY not set")

        _BATCH = 10
        out: list[list[float]] = []
        for i in range(0, len(texts), _BATCH):
            batch = texts[i:i + _BATCH]
            r = httpx.post(
                f"{EMBEDDING_BASE_URL}/embeddings",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": EMBEDDING_MODEL, "input": batch},
                timeout=60,
            )
            r.raise_for_status()
            data = r.json().get("data", [])
            if len(data) == 1 and "index" not in data[0]:
                # 单条输入时无 index 字段
                out.append(data[0]["embedding"])
            else:
                # 批量输入按 index 还原顺序
                for item in sorted(data, key=lambda x: x.get("index", 0)):
                    out.append(item["embedding"])
        return out

    @classmethod
    def _get_collection(cls, name: str):
        if cls._client is None:
            raise RuntimeError("RAGService not initialized. Call RAGService.initialize() first.")
        return cls._client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

    @classmethod
    def add(
        cls,
        collection_name: str,
        documents: list[str],
        metadatas: list[dict] | None = None,
        ids: list[str] | None = None,
    ) -> int:
        """批量添加文档，返回添加数量"""
        embeddings = cls._embed_texts(documents)

        if ids is None:
            import uuid
            ids = [str(uuid.uuid4()) for _ in documents]
        if metadatas is None:
            metadatas = [{} for _ in documents]
        # ChromaDB 拒绝空 metadata（报 Expected metadata to be a non-empty dict），填默认值
        metadatas = [m if m else {"source": "manual"} for m in metadatas]

        collection = cls._get_collection(collection_name)
        collection.add(embeddings=embeddings, documents=documents, metadatas=metadatas, ids=ids)
        logger.info(f"Added {len(documents)} docs to '{collection_name}'")
        return len(documents)

    @classmethod
    def search(
        cls,
        collection_name: str,
        query: str,
        top_k: int = 5,
        where: dict | None = None,
    ) -> list[dict]:
        """语义检索，返回 [{id, text, metadata, distance}]"""
        query_embedding = cls._embed_texts([query])

        collection = cls._get_collection(collection_name)
        results = collection.query(
            query_embeddings=query_embedding,
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        items = []
        if results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                items.append({
                    "id": results["ids"][0][i],
                    "text": results["documents"][0][i] if results["documents"] else "",
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": round(results["distances"][0][i], 4) if results["distances"] else 0,
                })
        return items

    @classmethod
    def delete(cls, collection_name: str, ids: list[str]) -> int:
        """批量删除"""
        collection = cls._get_collection(collection_name)
        collection.delete(ids=ids)
        return len(ids)

    @classmethod
    def count(cls, collection_name: str) -> int:
        """文档数量"""
        return cls._get_collection(collection_name).count()

    @classmethod
    def delete_collection(cls, collection_name: str) -> bool:
        """删除整个集合"""
        if cls._client is None:
            return False
        try:
            cls._client.delete_collection(collection_name)
            logger.info(f"Deleted collection '{collection_name}'")
            return True
        except Exception as e:
            logger.warning(f"Failed to delete collection '{collection_name}': {e}")
            return False

    @classmethod
    def create_collection(cls, collection_name: str) -> bool:
        """创建集合（若不存在），不触发 embedding，瞬时完成"""
        if cls._client is None:
            return False
        try:
            cls._get_collection(collection_name)
            logger.info(f"Created collection '{collection_name}'")
            return True
        except Exception as e:
            logger.warning(f"Failed to create collection '{collection_name}': {e}")
            return False

    @classmethod
    def list_items(cls, collection_name: str, limit: int = 100, offset: int = 0) -> dict:
        """分页列出集合中的文档 {total, items: [{id, text, metadata}]}"""
        collection = cls._get_collection(collection_name)
        total = collection.count()
        if total == 0:
            return {"total": 0, "items": []}
        results = collection.get(
            limit=limit,
            offset=offset,
            include=["documents", "metadatas"],
        )
        items = []
        if results["ids"]:
            for i in range(len(results["ids"])):
                items.append({
                    "id": results["ids"][i],
                    "text": results["documents"][i] if results["documents"] else "",
                    "metadata": results["metadatas"][i] if results["metadatas"] else {},
                })
        return {"total": total, "items": items}

    @classmethod
    def list_collections(cls) -> list[str]:
        """列出所有集合"""
        if cls._client is None:
            return []
        return [c.name for c in cls._client.list_collections()]
