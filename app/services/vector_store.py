"""
向量数据库管理
使用 ChromaDB 存储和检索项目文档，实现 Project 知识库功能
"""
import chromadb
from chromadb.config import Settings as ChromaSettings
from typing import List, Dict, Any, Optional
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


class VectorStore:
    """向量数据库管理类"""

    def __init__(self, persist_directory: Optional[str] = None):
        """
        初始化向量数据库

        Args:
            persist_directory: 持久化目录路径
        """
        self.persist_directory = persist_directory or settings.vector_db_path
        Path(self.persist_directory).mkdir(parents=True, exist_ok=True)

        # 初始化 ChromaDB 客户端
        self.client = chromadb.PersistentClient(
            path=self.persist_directory,
            settings=ChromaSettings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )

        logger.info(f"Initialized VectorStore at {self.persist_directory}")

    def get_or_create_collection(self, project_id: str):
        """
        获取或创建项目的 collection

        Args:
            project_id: 项目 ID

        Returns:
            Collection: ChromaDB collection 对象
        """
        # ChromaDB 要求集合名称 3-63 字符，只能包含字母数字、下划线、连字符
        # 使用项目 ID 的哈希值来生成短的唯一名称
        import hashlib
        project_hash = hashlib.md5(project_id.encode()).hexdigest()[:16]
        collection_name = f"proj_{project_hash}"

        try:
            collection = self.client.get_or_create_collection(
                name=collection_name,
                metadata={"project_id": project_id}
            )
            logger.info(f"Got/created collection: {collection_name} for project {project_id}")
            return collection
        except Exception as e:
            logger.error(f"Failed to get/create collection {collection_name}: {e}")
            raise

    async def add_document(self, project_id: str, doc_id: str,
                          content: str, metadata: Optional[Dict[str, Any]] = None):
        """
        添加文档到向量数据库

        Args:
            project_id: 项目 ID
            doc_id: 文档 ID
            content: 文档内容
            metadata: 文档元数据
        """
        try:
            collection = self.get_or_create_collection(project_id)

            # 准备元数据
            doc_metadata = metadata or {}
            doc_metadata["project_id"] = project_id
            doc_metadata["doc_id"] = doc_id

            # 添加文档
            collection.add(
                documents=[content],
                metadatas=[doc_metadata],
                ids=[doc_id]
            )

            logger.info(f"Added document {doc_id} to project {project_id}")

        except Exception as e:
            logger.error(f"Failed to add document {doc_id}: {e}")
            raise

    async def update_document(self, project_id: str, doc_id: str,
                             content: str, metadata: Optional[Dict[str, Any]] = None):
        """
        更新文档

        Args:
            project_id: 项目 ID
            doc_id: 文档 ID
            content: 新的文档内容
            metadata: 新的文档元数据
        """
        try:
            collection = self.get_or_create_collection(project_id)

            # 准备元数据
            doc_metadata = metadata or {}
            doc_metadata["project_id"] = project_id
            doc_metadata["doc_id"] = doc_id

            # 更新文档
            collection.update(
                documents=[content],
                metadatas=[doc_metadata],
                ids=[doc_id]
            )

            logger.info(f"Updated document {doc_id} in project {project_id}")

        except Exception as e:
            logger.error(f"Failed to update document {doc_id}: {e}")
            raise

    async def query(self, project_id: str, query_text: str,
                   top_k: int = 3, filter_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        查询相关文档

        Args:
            project_id: 项目 ID
            query_text: 查询文本
            top_k: 返回前 k 个最相关的文档
            filter_metadata: 元数据过滤条件

        Returns:
            List[Dict]: 相关文档列表
        """
        try:
            collection = self.get_or_create_collection(project_id)

            # 执行查询
            results = collection.query(
                query_texts=[query_text],
                n_results=top_k,
                where=filter_metadata
            )

            # 格式化结果
            documents = []
            if results and results['documents'] and len(results['documents']) > 0:
                for i in range(len(results['documents'][0])):
                    doc = {
                        "id": results['ids'][0][i],
                        "content": results['documents'][0][i],
                        "metadata": results['metadatas'][0][i] if results['metadatas'] else {},
                        "distance": results['distances'][0][i] if results['distances'] else None
                    }
                    documents.append(doc)

            logger.info(f"Query returned {len(documents)} documents for project {project_id}")
            return documents

        except Exception as e:
            logger.error(f"Failed to query documents: {e}")
            return []

    async def get_document(self, project_id: str, doc_id: str) -> Optional[Dict[str, Any]]:
        """
        获取指定文档

        Args:
            project_id: 项目 ID
            doc_id: 文档 ID

        Returns:
            Optional[Dict]: 文档信息，如果不存在则返回 None
        """
        try:
            collection = self.get_or_create_collection(project_id)

            results = collection.get(
                ids=[doc_id],
                include=["documents", "metadatas"]
            )

            if results and results['documents'] and len(results['documents']) > 0:
                return {
                    "id": results['ids'][0],
                    "content": results['documents'][0],
                    "metadata": results['metadatas'][0] if results['metadatas'] else {}
                }

            return None

        except Exception as e:
            logger.error(f"Failed to get document {doc_id}: {e}")
            return None

    async def delete_document(self, project_id: str, doc_id: str):
        """
        删除文档

        Args:
            project_id: 项目 ID
            doc_id: 文档 ID
        """
        try:
            collection = self.get_or_create_collection(project_id)
            collection.delete(ids=[doc_id])
            logger.info(f"Deleted document {doc_id} from project {project_id}")

        except Exception as e:
            logger.error(f"Failed to delete document {doc_id}: {e}")
            raise

    async def list_documents(self, project_id: str) -> List[Dict[str, Any]]:
        """
        列出项目的所有文档

        Args:
            project_id: 项目 ID

        Returns:
            List[Dict]: 文档列表
        """
        try:
            collection = self.get_or_create_collection(project_id)

            results = collection.get(
                include=["documents", "metadatas"]
            )

            documents = []
            if results and results['ids']:
                for i in range(len(results['ids'])):
                    doc = {
                        "id": results['ids'][i],
                        "content": results['documents'][i] if results['documents'] else "",
                        "metadata": results['metadatas'][i] if results['metadatas'] else {}
                    }
                    documents.append(doc)

            logger.info(f"Listed {len(documents)} documents for project {project_id}")
            return documents

        except Exception as e:
            logger.error(f"Failed to list documents: {e}")
            return []

    def delete_collection(self, project_id: str):
        """
        删除项目的 collection

        Args:
            project_id: 项目 ID
        """
        try:
            collection_name = f"project_{project_id}"
            self.client.delete_collection(name=collection_name)
            logger.info(f"Deleted collection: {collection_name}")

        except Exception as e:
            logger.error(f"Failed to delete collection: {e}")
            raise

    def reset(self):
        """重置整个数据库（谨慎使用）"""
        try:
            self.client.reset()
            logger.warning("Reset entire vector database")
        except Exception as e:
            logger.error(f"Failed to reset database: {e}")
            raise


# 全局向量数据库实例
_vector_store_instance = None


def get_vector_store() -> VectorStore:
    """获取全局向量数据库实例"""
    global _vector_store_instance
    if _vector_store_instance is None:
        _vector_store_instance = VectorStore()
    return _vector_store_instance
