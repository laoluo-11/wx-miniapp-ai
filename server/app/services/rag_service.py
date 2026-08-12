"""
RAG 知识库检索服务 — 单例模式
基于 ChromaDB + BAAI/bge-large-zh-v1.5
"""
import logging
import os
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = os.getenv("RAG_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
PERSIST_DIR = os.getenv("RAG_PERSIST_DIR", "/opt/wx-miniapp-ai/server/data/chroma_db")
HF_ENDPOINT = os.getenv("HF_ENDPOINT", "https://hf-mirror.com")


class RAGService:
    """RAG 检索服务单例"""

    _instance: Optional["RAGService"] = None
    _client: Optional[chromadb.PersistentClient] = None
    _embedding_fn = None

    def __init__(self):
        raise RuntimeError("Use RAGService.initialize() instead of constructor")

    @classmethod
    def initialize(cls, persist_dir: str | None = None) -> "RAGService":
        """初始化 ChromaDB 客户端（延迟加载模型）"""
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
    def _get_embedding_fn(cls):
        """延迟加载 embedding 模型"""
        if cls._embedding_fn is not None:
            return cls._embedding_fn

        if HF_ENDPOINT and "HF_ENDPOINT" not in os.environ:
            os.environ["HF_ENDPOINT"] = HF_ENDPOINT

        from sentence_transformers import SentenceTransformer

        logger.info(f"Loading embedding model: {EMBEDDING_MODEL} ...")
        model = SentenceTransformer(EMBEDDING_MODEL)
        cls._embedding_fn = model
        logger.info(f"Embedding model loaded, dim={model.get_sentence_embedding_dimension()}")
        return cls._embedding_fn

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
        model = cls._get_embedding_fn()
        embeddings = model.encode(documents, normalize_embeddings=True).tolist()

        if ids is None:
            import uuid
            ids = [str(uuid.uuid4()) for _ in documents]
        if metadatas is None:
            metadatas = [{} for _ in documents]

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
        model = cls._get_embedding_fn()
        query_embedding = model.encode([query], normalize_embeddings=True).tolist()

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
