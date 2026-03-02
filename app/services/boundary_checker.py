"""
Artifact Boundary Checker
检测 WP subtask 执行后的文件变更是否在允许范围内

防止 AI 执行时越界修改不相关的文件
"""
import logging
from typing import List, Set
from pathlib import Path, PurePosixPath
from fnmatch import fnmatch

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class BoundaryCheckResult(BaseModel):
    """边界检查结果"""
    passed: bool = Field(..., description="是否通过")
    violations: List[str] = Field(default_factory=list, description="违规文件列表")
    allowed_changes: List[str] = Field(default_factory=list, description="允许的变更文件")
    details: str = Field(default="", description="详细信息")


class ArtifactBoundaryChecker:
    """
    Artifact 边界检查器

    检查 subtask 执行后变更的文件是否在 allowed_paths 范围内，
    且不在 forbidden_paths 范围内。
    """

    @staticmethod
    def check(
        changed_files: List[str],
        allowed_paths: List[str],
        forbidden_paths: List[str]
    ) -> BoundaryCheckResult:
        """
        检查变更文件是否在允许范围内

        Args:
            changed_files: 变更的文件列表
            allowed_paths: 允许修改的路径模式列表（支持 glob）
            forbidden_paths: 禁止修改的路径模式列表（支持 glob）

        Returns:
            BoundaryCheckResult: 检查结果
        """
        violations = []
        allowed_changes = []

        for file_path in changed_files:
            # 标准化路径分隔符
            normalized = file_path.replace("\\", "/")

            # 检查是否在禁止列表中
            in_forbidden = any(
                fnmatch(normalized, pattern.replace("\\", "/"))
                for pattern in forbidden_paths
            )
            if in_forbidden:
                violations.append(file_path)
                continue

            # 检查是否在允许列表中
            if not allowed_paths:
                # 如果没有指定允许路径，所有非禁止路径都允许
                allowed_changes.append(file_path)
                continue

            in_allowed = any(
                fnmatch(normalized, pattern.replace("\\", "/"))
                for pattern in allowed_paths
            )
            if in_allowed:
                allowed_changes.append(file_path)
            else:
                violations.append(file_path)

        passed = len(violations) == 0
        details = ""
        if violations:
            details = f"发现 {len(violations)} 个越界修改: {', '.join(violations)}"
        else:
            details = f"所有 {len(allowed_changes)} 个变更文件在允许范围内"

        return BoundaryCheckResult(
            passed=passed,
            violations=violations,
            allowed_changes=allowed_changes,
            details=details
        )
