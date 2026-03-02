"""
Artifact Store 服务

管理 artifacts 的存储、检索和版本控制
"""
import os
import json
from typing import Optional, List, Dict
from pathlib import Path
import logging

from app.models.artifact import Artifact, ArtifactMetadata, ArtifactStatus, CreatedBy

logger = logging.getLogger(__name__)


class ArtifactStore:
    """Artifact 存储管理器"""

    def __init__(self, base_path: str = "artifacts"):
        """
        初始化 Artifact Store

        Args:
            base_path: artifacts 根目录路径
        """
        self.base_path = Path(base_path)
        self.index_file = self.base_path / "index.json"
        self.index: Dict[str, str] = {}  # artifact_id -> file_path

        # 确保目录存在
        self.base_path.mkdir(parents=True, exist_ok=True)

        # 加载索引
        self._load_index()

    def _load_index(self):
        """从文件加载索引"""
        if self.index_file.exists():
            try:
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    self.index = json.load(f)
                logger.info(f"Loaded artifact index: {len(self.index)} artifacts")
            except Exception as e:
                logger.error(f"Failed to load artifact index: {e}")
                self.index = {}
        else:
            self.index = {}

    def _save_index(self):
        """保存索引到文件"""
        try:
            with open(self.index_file, 'w', encoding='utf-8') as f:
                json.dump(self.index, f, indent=2, ensure_ascii=False)
            logger.debug("Saved artifact index")
        except Exception as e:
            logger.error(f"Failed to save artifact index: {e}")

    async def save_artifact(self, artifact: Artifact) -> str:
        """
        保存 artifact 到文件系统

        Args:
            artifact: 要保存的 artifact

        Returns:
            artifact_id
        """
        try:
            # 确保目录存在
            file_path = Path(artifact.file_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # 序列化为 Markdown
            content = artifact.to_markdown()

            # 写入文件
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)

            # 更新索引
            self.index[artifact.id] = str(file_path)
            self._save_index()

            logger.info(f"Saved artifact: {artifact.id} -> {file_path}")
            return artifact.id

        except Exception as e:
            logger.error(f"Failed to save artifact {artifact.id}: {e}")
            raise

    async def load_artifact(self, artifact_id: str) -> Optional[Artifact]:
        """
        从文件系统加载 artifact

        Args:
            artifact_id: artifact ID

        Returns:
            Artifact 对象，如果不存在则返回 None
        """
        try:
            # 从索引获取文件路径
            file_path = self.index.get(artifact_id)
            if not file_path:
                logger.warning(f"Artifact not found in index: {artifact_id}")
                return None

            # 读取文件
            file_path = Path(file_path)
            if not file_path.exists():
                logger.warning(f"Artifact file not found: {file_path}")
                return None

            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 解析为 Artifact
            artifact = Artifact.from_markdown(
                file_path=str(file_path),
                content=content,
                artifact_id=artifact_id
            )

            logger.debug(f"Loaded artifact: {artifact_id}")
            return artifact

        except Exception as e:
            logger.error(f"Failed to load artifact {artifact_id}: {e}")
            return None

    async def list_artifacts(
        self,
        project_id: str,
        doc_type: Optional[str] = None,
        status: Optional[ArtifactStatus] = None
    ) -> List[Artifact]:
        """
        列出项目的所有 artifacts

        Args:
            project_id: 项目 ID
            doc_type: 文档类型过滤（可选）
            status: 状态过滤（可选）

        Returns:
            Artifact 列表
        """
        artifacts = []

        for artifact_id in self.index.keys():
            artifact = await self.load_artifact(artifact_id)
            if not artifact:
                continue

            # 过滤条件
            if artifact.metadata.project_id != project_id:
                continue
            if doc_type and artifact.metadata.doc_type != doc_type:
                continue
            if status and artifact.metadata.status != status:
                continue

            artifacts.append(artifact)

        logger.debug(f"Listed {len(artifacts)} artifacts for project {project_id}")
        return artifacts

    async def update_artifact(self, artifact_id: str, new_content: str) -> Optional[Artifact]:
        """
        更新 artifact 内容

        Args:
            artifact_id: artifact ID
            new_content: 新内容

        Returns:
            更新后的 Artifact，如果不存在则返回 None
        """
        # 加载现有 artifact
        artifact = await self.load_artifact(artifact_id)
        if not artifact:
            return None

        # 更新内容（自动增加版本号）
        updated_artifact = artifact.update_content(new_content)

        # 保存
        await self.save_artifact(updated_artifact)

        logger.info(f"Updated artifact: {artifact_id} (version {updated_artifact.metadata.version})")
        return updated_artifact

    async def delete_artifact(self, artifact_id: str) -> bool:
        """
        删除 artifact

        Args:
            artifact_id: artifact ID

        Returns:
            是否成功删除
        """
        try:
            # 从索引获取文件路径
            file_path = self.index.get(artifact_id)
            if not file_path:
                logger.warning(f"Artifact not found in index: {artifact_id}")
                return False

            # 删除文件
            file_path = Path(file_path)
            if file_path.exists():
                file_path.unlink()

            # 从索引移除
            del self.index[artifact_id]
            self._save_index()

            logger.info(f"Deleted artifact: {artifact_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete artifact {artifact_id}: {e}")
            return False

    async def get_artifact_by_path(self, file_path: str) -> Optional[Artifact]:
        """
        通过文件路径获取 artifact

        Args:
            file_path: 文件路径

        Returns:
            Artifact 对象，如果不存在则返回 None
        """
        # 在索引中查找
        for artifact_id, path in self.index.items():
            if path == file_path:
                return await self.load_artifact(artifact_id)

        return None

    def rebuild_index(self):
        """重建索引（扫描所有 artifact 文件）"""
        logger.info("Rebuilding artifact index...")
        self.index = {}

        # 扫描所有 .md 文件
        for file_path in self.base_path.rglob("*.md"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # 尝试解析
                artifact_id = file_path.stem  # 使用文件名作为 ID
                artifact = Artifact.from_markdown(
                    file_path=str(file_path),
                    content=content,
                    artifact_id=artifact_id
                )

                self.index[artifact_id] = str(file_path)

            except Exception as e:
                logger.warning(f"Failed to parse artifact {file_path}: {e}")

        self._save_index()
        logger.info(f"Rebuilt index: {len(self.index)} artifacts")


# 全局单例实例
_artifact_store_instance: Optional[ArtifactStore] = None


def get_artifact_store(base_path: str = "artifacts") -> ArtifactStore:
    """
    获取 ArtifactStore 单例实例

    Args:
        base_path: artifacts 根目录路径

    Returns:
        ArtifactStore: 单例实例
    """
    global _artifact_store_instance
    if _artifact_store_instance is None:
        _artifact_store_instance = ArtifactStore(base_path=base_path)
    return _artifact_store_instance

