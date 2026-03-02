"""
Artifact 数据模型

定义 v6.0 的核心数据结构：Artifact 和 ArtifactStore
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class ArtifactStatus(str, Enum):
    """Artifact 状态"""
    DRAFT = "draft"
    FROZEN = "frozen"


class CreatedBy(str, Enum):
    """创建者类型"""
    HUMAN = "human"
    CHATGPT = "chatgpt"
    GEMINI = "gemini"
    SYSTEM = "system"


class RigorProfile(str, Enum):
    """研究强度档位"""
    TOP_JOURNAL = "top_journal"
    FAST_TRACK = "fast_track"


class ArtifactMetadata(BaseModel):
    """Artifact 元数据（对应 YAML front-matter）"""
    doc_type: str = Field(..., description="文档类型")
    version: str = Field(..., description="版本号")
    status: ArtifactStatus = Field(..., description="状态")
    created_by: CreatedBy = Field(..., description="创建者")
    project_id: str = Field(..., description="项目 ID")
    rigor_profile: Optional[RigorProfile] = Field(None, description="研究强度档位")
    inputs: List[str] = Field(default_factory=list, description="输入 artifacts")
    outputs: List[str] = Field(default_factory=list, description="输出 artifacts")
    gate_relevance: Optional[str] = Field(None, description="关联的 Gate")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")

    class Config:
        use_enum_values = True


class Artifact(BaseModel):
    """Artifact 完整模型"""
    id: str = Field(..., description="Artifact ID (唯一标识)")
    metadata: ArtifactMetadata = Field(..., description="元数据")
    content: str = Field(..., description="内容（Markdown）")
    file_path: str = Field(..., description="文件路径")

    def to_markdown(self) -> str:
        """序列化为 Markdown 文件内容（包含 YAML front-matter）"""
        import yaml

        # 序列化 metadata 为 YAML
        metadata_dict = self.metadata.dict()
        # 转换 datetime 为字符串
        metadata_dict['created_at'] = self.metadata.created_at.isoformat()
        metadata_dict['updated_at'] = self.metadata.updated_at.isoformat()

        yaml_str = yaml.dump(metadata_dict, allow_unicode=True, sort_keys=False)

        # 组装完整内容
        return f"---\n{yaml_str}---\n\n{self.content}"

    @classmethod
    def from_markdown(cls, file_path: str, content: str, artifact_id: str) -> "Artifact":
        """从 Markdown 文件内容解析（包含 YAML front-matter）"""
        import yaml
        import re

        # 解析 YAML front-matter
        match = re.match(r'^---\n(.*?)\n---\n\n(.*)$', content, re.DOTALL)
        if not match:
            raise ValueError("Invalid artifact format: missing YAML front-matter")

        yaml_str, markdown_content = match.groups()
        metadata_dict = yaml.safe_load(yaml_str)

        # 转换字符串为 datetime
        if isinstance(metadata_dict.get('created_at'), str):
            metadata_dict['created_at'] = datetime.fromisoformat(metadata_dict['created_at'])
        if isinstance(metadata_dict.get('updated_at'), str):
            metadata_dict['updated_at'] = datetime.fromisoformat(metadata_dict['updated_at'])

        metadata = ArtifactMetadata(**metadata_dict)

        return cls(
            id=artifact_id,
            metadata=metadata,
            content=markdown_content,
            file_path=file_path
        )

    def update_content(self, new_content: str) -> "Artifact":
        """更新内容并增加版本号"""
        # 解析当前版本号
        version_parts = self.metadata.version.split('.')
        major, minor = int(version_parts[0]), int(version_parts[1])

        # 增加 minor 版本
        new_version = f"{major}.{minor + 1}"

        # 创建新的 metadata
        new_metadata = self.metadata.copy(update={
            'version': new_version,
            'updated_at': datetime.now()
        })

        return Artifact(
            id=self.id,
            metadata=new_metadata,
            content=new_content,
            file_path=self.file_path
        )
