"""
Front-matter Linter 工具

验证文档的 YAML front-matter 是否符合 v6.0 规范

v6.0 NEW: 自动化 front-matter 质量检查
"""
import logging
import re
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from pydantic import ValidationError

from app.models.document import (
    Document, DocumentMetadata, DocumentType, DocumentStatus, GateStatus
)

logger = logging.getLogger(__name__)


class FrontmatterIssue:
    """Front-matter 问题"""

    def __init__(
        self,
        file_path: str,
        severity: str,  # "error" or "warning"
        field: Optional[str],
        message: str
    ):
        self.file_path = file_path
        self.severity = severity
        self.field = field
        self.message = message

    def __repr__(self) -> str:
        field_str = f" [{self.field}]" if self.field else ""
        return f"[{self.severity.upper()}]{field_str} {self.file_path}: {self.message}"


class FrontmatterLintResult:
    """Front-matter 检查结果"""

    def __init__(self):
        self.total_files = 0
        self.valid_files = 0
        self.invalid_files = 0
        self.issues: List[FrontmatterIssue] = []

    def add_issue(self, issue: FrontmatterIssue):
        """添加问题"""
        self.issues.append(issue)

    def is_valid(self) -> bool:
        """是否所有文件都有效"""
        return len([i for i in self.issues if i.severity == "error"]) == 0

    def get_summary(self) -> str:
        """获取检查摘要"""
        error_count = len([i for i in self.issues if i.severity == "error"])
        warning_count = len([i for i in self.issues if i.severity == "warning"])

        lines = [
            "=" * 80,
            "Front-matter Lint 检查结果",
            "=" * 80,
            f"总文件数: {self.total_files}",
            f"有效文件: {self.valid_files}",
            f"无效文件: {self.invalid_files}",
            f"错误数: {error_count}",
            f"警告数: {warning_count}",
            f"通过率: {self.valid_files / self.total_files * 100:.1f}%" if self.total_files > 0 else "通过率: N/A",
            ""
        ]

        if self.issues:
            lines.append("问题详情:")
            lines.append("-" * 80)
            for issue in self.issues:
                lines.append(str(issue))

        lines.append("=" * 80)
        return "\n".join(lines)


class FrontmatterLinter:
    """Front-matter Linter"""

    # v6.0 必需字段（所有文档必须包含）
    REQUIRED_FIELDS = [
        "doc_type",
        "version",
        "status",
        "created_at",
        "updated_at",
        "project_id"
    ]

    # v6.0 推荐字段（根据文档类型推荐）
    RECOMMENDED_FIELDS = [
        "inputs",
        "outputs",
        "created_by",
        "rigor_profile"
    ]

    # Gate 相关文档应该包含 gate_relevance
    GATE_RELATED_DOCS = [
        DocumentType.PROJECT_INTAKE_CARD,  # Gate 0
        DocumentType.SELECTED_TOPIC,  # Gate 1
        DocumentType.TOPIC_ALIGNMENT_CHECK,  # Gate 1.25
        DocumentType.KILLER_PRIOR_CHECK,  # Gate 1.5
        DocumentType.REFERENCE_QA_REPORT,  # Gate 1.6
        DocumentType.RESEARCH_PLAN_FROZEN  # Gate 2
    ]

    def __init__(self):
        """初始化 Linter"""
        pass

    def lint_file(self, file_path: Path) -> List[FrontmatterIssue]:
        """
        检查单个文件的 front-matter

        Args:
            file_path: 文件路径

        Returns:
            List[FrontmatterIssue]: 问题列表
        """
        issues = []

        try:
            # 读取文件
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 检查是否有 YAML front-matter
            if not content.startswith("---"):
                issues.append(FrontmatterIssue(
                    file_path=str(file_path),
                    severity="error",
                    field=None,
                    message="缺少 YAML front-matter（文件应该以 --- 开头）"
                ))
                return issues

            # 尝试解析文档
            try:
                document = Document.from_markdown(content)
            except ValidationError as e:
                # Pydantic 验证错误
                for error in e.errors():
                    field = ".".join(str(loc) for loc in error['loc'])
                    issues.append(FrontmatterIssue(
                        file_path=str(file_path),
                        severity="error",
                        field=field,
                        message=f"验证失败: {error['msg']}"
                    ))
                return issues
            except Exception as e:
                issues.append(FrontmatterIssue(
                    file_path=str(file_path),
                    severity="error",
                    field=None,
                    message=f"解析失败: {str(e)}"
                ))
                return issues

            # 提取 YAML front-matter
            yaml_text = content.split("---", 2)[1].strip()

            # 检查必需字段
            for field in self.REQUIRED_FIELDS:
                if field not in yaml_text:
                    issues.append(FrontmatterIssue(
                        file_path=str(file_path),
                        severity="error",
                        field=field,
                        message=f"缺少必需字段: {field}"
                    ))

            # 检查推荐字段
            for field in self.RECOMMENDED_FIELDS:
                if field not in yaml_text:
                    issues.append(FrontmatterIssue(
                        file_path=str(file_path),
                        severity="warning",
                        field=field,
                        message=f"缺少推荐字段: {field}"
                    ))

            # 检查 Gate 相关文档是否包含 gate_relevance
            if document.metadata.doc_type in self.GATE_RELATED_DOCS:
                if not document.metadata.gate_relevance:
                    issues.append(FrontmatterIssue(
                        file_path=str(file_path),
                        severity="warning",
                        field="gate_relevance",
                        message=f"Gate 相关文档 ({document.metadata.doc_type}) 应该包含 gate_relevance 字段"
                    ))

            # 检查字段取值
            issues.extend(self._validate_field_values(file_path, document.metadata))

        except Exception as e:
            issues.append(FrontmatterIssue(
                file_path=str(file_path),
                severity="error",
                field=None,
                message=f"检查失败: {str(e)}"
            ))

        return issues

    def _validate_field_values(
        self,
        file_path: Path,
        metadata: DocumentMetadata
    ) -> List[FrontmatterIssue]:
        """
        验证字段取值是否符合规范

        Args:
            file_path: 文件路径
            metadata: 文档元数据

        Returns:
            List[FrontmatterIssue]: 问题列表
        """
        issues = []

        # 检查 version 格式（应该是 x.y 格式）
        if not re.match(r'^\d+\.\d+$', metadata.version):
            issues.append(FrontmatterIssue(
                file_path=str(file_path),
                severity="warning",
                field="version",
                message=f"版本号格式不规范: {metadata.version}（建议使用 x.y 格式，如 1.0）"
            ))

        # 检查 created_by 取值（应该是 human/chatgpt/gemini/system）
        if metadata.created_by:
            valid_creators = ["human", "chatgpt", "gemini", "system"]
            if metadata.created_by not in valid_creators:
                issues.append(FrontmatterIssue(
                    file_path=str(file_path),
                    severity="warning",
                    field="created_by",
                    message=f"created_by 取值不规范: {metadata.created_by}（应该是 {', '.join(valid_creators)}）"
                ))

        # 检查 rigor_profile 取值（应该是 top_journal/fast_track）
        if metadata.rigor_profile:
            valid_profiles = ["top_journal", "fast_track"]
            if metadata.rigor_profile not in valid_profiles:
                issues.append(FrontmatterIssue(
                    file_path=str(file_path),
                    severity="warning",
                    field="rigor_profile",
                    message=f"rigor_profile 取值不规范: {metadata.rigor_profile}（应该是 {', '.join(valid_profiles)}）"
                ))

        # 检查 gate_relevance 格式（应该是 gate_x 或 gate_x_y 格式）
        if metadata.gate_relevance:
            if not re.match(r'^gate_\d+(_\d+)?$', metadata.gate_relevance):
                issues.append(FrontmatterIssue(
                    file_path=str(file_path),
                    severity="warning",
                    field="gate_relevance",
                    message=f"gate_relevance 格式不规范: {metadata.gate_relevance}（应该是 gate_x 或 gate_x_y 格式）"
                ))

        # 检查评分字段范围（0-1）
        if metadata.evidence_quality is not None:
            if metadata.evidence_quality < 0 or metadata.evidence_quality > 1:
                issues.append(FrontmatterIssue(
                    file_path=str(file_path),
                    severity="error",
                    field="evidence_quality",
                    message=f"evidence_quality 超出范围: {metadata.evidence_quality}（应该在 0-1 之间）"
                ))

        if metadata.consistency_score is not None:
            if metadata.consistency_score < 0 or metadata.consistency_score > 1:
                issues.append(FrontmatterIssue(
                    file_path=str(file_path),
                    severity="error",
                    field="consistency_score",
                    message=f"consistency_score 超出范围: {metadata.consistency_score}（应该在 0-1 之间）"
                ))

        # 检查时间字段（updated_at 应该 >= created_at）
        if metadata.updated_at < metadata.created_at:
            issues.append(FrontmatterIssue(
                file_path=str(file_path),
                severity="error",
                field="updated_at",
                message=f"updated_at ({metadata.updated_at}) 早于 created_at ({metadata.created_at})"
            ))

        return issues

    def lint_project(self, project_path: Path) -> FrontmatterLintResult:
        """
        检查项目中所有文档的 front-matter

        Args:
            project_path: 项目路径（包含 documents/ 子目录）

        Returns:
            FrontmatterLintResult: 检查结果
        """
        result = FrontmatterLintResult()

        # 查找所有 .md 文件
        documents_path = project_path / "documents"
        if not documents_path.exists():
            logger.warning(f"Documents path not found: {documents_path}")
            return result

        md_files = list(documents_path.glob("*.md"))
        result.total_files = len(md_files)

        logger.info(f"Found {result.total_files} markdown files in {documents_path}")

        # 检查每个文件
        for md_file in md_files:
            issues = self.lint_file(md_file)

            # 统计错误数量
            error_count = len([i for i in issues if i.severity == "error"])

            if error_count == 0:
                result.valid_files += 1
            else:
                result.invalid_files += 1

            # 添加所有问题到结果
            for issue in issues:
                result.add_issue(issue)

        return result

    def lint_directory(self, directory: Path, recursive: bool = True) -> FrontmatterLintResult:
        """
        检查目录中所有项目的 front-matter

        Args:
            directory: 目录路径（包含多个项目）
            recursive: 是否递归查找项目

        Returns:
            FrontmatterLintResult: 检查结果
        """
        result = FrontmatterLintResult()

        if not directory.exists():
            logger.error(f"Directory not found: {directory}")
            return result

        # 查找所有项目目录（包含 documents/ 子目录的目录）
        project_dirs = []

        if recursive:
            for subdir in directory.rglob("documents"):
                if subdir.is_dir():
                    project_dirs.append(subdir.parent)
        else:
            for subdir in directory.iterdir():
                if subdir.is_dir() and (subdir / "documents").exists():
                    project_dirs.append(subdir)

        logger.info(f"Found {len(project_dirs)} projects in {directory}")

        # 检查每个项目
        for project_dir in project_dirs:
            logger.info(f"Linting project: {project_dir}")
            project_result = self.lint_project(project_dir)

            # 合并结果
            result.total_files += project_result.total_files
            result.valid_files += project_result.valid_files
            result.invalid_files += project_result.invalid_files
            result.issues.extend(project_result.issues)

        return result


def lint_frontmatter(
    path: Path,
    recursive: bool = True,
    output_file: Optional[Path] = None
) -> FrontmatterLintResult:
    """
    检查 front-matter（便捷函数）

    Args:
        path: 文件、项目或目录路径
        recursive: 是否递归查找（仅对目录有效）
        output_file: 输出文件路径（可选）

    Returns:
        FrontmatterLintResult: 检查结果
    """
    linter = FrontmatterLinter()

    if path.is_file():
        # 单个文件
        result = FrontmatterLintResult()
        result.total_files = 1
        issues = linter.lint_file(path)

        error_count = len([i for i in issues if i.severity == "error"])
        if error_count == 0:
            result.valid_files = 1
        else:
            result.invalid_files = 1

        for issue in issues:
            result.add_issue(issue)

    elif (path / "documents").exists():
        # 单个项目
        result = linter.lint_project(path)

    else:
        # 目录（包含多个项目）
        result = linter.lint_directory(path, recursive=recursive)

    # 输出结果
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(result.get_summary())
        logger.info(f"Lint result saved to: {output_file}")

    return result
