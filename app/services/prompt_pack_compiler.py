"""
Prompt Pack Compiler

从 Artifact Store 编译 prompt，避免 prompt drift

v6.0 NEW: Artifact-driven prompt generation
v1.2 §13.3: 新增 memory_entries, north_star 参数 + READINESS_ASSESSMENT prompt_type
"""
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class PromptType(str, Enum):
    """v1.2 §13.3: Prompt 类型枚举"""
    EXECUTE = "execute"
    REVIEW_ACCEPTANCE = "review_acceptance"
    REVIEW_FIX = "review_fix"
    DIAGNOSE = "diagnose"
    ASSEMBLY_KIT = "assembly_kit"
    FIGURE_GEN = "figure_gen"
    READINESS_ASSESSMENT = "readiness_assessment"  # v1.2 新增
    PAPER_DRAFT = "paper_draft"
    GENERIC = "generic"


class PromptTemplate:
    """Prompt 模板"""

    def __init__(
        self,
        template_id: str,
        template_text: str,
        required_artifacts: List[str],
        optional_artifacts: List[str] = None,
        prompt_type: PromptType = PromptType.GENERIC  # v1.2 §13.3
    ):
        """
        初始化 Prompt 模板

        Args:
            template_id: 模板 ID
            template_text: 模板文本（支持 {artifact_name} 占位符）
            required_artifacts: 必需的 artifact 列表
            optional_artifacts: 可选的 artifact 列表
            prompt_type: Prompt 类型（v1.2 新增）
        """
        self.template_id = template_id
        self.template_text = template_text
        self.required_artifacts = required_artifacts
        self.optional_artifacts = optional_artifacts or []
        self.prompt_type = prompt_type  # v1.2 §13.3

    def get_placeholders(self) -> List[str]:
        """获取模板中的所有占位符"""
        import re
        return re.findall(r'\{(\w+)\}', self.template_text)


class PromptPack:
    """编译后的 Prompt Pack"""

    def __init__(
        self,
        prompt_id: str,
        compiled_prompt: str,
        artifacts_used: Dict[str, str],
        metadata: Dict[str, Any]
    ):
        """
        初始化 Prompt Pack

        Args:
            prompt_id: Prompt ID
            compiled_prompt: 编译后的 prompt
            artifacts_used: 使用的 artifacts（artifact_id -> content）
            metadata: 元数据
        """
        self.prompt_id = prompt_id
        self.compiled_prompt = compiled_prompt
        self.artifacts_used = artifacts_used
        self.metadata = metadata
        self.compiled_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "prompt_id": self.prompt_id,
            "compiled_prompt": self.compiled_prompt,
            "artifacts_used": self.artifacts_used,
            "metadata": self.metadata,
            "compiled_at": self.compiled_at.isoformat()
        }


class PromptPackCompiler:
    """
    Prompt Pack Compiler

    从 Artifact Store 编译 prompt
    """

    def __init__(self, artifact_store=None):
        """
        初始化 Compiler

        Args:
            artifact_store: Artifact Store 实例（可选）
        """
        self.artifact_store = artifact_store
        self.templates: Dict[str, PromptTemplate] = {}

    def register_template(self, template: PromptTemplate):
        """
        注册 Prompt 模板

        Args:
            template: Prompt 模板
        """
        self.templates[template.template_id] = template
        logger.info(f"Registered template: {template.template_id}")

    def compile_prompt(
        self,
        template_id: str,
        project_id: str,
        artifact_overrides: Optional[Dict[str, str]] = None,
        context: Optional[Dict[str, Any]] = None,
        memory_entries: Optional[str] = None,  # v1.2 §13.3 新增
        north_star: Optional[str] = None  # v1.2 §13.3 新增
    ) -> PromptPack:
        """
        编译 Prompt

        Args:
            template_id: 模板 ID
            project_id: 项目 ID
            artifact_overrides: Artifact 覆盖（artifact_id -> content）
            context: 额外上下文
            memory_entries: MEMORY.md 相关条目（v1.2 §13.3）
            north_star: 北极星问题（v1.2 §13.3，用于 READINESS_ASSESSMENT）

        Returns:
            PromptPack: 编译后的 Prompt Pack

        Raises:
            ValueError: 如果模板不存在或缺少必需的 artifacts
        """
        # 获取模板
        if template_id not in self.templates:
            raise ValueError(f"Template not found: {template_id}")

        template = self.templates[template_id]
        logger.info(f"Compiling prompt: {template_id} for project {project_id}")

        # 收集 artifacts
        artifacts = {}
        artifact_overrides = artifact_overrides or {}

        # 处理必需的 artifacts
        for artifact_id in template.required_artifacts:
            if artifact_id in artifact_overrides:
                # 使用覆盖值
                artifacts[artifact_id] = artifact_overrides[artifact_id]
            elif self.artifact_store:
                # 从 Artifact Store 读取
                artifact = self.artifact_store.get_artifact(project_id, artifact_id)
                if not artifact:
                    raise ValueError(f"Required artifact not found: {artifact_id}")
                artifacts[artifact_id] = artifact.content
            else:
                raise ValueError(f"Cannot resolve artifact: {artifact_id} (no artifact store)")

        # 处理可选的 artifacts
        for artifact_id in template.optional_artifacts:
            if artifact_id in artifact_overrides:
                artifacts[artifact_id] = artifact_overrides[artifact_id]
            elif self.artifact_store:
                artifact = self.artifact_store.get_artifact(project_id, artifact_id)
                if artifact:
                    artifacts[artifact_id] = artifact.content
                else:
                    # 可选 artifact 不存在，使用空字符串
                    artifacts[artifact_id] = ""
            else:
                artifacts[artifact_id] = ""

        # 添加额外上下文
        if context:
            artifacts.update(context)

        # v1.2 §13.3: 添加 memory_entries 和 north_star
        if memory_entries:
            artifacts['memory_entries'] = memory_entries
        if north_star:
            artifacts['north_star'] = north_star

        # 编译 prompt
        try:
            compiled_prompt = template.template_text.format(**artifacts)
        except KeyError as e:
            raise ValueError(f"Missing placeholder in template: {e}")

        # 创建 Prompt Pack
        prompt_pack = PromptPack(
            prompt_id=f"{template_id}_{project_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            compiled_prompt=compiled_prompt,
            artifacts_used={k: v[:100] + "..." if len(v) > 100 else v for k, v in artifacts.items()},
            metadata={
                "template_id": template_id,
                "project_id": project_id,
                "required_artifacts": template.required_artifacts,
                "optional_artifacts": template.optional_artifacts
            }
        )

        logger.info(f"Compiled prompt: {prompt_pack.prompt_id} ({len(compiled_prompt)} chars)")
        return prompt_pack

    def validate_template(self, template: PromptTemplate) -> List[str]:
        """
        验证模板

        Args:
            template: Prompt 模板

        Returns:
            List[str]: 验证问题列表（空列表表示无问题）
        """
        issues = []

        # 检查占位符
        placeholders = template.get_placeholders()

        # 检查所有占位符是否在 required 或 optional artifacts 中
        all_artifacts = set(template.required_artifacts + template.optional_artifacts)
        for placeholder in placeholders:
            if placeholder not in all_artifacts:
                issues.append(f"Placeholder '{placeholder}' not in artifact lists")

        # 检查是否有未使用的 artifacts
        for artifact_id in all_artifacts:
            if artifact_id not in placeholders:
                issues.append(f"Artifact '{artifact_id}' not used in template")

        return issues

    def get_template_info(self, template_id: str) -> Dict[str, Any]:
        """
        获取模板信息

        Args:
            template_id: 模板 ID

        Returns:
            Dict[str, Any]: 模板信息
        """
        if template_id not in self.templates:
            raise ValueError(f"Template not found: {template_id}")

        template = self.templates[template_id]
        return {
            "template_id": template.template_id,
            "required_artifacts": template.required_artifacts,
            "optional_artifacts": template.optional_artifacts,
            "placeholders": template.get_placeholders(),
            "template_length": len(template.template_text)
        }

    def list_templates(self) -> List[str]:
        """列出所有已注册的模板"""
        return list(self.templates.keys())


def inject_agents_md(project_id: str) -> str:
    """
    v7.1: 读取项目 AGENTS.md 内容用于 prompt 注入

    Args:
        project_id: 项目 ID

    Returns:
        str: AGENTS.md 内容（截断至 3500 tokens ≈ 10500 chars）
    """
    from app.config import settings
    agents_path = Path(settings.projects_path) / project_id / "AGENTS.md"
    if not agents_path.exists():
        return "(AGENTS.md not found)"
    content = agents_path.read_text(encoding="utf-8")
    # Token budget: < 3500 tokens ≈ 10500 chars
    if len(content) > 10500:
        content = content[:10500] + "\n... (truncated)"
    return content


def inject_memory_md(project_id: str, tags: Optional[List[str]] = None) -> str:
    """
    v7.1: 读取项目 MEMORY.md 内容用于 prompt 注入

    Args:
        project_id: 项目 ID
        tags: 可选的 domain tag 过滤列表

    Returns:
        str: MEMORY.md 内容或过滤后的条目（截断至 500 tokens ≈ 1500 chars）
    """
    from app.services.memory_store import MemoryStore
    from app.config import settings
    project_path = str(Path(settings.projects_path) / project_id)
    store = MemoryStore(project_path)
    if tags:
        entries = store.get_relevant_entries(tags)
        content = "\n".join(entries) if entries else "(No relevant MEMORY entries)"
    else:
        content = store.get_all_entries_formatted()
        if not content:
            content = "(MEMORY.md empty)"
    # Token budget: < 500 tokens ≈ 1500 chars
    if len(content) > 1500:
        content = content[:1500] + "\n... (truncated)"
    return content
_compiler_instance = None


def get_prompt_pack_compiler(artifact_store=None) -> PromptPackCompiler:
    """
    获取全局 Prompt Pack Compiler 实例

    Args:
        artifact_store: Artifact Store 实例（可选）

    Returns:
        PromptPackCompiler: Compiler 实例
    """
    global _compiler_instance
    if _compiler_instance is None:
        _compiler_instance = PromptPackCompiler(artifact_store)
    elif artifact_store and _compiler_instance.artifact_store is None:
        _compiler_instance.artifact_store = artifact_store
    return _compiler_instance
