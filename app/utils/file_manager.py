"""
文件管理器
处理文档的读写、YAML front-matter 解析等操作

v6.0 Enhancement: 支持双写模式（v4 projects/ + v6 artifacts/）
"""
import aiofiles
from pathlib import Path
from typing import Optional
import logging

from app.models.document import Document, DocumentMetadata, DocumentType, DocumentStatus
from app.config import settings

logger = logging.getLogger(__name__)


class FileManager:
    """
    文件管理器类

    v6.0 Enhancement: 支持双写模式
    - v4 模式: 写入 projects/{project_id}/documents/
    - v6 模式: 同时写入 artifacts/ (通过 ArtifactStore)
    """

    def __init__(self, base_path: Optional[str] = None, enable_v6_dual_write: bool = True):
        """
        初始化文件管理器

        Args:
            base_path: 基础路径（项目根目录）
            enable_v6_dual_write: 是否启用 v6 双写模式（默认启用）
        """
        self.base_path = Path(base_path or settings.projects_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

        # v6.0: 双写模式开关
        self.enable_v6_dual_write = enable_v6_dual_write
        self._artifact_store = None  # 延迟初始化

    def get_project_path(self, project_id: str) -> Path:
        """获取项目目录路径"""
        return self.base_path / project_id

    def get_documents_path(self, project_id: str) -> Path:
        """获取项目文档目录路径"""
        return self.get_project_path(project_id) / "documents"

    def ensure_project_structure(self, project_id: str):
        """
        确保项目目录结构存在

        Args:
            project_id: 项目 ID
        """
        project_path = self.get_project_path(project_id)
        documents_path = self.get_documents_path(project_id)
        logs_path = project_path / "logs"

        project_path.mkdir(parents=True, exist_ok=True)
        documents_path.mkdir(parents=True, exist_ok=True)
        logs_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"Ensured project structure for {project_id}")

    def _get_artifact_store(self):
        """
        获取 ArtifactStore 实例（延迟初始化）

        Returns:
            ArtifactStore 实例，如果未启用 v6 则返回 None
        """
        if not self.enable_v6_dual_write:
            return None

        if self._artifact_store is None:
            try:
                from app.services.artifact_store import ArtifactStore
                # 使用 backend/artifacts 作为基础路径
                artifacts_base = Path(settings.projects_path).parent / "artifacts"
                self._artifact_store = ArtifactStore(base_path=str(artifacts_base))
                logger.info(f"Initialized ArtifactStore at {artifacts_base}")
            except Exception as e:
                logger.warning(f"Failed to initialize ArtifactStore: {e}. v6 dual-write disabled.")
                self.enable_v6_dual_write = False
                return None

        return self._artifact_store

    def _document_to_artifact_category(self, doc_type: DocumentType) -> str:
        """
        将 v4 DocumentType 映射到 v6 Artifact 类别

        Args:
            doc_type: v4 文档类型

        Returns:
            v6 artifact 类别目录名
        """
        # 映射规则（基于 v6 SOP）
        doc_type_str = str(doc_type.value if hasattr(doc_type, 'value') else doc_type)

        if doc_type_str.startswith("00_"):
            return "00_intake"
        elif doc_type_str.startswith("01_"):
            return "01_research"
        elif doc_type_str.startswith("02_"):
            return "02_freeze"
        elif doc_type_str.startswith("03_"):
            return "03_spec"
        elif doc_type_str.startswith("04_"):
            return "04_frozen"
        else:
            return "00_intake"  # 默认分类

    async def _save_to_artifact_store(self, project_id: str, document: Document, file_path: str):
        """
        保存文档到 ArtifactStore (v6 双写)

        v6.0 Enhanced: Uses created_by, rigor_profile, gate_relevance from DocumentMetadata

        Args:
            project_id: 项目 ID
            document: 文档对象
            file_path: v4 文件路径
        """
        if not self.enable_v6_dual_write:
            return

        try:
            artifact_store = self._get_artifact_store()
            if artifact_store is None:
                return

            from app.models.artifact import Artifact, ArtifactMetadata, ArtifactStatus, CreatedBy

            # 确定 artifact 类别
            category = self._document_to_artifact_category(document.metadata.doc_type)

            # 生成 artifact ID（使用 project_id + doc_type）
            doc_type_value = getattr(document.metadata.doc_type, 'value', document.metadata.doc_type)
            artifact_id = f"{project_id}_{doc_type_value}"

            # 生成 artifact 文件路径
            artifact_file_path = Path(artifact_store.base_path) / category / f"{doc_type_value}.md"

            # 映射 created_by（v6.0 新增）
            created_by_str = document.metadata.created_by or "system"
            try:
                created_by = CreatedBy(created_by_str.lower())
            except ValueError:
                created_by = CreatedBy.SYSTEM
                logger.warning(f"Invalid created_by value: {created_by_str}, using SYSTEM")

            # 创建 ArtifactMetadata
            artifact_metadata = ArtifactMetadata(
                doc_type=doc_type_value,
                version=document.metadata.version,
                status=ArtifactStatus.DRAFT if document.metadata.status == DocumentStatus.DRAFT else ArtifactStatus.FROZEN,
                created_by=created_by,
                project_id=project_id,
                rigor_profile=document.metadata.rigor_profile,  # v6.0 新增
                inputs=document.metadata.inputs,
                outputs=document.metadata.outputs,
                gate_relevance=document.metadata.gate_relevance,  # v6.0 新增
                created_at=document.metadata.created_at,
                updated_at=document.metadata.updated_at
            )

            # 创建 Artifact
            artifact = Artifact(
                id=artifact_id,
                metadata=artifact_metadata,
                content=document.content,
                file_path=str(artifact_file_path)
            )

            # 保存到 ArtifactStore
            await artifact_store.save_artifact(artifact)
            logger.info(f"[v6 dual-write] Saved artifact: {artifact_id} -> {artifact_file_path}")

        except Exception as e:
            # 双写失败不应影响主流程
            logger.warning(f"[v6 dual-write] Failed to save to ArtifactStore: {e}")


    async def save_document(self, project_id: str, document: Document) -> str:
        """
        保存文档到文件系统

        v6.0 Enhancement: 支持双写模式
        - 主写入: projects/{project_id}/documents/ (v4 兼容)
        - 副写入: artifacts/ (v6 新增，通过 ArtifactStore)

        Args:
            project_id: 项目 ID
            document: 文档对象

        Returns:
            str: 文件路径（v4 路径）
        """
        try:
            self.ensure_project_structure(project_id)

            # 生成文件名 - 使用枚举的 value 值
            doc_type_value = getattr(document.metadata.doc_type, 'value', document.metadata.doc_type)
            filename = f"{doc_type_value}.md"
            file_path = self.get_documents_path(project_id) / filename

            # 转换为 Markdown 格式
            markdown_content = document.to_markdown()

            # 主写入: v4 路径（异步写入文件）
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(markdown_content)

            logger.info(f"[v4] Saved document to {file_path}")

            # 副写入: v6 ArtifactStore（双写模式）
            await self._save_to_artifact_store(project_id, document, str(file_path))

            return str(file_path)

        except Exception as e:
            logger.error(f"Failed to save document: {e}")
            raise

    async def load_document(self, project_id: str, doc_type: DocumentType) -> Optional[Document]:
        """
        从文件系统加载文档

        Args:
            project_id: 项目 ID
            doc_type: 文档类型

        Returns:
            Optional[Document]: 文档对象，如果不存在则返回 None
        """
        try:
            # 使用枚举的 value 值生成文件名
            doc_type_value = getattr(doc_type, 'value', doc_type)
            filename = f"{doc_type_value}.md"
            file_path = self.get_documents_path(project_id) / filename

            if not file_path.exists():
                logger.warning(f"Document not found: {file_path}")
                return None

            # 异步读取文件
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                markdown_content = await f.read()

            # 解析文档
            document = Document.from_markdown(markdown_content)
            logger.info(f"Loaded document from {file_path}")
            return document

        except Exception as e:
            logger.error(f"Failed to load document: {e}")
            return None

    async def document_exists(self, project_id: str, doc_type: DocumentType) -> bool:
        """
        检查文档是否存在

        Args:
            project_id: 项目 ID
            doc_type: 文档类型

        Returns:
            bool: 文档是否存在
        """
        filename = f"{doc_type}.md"
        file_path = self.get_documents_path(project_id) / filename
        return file_path.exists()

    async def list_documents(self, project_id: str) -> list:
        """
        列出项目的所有文档

        Args:
            project_id: 项目 ID

        Returns:
            list: 文档文件名列表
        """
        documents_path = self.get_documents_path(project_id)
        if not documents_path.exists():
            return []

        return [f.name for f in documents_path.glob("*.md")]

    async def delete_document(self, project_id: str, doc_type: DocumentType):
        """
        删除文档

        Args:
            project_id: 项目 ID
            doc_type: 文档类型
        """
        try:
            filename = f"{doc_type}.md"
            file_path = self.get_documents_path(project_id) / filename

            if file_path.exists():
                file_path.unlink()
                logger.info(f"Deleted document: {file_path}")
            else:
                logger.warning(f"Document not found for deletion: {file_path}")

        except Exception as e:
            logger.error(f"Failed to delete document: {e}")
            raise


# 全局文件管理器实例
_file_manager_instance = None


def get_file_manager(enable_v6_dual_write: bool = True) -> FileManager:
    """
    获取全局文件管理器实例

    Args:
        enable_v6_dual_write: 是否启用 v6 双写模式（默认启用）

    Returns:
        FileManager 实例
    """
    global _file_manager_instance
    if _file_manager_instance is None:
        _file_manager_instance = FileManager(enable_v6_dual_write=enable_v6_dual_write)
    return _file_manager_instance
