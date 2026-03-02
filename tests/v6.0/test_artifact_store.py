"""
Artifact 和 ArtifactStore 单元测试
"""
import pytest
import asyncio
from datetime import datetime
from pathlib import Path
import tempfile
import shutil

from app.models.artifact import (
    Artifact, ArtifactMetadata, ArtifactStatus, CreatedBy, RigorProfile
)
from app.services.artifact_store import ArtifactStore


class TestArtifactModel:
    """测试 Artifact 数据模型"""

    def test_artifact_metadata_creation(self):
        """测试 ArtifactMetadata 创建"""
        metadata = ArtifactMetadata(
            doc_type="ProjectIntake",
            version="0.1",
            status=ArtifactStatus.DRAFT,
            created_by=CreatedBy.HUMAN,
            project_id="test-project-001",
            rigor_profile=RigorProfile.TOP_JOURNAL
        )

        assert metadata.doc_type == "ProjectIntake"
        assert metadata.version == "0.1"
        assert metadata.status == ArtifactStatus.DRAFT
        assert metadata.created_by == CreatedBy.HUMAN
        assert metadata.rigor_profile == RigorProfile.TOP_JOURNAL

    def test_artifact_creation(self):
        """测试 Artifact 创建"""
        metadata = ArtifactMetadata(
            doc_type="ProjectIntake",
            version="0.1",
            status=ArtifactStatus.DRAFT,
            created_by=CreatedBy.HUMAN,
            project_id="test-project-001"
        )

        artifact = Artifact(
            id="artifact-001",
            metadata=metadata,
            content="# Test Content\n\nThis is a test artifact.",
            file_path="artifacts/00_intake/test.md"
        )

        assert artifact.id == "artifact-001"
        assert artifact.metadata.doc_type == "ProjectIntake"
        assert "Test Content" in artifact.content

    def test_artifact_to_markdown(self):
        """测试 Artifact 序列化为 Markdown"""
        metadata = ArtifactMetadata(
            doc_type="ProjectIntake",
            version="0.1",
            status=ArtifactStatus.DRAFT,
            created_by=CreatedBy.HUMAN,
            project_id="test-project-001"
        )

        artifact = Artifact(
            id="artifact-001",
            metadata=metadata,
            content="# Test Content",
            file_path="artifacts/00_intake/test.md"
        )

        markdown = artifact.to_markdown()

        assert markdown.startswith("---\n")
        assert "doc_type: ProjectIntake" in markdown
        assert "version: '0.1'" in markdown
        assert "# Test Content" in markdown

    def test_artifact_from_markdown(self):
        """测试从 Markdown 解析 Artifact"""
        markdown_content = """---
doc_type: ProjectIntake
version: '0.1'
status: draft
created_by: human
project_id: test-project-001
rigor_profile: top_journal
inputs: []
outputs: []
gate_relevance: null
created_at: '2026-02-04T10:00:00'
updated_at: '2026-02-04T10:00:00'
---

# Test Content

This is a test artifact.
"""

        artifact = Artifact.from_markdown(
            file_path="artifacts/00_intake/test.md",
            content=markdown_content,
            artifact_id="artifact-001"
        )

        assert artifact.id == "artifact-001"
        assert artifact.metadata.doc_type == "ProjectIntake"
        assert artifact.metadata.version == "0.1"
        assert "Test Content" in artifact.content

    def test_artifact_update_content(self):
        """测试 Artifact 内容更新"""
        import time
        metadata = ArtifactMetadata(
            doc_type="ProjectIntake",
            version="0.1",
            status=ArtifactStatus.DRAFT,
            created_by=CreatedBy.HUMAN,
            project_id="test-project-001"
        )

        artifact = Artifact(
            id="artifact-001",
            metadata=metadata,
            content="# Original Content",
            file_path="artifacts/00_intake/test.md"
        )

        # Small delay to ensure updated_at differs
        time.sleep(0.01)

        # 更新内容
        updated_artifact = artifact.update_content("# Updated Content")

        assert updated_artifact.metadata.version == "0.2"  # 版本号增加
        assert updated_artifact.content == "# Updated Content"
        assert updated_artifact.metadata.updated_at >= artifact.metadata.updated_at


class TestArtifactStore:
    """测试 ArtifactStore 服务"""

    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def artifact_store(self, temp_dir):
        """创建 ArtifactStore 实例"""
        return ArtifactStore(base_path=temp_dir)

    @pytest.fixture
    def sample_artifact(self):
        """创建示例 Artifact"""
        metadata = ArtifactMetadata(
            doc_type="ProjectIntake",
            version="0.1",
            status=ArtifactStatus.DRAFT,
            created_by=CreatedBy.HUMAN,
            project_id="test-project-001"
        )

        return Artifact(
            id="artifact-001",
            metadata=metadata,
            content="# Test Content\n\nThis is a test artifact.",
            file_path="artifacts/00_intake/test.md"
        )

    def test_save_artifact(self, artifact_store, sample_artifact, temp_dir):
        """测试保存 Artifact"""
        async def _run():
            sample_artifact.file_path = str(Path(temp_dir) / "00_intake" / "test.md")
            artifact_id = await artifact_store.save_artifact(sample_artifact)
            assert artifact_id == "artifact-001"
            assert Path(sample_artifact.file_path).exists()
            assert artifact_id in artifact_store.index
        asyncio.run(_run())

    def test_load_artifact(self, artifact_store, sample_artifact, temp_dir):
        """测试加载 Artifact"""
        async def _run():
            sample_artifact.file_path = str(Path(temp_dir) / "00_intake" / "test.md")
            await artifact_store.save_artifact(sample_artifact)
            loaded_artifact = await artifact_store.load_artifact("artifact-001")
            assert loaded_artifact is not None
            assert loaded_artifact.id == "artifact-001"
            assert loaded_artifact.metadata.doc_type == "ProjectIntake"
            assert "Test Content" in loaded_artifact.content
        asyncio.run(_run())

    def test_list_artifacts(self, artifact_store, temp_dir):
        """测试列出 Artifacts"""
        async def _run():
            for i in range(3):
                metadata = ArtifactMetadata(
                    doc_type="ProjectIntake",
                    version="0.1",
                    status=ArtifactStatus.DRAFT,
                    created_by=CreatedBy.HUMAN,
                    project_id="test-project-001"
                )
                artifact = Artifact(
                    id=f"artifact-{i:03d}",
                    metadata=metadata,
                    content=f"# Test Content {i}",
                    file_path=str(Path(temp_dir) / "00_intake" / f"test_{i}.md")
                )
                await artifact_store.save_artifact(artifact)
            artifacts = await artifact_store.list_artifacts("test-project-001")
            assert len(artifacts) == 3
        asyncio.run(_run())

    def test_update_artifact(self, artifact_store, sample_artifact, temp_dir):
        """测试更新 Artifact"""
        async def _run():
            sample_artifact.file_path = str(Path(temp_dir) / "00_intake" / "test.md")
            await artifact_store.save_artifact(sample_artifact)
            updated_artifact = await artifact_store.update_artifact(
                "artifact-001", "# Updated Content"
            )
            assert updated_artifact is not None
            assert updated_artifact.metadata.version == "0.2"
            assert updated_artifact.content == "# Updated Content"
        asyncio.run(_run())

    def test_delete_artifact(self, artifact_store, sample_artifact, temp_dir):
        """测试删除 Artifact"""
        async def _run():
            sample_artifact.file_path = str(Path(temp_dir) / "00_intake" / "test.md")
            await artifact_store.save_artifact(sample_artifact)
            success = await artifact_store.delete_artifact("artifact-001")
            assert success
            assert "artifact-001" not in artifact_store.index
            assert not Path(sample_artifact.file_path).exists()
        asyncio.run(_run())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
