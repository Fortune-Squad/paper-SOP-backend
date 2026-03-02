"""
Gate Runner 服务

可脚本化的 Gate 检查系统，支持 Rigor Profile 的阈值调整

v6.0 NEW: 独立运行的 Gate 检查器，集成 Rigor Profile
"""
import logging
from typing import Optional, Dict, Any
from datetime import datetime

from app.models.gate import (
    GateType, GateResult, GateVerdict, CheckItem
)
from app.models.rigor_profile import (
    RigorLevel, get_rigor_profile, calculate_gate_verdict
)
from app.services.gate_checker import GateChecker
from app.models.project import Project

logger = logging.getLogger(__name__)


class GateRunner:
    """
    可脚本化的 Gate Runner

    支持独立运行 Gate 检查，并根据 Rigor Profile 调整判定标准
    """

    def __init__(self, rigor_level: RigorLevel = RigorLevel.TOP_JOURNAL):
        """
        初始化 Gate Runner

        Args:
            rigor_level: 研究强度档位
        """
        self.rigor_level = rigor_level
        self.rigor_profile = get_rigor_profile(rigor_level)
        self.gate_checker = GateChecker()

        logger.info(f"Initialized GateRunner with rigor level: {rigor_level.value}")

    async def run_gate(
        self,
        project: Project,
        gate_type: GateType,
        force_recheck: bool = False
    ) -> GateResult:
        """
        运行指定的 Gate 检查

        Args:
            project: 项目对象
            gate_type: Gate 类型
            force_recheck: 是否强制重新检查（忽略缓存）

        Returns:
            GateResult: Gate 检查结果（已应用 Rigor Profile 阈值）
        """
        try:
            logger.info(f"Running {gate_type.value} for project {project.project_id} with rigor level {self.rigor_level.value}")

            # 如果强制重新检查，清除缓存
            if force_recheck:
                self.gate_checker.clear_cache(project.project_id, gate_type.value)

            # 调用 GateChecker 获取原始结果
            if gate_type == GateType.GATE_0:
                raw_result = await self.gate_checker.check_gate_0(project)
            elif gate_type == GateType.GATE_1:
                raw_result = await self.gate_checker.check_gate_1(project)
            elif gate_type == GateType.GATE_1_25:
                raw_result = await self.gate_checker.check_gate_1_25(project)
            elif gate_type == GateType.GATE_1_5:
                raw_result = await self.gate_checker.check_gate_1_5(project)
            elif gate_type == GateType.GATE_1_6:
                raw_result = await self.gate_checker.check_gate_1_6(project)
            elif gate_type == GateType.GATE_2:
                raw_result = await self.gate_checker.check_gate_2(project)
            else:
                raise ValueError(f"Unknown gate type: {gate_type}")

            # 应用 Rigor Profile 阈值调整判定
            adjusted_result = self._apply_rigor_profile(raw_result)

            logger.info(f"{gate_type.value} result: {adjusted_result.verdict.value} (rigor: {self.rigor_level.value})")

            return adjusted_result

        except Exception as e:
            logger.error(f"Failed to run {gate_type.value}: {e}")
            raise

    def _apply_rigor_profile(self, raw_result: GateResult) -> GateResult:
        """
        应用 Rigor Profile 阈值调整判定

        Args:
            raw_result: 原始 Gate 检查结果

        Returns:
            GateResult: 调整后的结果
        """
        gate_type_str = raw_result.gate_type.value

        # 获取该 gate 的阈值配置
        try:
            threshold = self.rigor_profile.gate_thresholds[gate_type_str]
        except KeyError:
            # 如果没有配置，使用原始结果
            logger.warning(f"No threshold config for {gate_type_str} in {self.rigor_level.value}, using raw result")
            return raw_result

        # 检查是否可跳过
        if threshold.skippable and raw_result.verdict == GateVerdict.FAIL:
            logger.info(f"{gate_type_str} is skippable in {self.rigor_level.value} mode, but still marked as FAIL")
            # 可跳过的 gate 失败时，添加提示但不改变判定
            raw_result.suggestions.insert(0, f"[{self.rigor_level.value}] 此 Gate 可选，但建议通过")

        # 检查是否必须通过
        if not threshold.required:
            logger.info(f"{gate_type_str} is not required in {self.rigor_level.value} mode")
            raw_result.suggestions.insert(0, f"[{self.rigor_level.value}] 此 Gate 非必须")

        # 使用 Rigor Profile 的阈值重新计算判定
        rigor_verdict = calculate_gate_verdict(
            self.rigor_level,
            gate_type_str,
            raw_result.passed_count,
            raw_result.total_count
        )

        # 如果判定发生变化，记录日志
        if rigor_verdict != raw_result.is_passed():
            logger.info(
                f"{gate_type_str} verdict changed by rigor profile: "
                f"{raw_result.verdict.value} -> {'PASS' if rigor_verdict else 'FAIL'} "
                f"({raw_result.passed_count}/{raw_result.total_count}, "
                f"threshold: {threshold.min_pass_rate})"
            )

            # 更新判定
            raw_result.verdict = GateVerdict.PASS if rigor_verdict else GateVerdict.FAIL

            # 添加说明
            raw_result.suggestions.insert(
                0,
                f"[{self.rigor_level.value}] 通过率 {raw_result.pass_rate:.1f}% "
                f"({'≥' if rigor_verdict else '<'} {threshold.min_pass_rate * 100:.0f}% 要求)"
            )

        return raw_result

    async def run_all_gates(
        self,
        project: Project,
        stop_on_failure: bool = True,
        force_recheck: bool = False
    ) -> Dict[GateType, GateResult]:
        """
        运行所有 Gate 检查

        Args:
            project: 项目对象
            stop_on_failure: 是否在遇到失败时停止
            force_recheck: 是否强制重新检查

        Returns:
            Dict[GateType, GateResult]: 所有 Gate 的检查结果
        """
        results = {}

        # Gate 检查顺序
        gate_sequence = [
            GateType.GATE_0,
            GateType.GATE_1,
            GateType.GATE_1_25,
            GateType.GATE_1_5,
            GateType.GATE_1_6,
            GateType.GATE_2,
        ]

        for gate_type in gate_sequence:
            try:
                result = await self.run_gate(project, gate_type, force_recheck)
                results[gate_type] = result

                # 如果失败且需要停止
                if stop_on_failure and result.verdict == GateVerdict.FAIL:
                    # 检查是否可跳过
                    threshold = self.rigor_profile.gate_thresholds.get(gate_type.value)
                    if threshold and threshold.skippable:
                        logger.info(f"{gate_type.value} failed but is skippable, continuing...")
                    else:
                        logger.warning(f"{gate_type.value} failed, stopping gate checks")
                        break

            except Exception as e:
                logger.error(f"Failed to run {gate_type.value}: {e}")
                # 创建失败结果
                results[gate_type] = GateResult(
                    gate_type=gate_type,
                    verdict=GateVerdict.FAIL,
                    check_items=[],
                    passed_count=0,
                    total_count=0,
                    suggestions=[f"检查失败: {str(e)}"],
                    checked_at=datetime.now(),
                    project_id=project.project_id
                )

                if stop_on_failure:
                    break

        return results

    def get_gate_summary(self, results: Dict[GateType, GateResult]) -> Dict[str, Any]:
        """
        生成 Gate 检查摘要

        Args:
            results: Gate 检查结果字典

        Returns:
            Dict[str, Any]: 摘要信息
        """
        total_gates = len(results)
        passed_gates = sum(1 for r in results.values() if r.verdict == GateVerdict.PASS)
        failed_gates = total_gates - passed_gates

        # 统计检查项
        total_checks = sum(r.total_count for r in results.values())
        passed_checks = sum(r.passed_count for r in results.values())

        # 识别阻塞性失败（必须通过的 gate）
        blocking_failures = []
        for gate_type, result in results.items():
            if result.verdict == GateVerdict.FAIL:
                threshold = self.rigor_profile.gate_thresholds.get(gate_type.value)
                if threshold and threshold.required and not threshold.skippable:
                    blocking_failures.append(gate_type.value)

        return {
            "rigor_level": self.rigor_level.value,
            "total_gates": total_gates,
            "passed_gates": passed_gates,
            "failed_gates": failed_gates,
            "total_checks": total_checks,
            "passed_checks": passed_checks,
            "overall_pass_rate": (passed_checks / total_checks * 100) if total_checks > 0 else 0,
            "blocking_failures": blocking_failures,
            "can_proceed": len(blocking_failures) == 0
        }

    def is_gate_required(self, gate_type: GateType) -> bool:
        """
        检查指定 Gate 是否必须通过

        Args:
            gate_type: Gate 类型

        Returns:
            bool: 是否必须通过
        """
        threshold = self.rigor_profile.gate_thresholds.get(gate_type.value)
        if not threshold:
            return True  # 默认必须
        return threshold.required and not threshold.skippable

    def get_gate_threshold_info(self, gate_type: GateType) -> Dict[str, Any]:
        """
        获取指定 Gate 的阈值信息

        Args:
            gate_type: Gate 类型

        Returns:
            Dict[str, Any]: 阈值信息
        """
        threshold = self.rigor_profile.gate_thresholds.get(gate_type.value)
        if not threshold:
            return {
                "gate_type": gate_type.value,
                "required": True,
                "min_pass_rate": 1.0,
                "allow_partial_pass": False,
                "skippable": False,
                "description": "默认配置"
            }

        return {
            "gate_type": gate_type.value,
            "required": threshold.required,
            "min_pass_rate": threshold.min_pass_rate,
            "allow_partial_pass": threshold.allow_partial_pass,
            "skippable": threshold.skippable,
            "description": threshold.description
        }


# 全局 Gate Runner 实例缓存
_gate_runner_instances: Dict[RigorLevel, GateRunner] = {}


def get_gate_runner(rigor_level: RigorLevel = RigorLevel.TOP_JOURNAL) -> GateRunner:
    """
    获取 Gate Runner 实例（单例模式）

    Args:
        rigor_level: 研究强度档位

    Returns:
        GateRunner: Gate Runner 实例
    """
    if rigor_level not in _gate_runner_instances:
        _gate_runner_instances[rigor_level] = GateRunner(rigor_level)
    return _gate_runner_instances[rigor_level]
