"""
WP Gate Checker
Work Package 验收门禁和冻结门禁检查器
"""
import logging
import yaml
from typing import Optional, Dict, Any, List

from app.models.gate import (
    GateResult, GateVerdict, GateType, CheckItem,
    WPGateChecklist, FreezeGateChecklist, SubtaskGateChecklist
)
from app.models.work_package import WPSpec, WPState, WPStatus, SubtaskSpec, SubtaskResult
from app.services.boundary_checker import ArtifactBoundaryChecker

logger = logging.getLogger(__name__)


class WPGateChecker:
    """WP 验收门禁和冻结门禁检查器"""

    async def check_wp_gate(
        self,
        project_id: str,
        wp_id: str,
        wp_spec: WPSpec,
        wp_state: WPState,
        review_result: Optional[Dict[str, Any]] = None
    ) -> GateResult:
        """
        检查 WP 验收门禁

        Args:
            project_id: 项目 ID
            wp_id: WP ID
            wp_spec: WP 规格
            wp_state: WP 状态
            review_result: Reviewer 的审查结果（YAML parsed）

        Returns:
            GateResult: 门禁检查结果
        """
        try:
            # 1. 检查所有 subtask 是否完成
            all_completed = all(
                r.status == "completed"
                for r in wp_state.subtask_results.values()
            ) if wp_state.subtask_results else False

            # 2. 检查 gate criteria（基于 review 结果）
            criteria_met = False
            if review_result:
                verdict = review_result.get("verdict", "FAIL")
                criteria_met = verdict == "PASS"

            # 3. 检查 artifact 边界
            all_changed_files = []
            all_allowed = []
            all_forbidden = []
            for st in wp_spec.subtasks:
                result = wp_state.subtask_results.get(st.subtask_id)
                if result:
                    all_changed_files.extend(result.what_changed)
                all_allowed.extend(st.allowed_paths)
                all_forbidden.extend(st.forbidden_paths)

            boundary_result = ArtifactBoundaryChecker.check(
                changed_files=all_changed_files,
                allowed_paths=all_allowed,
                forbidden_paths=all_forbidden
            )

            # 4. Review 是否批准
            review_approved = criteria_met

            checklist = WPGateChecklist(
                all_subtasks_completed=all_completed,
                gate_criteria_met=criteria_met,
                boundary_check_passed=boundary_result.passed,
                review_approved=review_approved
            )

            result = checklist.validate(wp_id=wp_id)
            result.project_id = project_id
            return result

        except Exception as e:
            logger.error(f"WP gate check failed for {wp_id}: {e}")
            return GateResult(
                gate_type=GateType.GATE_WP,
                verdict=GateVerdict.FAIL,
                check_items=[CheckItem(
                    item_name="Gate Check Error",
                    description=str(e),
                    passed=False,
                    details=str(e)
                )],
                passed_count=0,
                total_count=1,
                suggestions=["Gate 检查过程出错，请检查日志"],
                project_id=project_id
            )

    async def check_subtask_gate(
        self,
        subtask_spec: SubtaskSpec,
        subtask_result: SubtaskResult,
    ) -> GateResult:
        """
        §2.2.3: Subtask 级 gate 检查

        Args:
            subtask_spec: Subtask 规格
            subtask_result: Subtask 执行结果

        Returns:
            GateResult: 门禁检查结果
        """
        try:
            status_ok = subtask_result.status == "completed"

            # Boundary check
            changed = subtask_result.what_changed or subtask_result.artifacts_written
            if changed:
                bc = ArtifactBoundaryChecker.check(
                    changed_files=[f if isinstance(f, str) else f.get("path", "") for f in changed],
                    allowed_paths=subtask_spec.allowed_paths,
                    forbidden_paths=subtask_spec.forbidden_paths,
                )
                boundary_ok = bc.passed
            else:
                boundary_ok = True

            # Acceptance criteria check: search keywords in result summary
            criteria_ok = self._check_acceptance_criteria(
                subtask_spec.acceptance_criteria, subtask_result
            )

            # No critical issues
            no_critical = not any(
                isinstance(i, dict) and i.get("severity") == "high"
                for i in subtask_result.open_issues
            )

            checklist = SubtaskGateChecklist(
                status_completed=status_ok,
                boundary_check_passed=boundary_ok,
                acceptance_criteria_met=criteria_ok,
                no_critical_issues=no_critical,
            )
            result = checklist.validate(subtask_id=subtask_spec.subtask_id)
            return result

        except Exception as e:
            logger.error(f"Subtask gate check failed for {subtask_spec.subtask_id}: {e}")
            return GateResult(
                gate_type=GateType.GATE_SUBTASK,
                verdict=GateVerdict.FAIL,
                check_items=[CheckItem(
                    item_name="Subtask Gate Error",
                    description=str(e),
                    passed=False,
                    details=str(e)
                )],
                passed_count=0,
                total_count=1,
                suggestions=["Subtask gate 检查出错，请检查日志"],
                project_id=""
            )

    @staticmethod
    def _check_acceptance_criteria(
        criteria: list, result: SubtaskResult
    ) -> bool:
        """检查 acceptance_criteria 是否在 result 中体现"""
        if not criteria:
            return True
        summary_lower = (result.summary or "").lower()
        # 每条 criteria 至少有一个关键词出现在 summary 中
        for criterion in criteria:
            words = [w.strip().lower() for w in criterion.split() if len(w.strip()) > 3]
            if words and not any(w in summary_lower for w in words):
                return False
        return True

    async def check_freeze_gate(
        self,
        project_id: str,
        wp_id: str,
        wp_state: WPState
    ) -> GateResult:
        """
        检查 WP 冻结门禁 (v1.2: F1-F7)

        Args:
            project_id: 项目 ID
            wp_id: WP ID
            wp_state: WP 状态

        Returns:
            GateResult: 门禁检查结果
        """
        # F1: WP Gate 必须已通过
        wp_gate_passed = wp_state.gate_result is not None and \
            wp_state.gate_result.get("verdict") == "PASS"

        # F2: 检查是否有 artifacts 被写入
        artifacts_committed = any(
            len(r.artifacts_written) > 0
            for r in wp_state.subtask_results.values()
        ) if wp_state.subtask_results else False

        # F3: 检查是否有未解决问题
        open_issues = []
        for r in wp_state.subtask_results.values():
            open_issues.extend(r.open_issues)
        no_open_issues = len(open_issues) == 0

        # v1.2 §9.2 F4: Version tagged
        version_tagged = False
        try:
            from app.utils.git_manager import get_git_manager
            from git import Repo
            git_mgr = get_git_manager()
            project_path = git_mgr.get_project_path(project_id)
            if project_path.exists():
                repo = Repo(project_path)
                version_tagged = any(t.name.startswith(f"{wp_id}-v") for t in repo.tags)
        except Exception:
            pass

        # v1.2 §9.2 F5: No uncommitted changes
        no_uncommitted_changes = False
        try:
            from app.utils.git_manager import get_git_manager
            git_mgr = get_git_manager()
            no_uncommitted_changes = not git_mgr.has_uncommitted_changes(project_id)
        except Exception:
            pass

        # v1.2 §9.2 F6: FROZEN_MANIFEST exists and has artifacts
        manifest_complete = False
        try:
            from app.config import settings
            from pathlib import Path
            import json
            manifest_path = Path(settings.projects_path) / project_id / "execution" / f"FROZEN_MANIFEST_{wp_id}.json"
            if manifest_path.exists():
                manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest_complete = len(manifest_data.get("artifacts", {})) > 0
        except Exception:
            pass

        # v1.2 §9.2 F7: AGENTS.md and MEMORY.md updated after WP start
        agents_memory_updated = False
        try:
            from app.config import settings
            from pathlib import Path
            project_path = Path(settings.projects_path) / project_id
            agents_path = project_path / "AGENTS.md"
            memory_path = project_path / "MEMORY.md"
            wp_started = wp_state.started_at
            if wp_started and agents_path.exists() and memory_path.exists():
                import os
                agents_mtime = datetime.fromtimestamp(os.path.getmtime(agents_path))
                memory_mtime = datetime.fromtimestamp(os.path.getmtime(memory_path))
                agents_memory_updated = agents_mtime > wp_started and memory_mtime > wp_started
        except Exception:
            pass

        checklist = FreezeGateChecklist(
            wp_gate_passed=wp_gate_passed,
            artifacts_committed=artifacts_committed,
            no_open_issues=no_open_issues,
            version_tagged=version_tagged,
            no_uncommitted_changes=no_uncommitted_changes,
            manifest_complete=manifest_complete,
            agents_memory_updated=agents_memory_updated,
        )

        result = checklist.validate(wp_id=wp_id)
        result.project_id = project_id
        return result

    @staticmethod
    def parse_review_yaml(review_content: str) -> Dict[str, Any]:
        """
        解析 reviewer 返回的 JSON 或 YAML 内容

        v1.2 §6.3/§6.5: review_acceptance 和 diagnose 输出 JSON，
        但保留 YAML 兼容以支持旧格式。

        Args:
            review_content: JSON 或 YAML 格式的 review 结果

        Returns:
            Dict: 解析后的结果
        """
        import json

        content = review_content.strip()
        # 去除可能的 markdown code fences
        if content.startswith("```"):
            lines = content.split("\n")
            # Remove first line (```json or ```yaml) and last line (```)
            if lines[-1].strip() == "```":
                content = "\n".join(lines[1:-1])
            else:
                content = "\n".join(lines[1:])

        # Try JSON first (v1.2 preferred format)
        try:
            return json.loads(content) or {}
        except (json.JSONDecodeError, ValueError):
            pass

        # Fall back to YAML
        try:
            return yaml.safe_load(content) or {}
        except Exception as e:
            logger.warning(f"Failed to parse review content as JSON or YAML: {e}")
            return {"verdict": "FAIL", "issues": [str(e)]}
