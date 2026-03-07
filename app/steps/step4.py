"""
Step 4 实现
Convergence & Delivery 阶段的步骤实现

Step 4 回归 BaseStep 模式，顺序执行：
D0 (Collect) → D1 (FigurePolish) → D2 (Assembly) → D3 (Citation QA) → D5 (Package)

v7.1: DeliveryState 状态机 + FigurePolish + trace bundle export
"""
import logging
from typing import Dict, Any
from enum import Enum
from pathlib import Path

from app.steps.base import BaseStep, StepExecutionError
from app.models.document import Document, DocumentType, DocumentStatus
from app.models.project import Project
from app.models.artifact import ArtifactStatus
from app.services.state_store import StateStore
from app.prompts.step4_prompts import (
    render_collect_prompt,
    render_assembly_kit_prompt,
    render_paper_draft_prompt,
    render_citation_qa_prompt,
    render_package_prompt,
    render_repro_check_prompt,
)

logger = logging.getLogger(__name__)


class DeliveryState(str, Enum):
    """v7.1 S3-3: Delivery 状态机"""
    NOT_STARTED = "not_started"
    COLLECTING = "collecting"
    FIGURES = "figures"
    ASSEMBLING = "assembling"
    CITATION_QA = "citation_qa"
    REPRO_CHECK = "repro_check"  # v1.2 §4.3
    PACKAGING = "packaging"
    DELIVERED = "delivered"


# State transition map: current_state -> next_state
DELIVERY_TRANSITIONS = {
    DeliveryState.NOT_STARTED: DeliveryState.COLLECTING,
    DeliveryState.COLLECTING: DeliveryState.FIGURES,
    DeliveryState.FIGURES: DeliveryState.ASSEMBLING,
    DeliveryState.ASSEMBLING: DeliveryState.CITATION_QA,
    DeliveryState.CITATION_QA: DeliveryState.REPRO_CHECK,
    DeliveryState.REPRO_CHECK: DeliveryState.PACKAGING,
    DeliveryState.PACKAGING: DeliveryState.DELIVERED,
}

# Step -> expected state
STEP_EXPECTED_STATE = {
    "step_4_collect": DeliveryState.NOT_STARTED,
    "step_4_figure_polish": DeliveryState.COLLECTING,
    "step_4_assembly": DeliveryState.FIGURES,
    "step_4_citation_qa": DeliveryState.ASSEMBLING,
    "step_4_repro": DeliveryState.CITATION_QA,
    "step_4_package": DeliveryState.REPRO_CHECK,
}


def _get_delivery_state(project: Project) -> DeliveryState:
    """获取当前 DeliveryState"""
    state_str = getattr(project, '_delivery_state', DeliveryState.NOT_STARTED.value)
    if isinstance(state_str, DeliveryState):
        return state_str
    try:
        return DeliveryState(state_str)
    except ValueError:
        return DeliveryState.NOT_STARTED


def _advance_delivery_state(project: Project, current: DeliveryState) -> DeliveryState:
    """推进 DeliveryState"""
    next_state = DELIVERY_TRANSITIONS.get(current, current)
    project._delivery_state = next_state.value
    logger.info(f"DeliveryState: {current.value} → {next_state.value}")
    return next_state


def _resolve_delivery_profile(project: Project) -> str:
    """从 state.json 读取 delivery_profile（权威来源），降级到 project model"""
    try:
        state_store = StateStore()
        exec_state = state_store.load(project.project_id)
        return exec_state.delivery_state.profile.value
    except Exception:
        return project.delivery_profile or "external_assembly_kit"


def _check_delivery_state(project: Project, step_id: str) -> None:
    """检查 DeliveryState 是否允许执行"""
    expected = STEP_EXPECTED_STATE.get(step_id)
    if expected is None:
        return  # No state check for unknown steps
    current = _get_delivery_state(project)
    if current != expected:
        logger.warning(
            f"DeliveryState mismatch for {step_id}: expected={expected.value}, "
            f"current={current.value}. Proceeding anyway."
        )


def _export_handoff_audit(project_path: Path) -> None:
    """Export handoff audit + convergence stats for delivery packaging.

    Reads ``handoff/packets.jsonl`` — if it exists — and writes:
    - ``delivery/handoff_audit.json``   (full packet chain)
    - ``delivery/convergence_report.json`` (aggregate statistics)

    Skipped silently when no packets file is present (legacy projects).
    """
    import json as _json
    from collections import Counter

    packets_path = project_path / "handoff" / "packets.jsonl"
    if not packets_path.exists():
        logger.info("No handoff packets found — skipping audit export")
        return

    # Load all packets
    all_packets: list = []
    with open(packets_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                all_packets.append(_json.loads(line))
            except _json.JSONDecodeError:
                continue

    if not all_packets:
        logger.info("Packets file empty — skipping audit export")
        return

    delivery_dir = project_path / "delivery"
    delivery_dir.mkdir(parents=True, exist_ok=True)

    # ── D1: handoff_audit.json ───────────────────────────────────
    audit_path = delivery_dir / "handoff_audit.json"
    with open(audit_path, "w", encoding="utf-8") as f:
        _json.dump(
            {"schema": "m2m-tp/0.2", "total": len(all_packets), "packets": all_packets},
            f, ensure_ascii=False, indent=2, default=str,
        )
    logger.info("Handoff audit exported: %d packets → %s", len(all_packets), audit_path)

    # ── D2: convergence_report.json ──────────────────────────────
    phase_ids = set()
    advanced = set()
    aborted = set()
    escalated = set()
    total_iterations = 0
    error_types: Counter = Counter()
    warning_gates_triggered: list = []

    for pkt in all_packets:
        pid = pkt.get("phase_id", "")
        if pid:
            phase_ids.add(pid)

        ptype = pkt.get("packet_type", "")
        decisions = pkt.get("decisions") or {}
        ra_action = decisions.get("ra_action", "")

        if ra_action == "ADVANCE":
            advanced.add(pid)
        elif ra_action == "ABORT":
            aborted.add(pid)
        elif ra_action == "ESCALATE":
            escalated.add(pid)

        if ptype == "result_report":
            total_iterations += 1

        # Collect error types from reasoning.what_i_tried_but_failed
        reasoning = pkt.get("reasoning") or {}
        for failure in reasoning.get("what_i_tried_but_failed", []):
            if isinstance(failure, str) and failure:
                error_types[failure[:80]] += 1

        # Warning gates from reasoning.warnings
        for w in reasoning.get("warnings", []):
            if isinstance(w, str) and w:
                warning_gates_triggered.append(w)

    n_phases = len(phase_ids) or 1
    stats = {
        "total_phases": len(phase_ids),
        "phases_advanced": len(advanced),
        "phases_aborted": len(aborted),
        "phases_escalated": len(escalated),
        "total_iterations": total_iterations,
        "avg_iterations_per_phase": round(total_iterations / n_phases, 2),
        "top_error_types": [
            {"error": err, "count": cnt}
            for err, cnt in error_types.most_common(10)
        ],
        "warning_gates_triggered": sorted(set(warning_gates_triggered)),
    }

    report_path = delivery_dir / "convergence_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        _json.dump(stats, f, ensure_ascii=False, indent=2, default=str)
    logger.info("Convergence report exported → %s", report_path)


class Step4_Collect(BaseStep):
    """Step 4 Collect (D0): 收集冻结 artifacts → delivery manifest"""

    @property
    def step_id(self) -> str:
        return "step_4_collect"

    @property
    def step_name(self) -> str:
        return "Collect Frozen Artifacts"

    @property
    def output_doc_type(self) -> DocumentType:
        return DocumentType.DELIVERY_MANIFEST

    @property
    def ai_model(self) -> str:
        from app.config import settings
        return settings.claude_model

    async def execute(self) -> Document:
        try:
            logger.info(f"Starting {self.step_name} for project {self.project.project_id}")
            _check_delivery_state(self.project, self.step_id)

            # 加载 WP Registry
            wp_registry = await self.load_context_with_fallback(
                step_id="step_3_init", doc_type=DocumentType.WP_REGISTRY
            ) or ""

            # 加载 Execution State
            exec_state = await self.load_context_with_fallback(
                step_id="step_3_exec", doc_type=DocumentType.EXECUTION_STATE
            ) or ""

            # 构建冻结 artifact 摘要
            frozen_summary = f"## Execution State\n{exec_state}\n"

            prompt = render_collect_prompt(frozen_summary, wp_registry)

            response = await self._dispatch_ai("structured_extract").chat(
                prompt,
                system_prompt="You are a Research Delivery Manager collecting frozen artifacts.",
            )

            self.log_ai_conversation(
                model=self.ai_model, system_prompt="Collect frozen artifacts",
                user_prompt=prompt[:500], response=response[:1000]
            )

            # §4.3 D0: Cross-check against PlanFrozen deliverables list
            try:
                plan_frozen = await self.load_context_with_fallback(
                    step_id="step_2_5", doc_type=DocumentType.RESEARCH_PLAN_FROZEN
                ) or ""
                if plan_frozen:
                    import re
                    # Extract expected deliverables from PlanFrozen (lines starting with - or * under deliverables/outputs sections)
                    expected_items = set()
                    in_deliverables = False
                    for line in plan_frozen.split("\n"):
                        lower = line.strip().lower()
                        if any(kw in lower for kw in ["deliverable", "output", "artifact"]) and "#" in line:
                            in_deliverables = True
                            continue
                        if in_deliverables and line.strip().startswith("#"):
                            in_deliverables = False
                        if in_deliverables and re.match(r"^\s*[-*]\s+", line):
                            item = re.sub(r"^\s*[-*]\s+", "", line).strip()
                            if item:
                                expected_items.add(item)

                    # Check which expected items are missing from the manifest response
                    missing_items = []
                    response_lower = response.lower()
                    for item in expected_items:
                        # Simple keyword match: if the item name doesn't appear in the manifest
                        item_keywords = [w for w in re.split(r"[\s_/]+", item.lower()) if len(w) > 3]
                        if item_keywords and not any(kw in response_lower for kw in item_keywords):
                            missing_items.append(item)

                    if missing_items:
                        from app.services.hil_service import HILService
                        from app.models.hil import HILTicketCreate, TicketPriority, QuestionType
                        hil = HILService()
                        await hil.create_ticket(HILTicketCreate(
                            project_id=self.project.project_id,
                            step_id="step_4_collect",
                            question_type=QuestionType.VALIDATION,
                            question=f"D0 cross-check: {len(missing_items)} deliverables missing from manifest: {', '.join(missing_items[:10])}",
                            context={"missing_items": missing_items},
                            priority=TicketPriority.HIGH,
                            blocking=True,
                        ))
                        logger.warning(f"D0 cross-check: {len(missing_items)} missing items, HIL ticket created")
            except Exception as xc_err:
                logger.warning(f"D0 cross-check failed (non-blocking): {xc_err}")

            self.project.step4_started = True

            document = self.create_document(
                doc_type=DocumentType.DELIVERY_MANIFEST,
                content=response,
                status=DocumentStatus.COMPLETED,
                inputs=["05_WP_Registry", "05_Execution_State"],
                outputs=["06_Delivery_Manifest"],
            )

            await self.save_and_commit(document, "step_4_collect: Delivery manifest created")
            await self.save_to_artifact_store(response, DocumentType.DELIVERY_MANIFEST, ArtifactStatus.DRAFT)
            _advance_delivery_state(self.project, DeliveryState.NOT_STARTED)

            return document

        except StepExecutionError:
            raise
        except Exception as e:
            logger.error(f"Step 4 Collect failed: {e}")
            raise StepExecutionError(f"Step 4 Collect failed: {e}")


class Step4_FigurePolish(BaseStep):
    """v7.1 Step 4 Figure Polish (D1): 图表润色"""

    @property
    def step_id(self) -> str:
        return "step_4_figure_polish"

    @property
    def step_name(self) -> str:
        return "Figure Polish"

    @property
    def output_doc_type(self) -> DocumentType:
        return DocumentType.DELIVERY_MANIFEST  # Reuse manifest for figure notes

    @property
    def ai_model(self) -> str:
        from app.config import settings
        return settings.claude_model

    async def execute(self) -> Document:
        try:
            logger.info(f"Starting {self.step_name} for project {self.project.project_id}")
            _check_delivery_state(self.project, self.step_id)

            manifest = await self.load_context_with_fallback(
                step_id="step_4_collect", doc_type=DocumentType.DELIVERY_MANIFEST
            ) or ""

            figure_list = await self.load_context_with_fallback(
                step_id="step_2_0", doc_type=DocumentType.FIGURE_TABLE_LIST
            ) or ""

            # §4.3 D1: Human review loop (max 2 rounds)
            MAX_REVIEW_ROUNDS = 2
            human_feedback = ""
            response = ""

            for round_num in range(1, MAX_REVIEW_ROUNDS + 1):
                feedback_section = f"\n## Human Feedback (Round {round_num})\n{human_feedback}" if human_feedback else ""
                prompt = f"""Review the delivery manifest and figure/table list.
For each figure and table, provide polish suggestions:
- Caption clarity and completeness
- Axis labels, units, legends
- Color scheme accessibility
- Resolution and format recommendations

## Delivery Manifest
{manifest}

## Figure/Table List
{figure_list}
{feedback_section}

Output a structured list of polish items per figure/table.
"""

                response = await self._dispatch_ai("packaging").chat(
                    prompt,
                    system_prompt="You are a scientific figure quality specialist.",
                )

                self.log_ai_conversation(
                    model=self.ai_model, system_prompt=f"Figure Polish (round {round_num})",
                    user_prompt=prompt[:500], response=response[:1000],
                )

                # §4.3 D1: Deliv-Loop1 blocking HIL — human review
                from app.models.hil import QuestionType, TicketPriority
                answer = await self.request_and_wait(
                    question=f"[D1 Round {round_num}/{MAX_REVIEW_ROUNDS}] 请审核图表润色建议。approve = 通过, 其他文字 = 修改意见",
                    question_type=QuestionType.VALIDATION,
                    options=["approve"],
                    priority=TicketPriority.HIGH,
                    blocking=True,
                    timeout_hours=48.0,
                )
                if answer and answer.strip().lower() == "approve":
                    break
                elif round_num < MAX_REVIEW_ROUNDS:
                    human_feedback = answer or ""
                # else: max rounds reached, proceed with last version

            document = self.create_document(
                doc_type=DocumentType.DELIVERY_MANIFEST,
                content=response,
                status=DocumentStatus.COMPLETED,
                inputs=["06_Delivery_Manifest", "02_Figure_Table_List"],
                outputs=["06_Figure_Polish_Notes"],
            )

            await self.save_and_commit(document, "step_4_figure_polish: Figure polish notes created")
            _advance_delivery_state(self.project, DeliveryState.COLLECTING)

            return document

        except StepExecutionError:
            raise
        except Exception as e:
            logger.error(f"Step 4 Figure Polish failed: {e}")
            raise StepExecutionError(f"Step 4 Figure Polish failed: {e}")


class Step4_Assembly(BaseStep):
    """Step 4 Assembly (D2): 生成 Assembly Kit"""

    @property
    def step_id(self) -> str:
        return "step_4_assembly"

    @property
    def step_name(self) -> str:
        return "Assembly Kit Generation"

    @property
    def output_doc_type(self) -> DocumentType:
        return DocumentType.ASSEMBLY_KIT_OUTLINE

    @property
    def ai_model(self) -> str:
        from app.config import settings
        return settings.claude_model

    async def execute(self) -> Document:
        try:
            logger.info(f"Starting {self.step_name} for project {self.project.project_id}")
            _check_delivery_state(self.project, self.step_id)

            manifest = await self.load_context_with_fallback(
                step_id="step_4_collect", doc_type=DocumentType.DELIVERY_MANIFEST
            ) or ""

            # 加载关键 artifacts 作为上下文
            claims = await self.load_context_with_fallback(
                step_id="step_1_4", doc_type=DocumentType.CLAIMS_AND_NONCLAIMS
            ) or ""

            exec_state = await self.load_context_with_fallback(
                step_id="step_3_exec", doc_type=DocumentType.EXECUTION_STATE
            ) or ""

            # §4.3 D2: delivery_profile 分支（从 state.json 权威读取）
            delivery_profile = _resolve_delivery_profile(self.project)

            if delivery_profile == "internal_draft":
                prompt = render_paper_draft_prompt(
                    delivery_manifest=manifest,
                    frozen_artifacts=exec_state,
                    claim_evidence_map=claims,
                )
                doc_type = DocumentType.PAPER_DRAFT
            else:
                prompt = render_assembly_kit_prompt(
                    delivery_manifest=manifest,
                    frozen_artifacts=exec_state,
                    claim_evidence_map=claims,
                )
                doc_type = DocumentType.ASSEMBLY_KIT_OUTLINE

            response = await self._dispatch_ai("packaging").chat(
                prompt,
                system_prompt="You are a Research Paper Assembly Specialist.",
            )

            self.log_ai_conversation(
                model=self.ai_model, system_prompt=f"Assembly ({delivery_profile})",
                user_prompt=prompt[:500], response=response[:1000]
            )

            document = self.create_document(
                doc_type=doc_type,
                content=response,
                status=DocumentStatus.COMPLETED,
                inputs=["06_Delivery_Manifest"],
                outputs=[doc_type.value],
            )

            await self.save_and_commit(document, f"step_4_assembly: {delivery_profile} generated")
            await self.save_to_artifact_store(response, doc_type, ArtifactStatus.DRAFT)
            _advance_delivery_state(self.project, DeliveryState.FIGURES)

            return document

        except StepExecutionError:
            raise
        except Exception as e:
            logger.error(f"Step 4 Assembly failed: {e}")
            raise StepExecutionError(f"Step 4 Assembly failed: {e}")


class Step4_CitationQA(BaseStep):
    """Step 4 Citation QA (D3): 引用完整性检查"""

    @property
    def step_id(self) -> str:
        return "step_4_citation_qa"

    @property
    def step_name(self) -> str:
        return "Citation QA Check"

    @property
    def output_doc_type(self) -> DocumentType:
        return DocumentType.CITATION_REPORT

    @property
    def ai_model(self) -> str:
        from app.config import settings
        return settings.claude_model

    async def execute(self) -> Document:
        try:
            logger.info(f"Starting {self.step_name} for project {self.project.project_id}")
            _check_delivery_state(self.project, self.step_id)

            assembly = await self.load_context_with_fallback(
                step_id="step_4_assembly", doc_type=DocumentType.ASSEMBLY_KIT_OUTLINE
            ) or ""

            # 加载参考文献
            refs = await self.load_context_with_fallback(
                step_id="step_1_1b", doc_type=DocumentType.REFERENCE_QA_REPORT
            ) or ""

            prompt = render_citation_qa_prompt(assembly, refs)

            response = await self._dispatch_ai("citation_qa").chat(
                prompt,
                system_prompt="You are a Citation Quality Assurance Specialist.",
            )

            self.log_ai_conversation(
                model=self.ai_model, system_prompt="Citation QA",
                user_prompt=prompt[:500], response=response[:1000]
            )

            # v1.2 §9.3 D7: 结构化引用验证
            try:
                import json
                from app.services.citation_qa_checker import CitationQAChecker
                from app.config import settings
                checker = CitationQAChecker()
                citation_report = checker.check(assembly, refs)
                report_path = Path(settings.projects_path) / self.project.project_id / "delivery" / "citation_report.json"
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(json.dumps(citation_report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
                logger.info(f"v1.2: citation_report.json saved: verdict={citation_report.verdict}")

                # §4.3 D3: FAIL → blocking HIL
                if citation_report.verdict == "FAIL":
                    from app.services.hil_service import HILService
                    from app.models.hil import HILTicketCreate, TicketPriority, QuestionType
                    hil = HILService()
                    await hil.create_ticket(HILTicketCreate(
                        project_id=self.project.project_id,
                        step_id="step_4_citation_qa",
                        question_type=QuestionType.VALIDATION,
                        question=f"Citation QA FAIL: {len(citation_report.missing_keys)} missing keys: {', '.join(citation_report.missing_keys[:10])}",
                        context={"verdict": "FAIL", "missing_keys": citation_report.missing_keys},
                        priority=TicketPriority.CRITICAL,
                        blocking=True,
                    ))
            except Exception as cqa_err:
                logger.warning(f"v1.2: CitationQAChecker failed (non-blocking): {cqa_err}")

            document = self.create_document(
                doc_type=DocumentType.CITATION_REPORT,
                content=response,
                status=DocumentStatus.COMPLETED,
                inputs=["06_Assembly_Kit_Outline"],
                outputs=["06_Citation_Report"],
            )

            await self.save_and_commit(document, "step_4_citation_qa: Citation QA completed")
            await self.save_to_artifact_store(response, DocumentType.CITATION_REPORT, ArtifactStatus.DRAFT)
            _advance_delivery_state(self.project, DeliveryState.ASSEMBLING)

            return document

        except StepExecutionError:
            raise
        except Exception as e:
            logger.error(f"Step 4 Citation QA failed: {e}")
            raise StepExecutionError(f"Step 4 Citation QA failed: {e}")


class Step4_ReproCheck(BaseStep):
    """v1.2 Step 4 Repro Check (D4): Artifact 完整性验证"""

    @property
    def step_id(self) -> str:
        return "step_4_repro"

    @property
    def step_name(self) -> str:
        return "Reproducibility Check"

    @property
    def output_doc_type(self) -> DocumentType:
        return DocumentType.REPRO_CHECK

    @property
    def ai_model(self) -> str:
        from app.config import settings
        return settings.claude_model

    async def execute(self) -> Document:
        try:
            import json
            import hashlib
            logger.info(f"Starting {self.step_name} for project {self.project.project_id}")
            _check_delivery_state(self.project, self.step_id)

            from app.config import settings
            project_path = Path(settings.projects_path) / self.project.project_id
            exec_dir = project_path / "execution"

            # Load all FROZEN_MANIFEST files
            manifests = {}
            verification_results = []
            if exec_dir.exists():
                for mf in exec_dir.glob("FROZEN_MANIFEST_*.json"):
                    try:
                        data = json.loads(mf.read_text(encoding="utf-8"))
                        wp_id = data.get("wp_id", mf.stem)
                        manifests[wp_id] = data
                        for art_path, art_info in data.get("artifacts", {}).items():
                            full_path = project_path / art_path
                            if full_path.exists():
                                actual_sha = hashlib.sha256(full_path.read_bytes()).hexdigest()
                                match = actual_sha == art_info.get("sha256", "")
                                verification_results.append({
                                    "wp_id": wp_id, "artifact": art_path,
                                    "expected_sha256": art_info.get("sha256", "")[:16] + "...",
                                    "match": match,
                                })
                            else:
                                verification_results.append({
                                    "wp_id": wp_id, "artifact": art_path,
                                    "expected_sha256": art_info.get("sha256", "")[:16] + "...",
                                    "match": False, "error": "file not found",
                                })
                    except Exception as e:
                        logger.warning(f"Failed to load manifest {mf}: {e}")

            all_match = all(v.get("match", False) for v in verification_results)
            total = len(verification_results)
            passed = sum(1 for v in verification_results if v.get("match", False))

            # Build report via AI
            manifest_summary = json.dumps(manifests, indent=2, ensure_ascii=False)[:3000]
            verification_summary = json.dumps(verification_results, indent=2, ensure_ascii=False)[:3000]

            prompt = render_repro_check_prompt(manifest_summary, verification_summary)

            response = await self._dispatch_ai("review").chat(
                prompt,
                system_prompt="You are a Reproducibility Verification Specialist.",
            )

            self.log_ai_conversation(
                model=self.ai_model, system_prompt="Repro Check",
                user_prompt=prompt[:500], response=response[:1000]
            )

            # Save structured report
            report = {
                "verdict": "PASS" if all_match else "FAIL",
                "total_artifacts": total,
                "verified": passed,
                "failed": total - passed,
                "details": verification_results,
            }
            report_path = project_path / "delivery" / "repro_check_report.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

            # §4.3 D4: FAIL → blocking HIL
            if not all_match:
                from app.services.hil_service import HILService
                from app.models.hil import HILTicketCreate, TicketPriority, QuestionType
                hil = HILService()
                await hil.create_ticket(HILTicketCreate(
                    project_id=self.project.project_id,
                    step_id="step_4_repro",
                    question_type=QuestionType.VALIDATION,
                    question=f"Reproducibility FAIL: {total - passed}/{total} artifacts mismatch",
                    context={"verdict": "FAIL", "failed": total - passed, "total": total},
                    priority=TicketPriority.CRITICAL,
                    blocking=True,
                ))

            document = self.create_document(
                doc_type=DocumentType.REPRO_CHECK,
                content=response,
                status=DocumentStatus.COMPLETED,
                inputs=["FROZEN_MANIFEST_*.json"],
                outputs=["06_Repro_Check"],
            )

            await self.save_and_commit(document, "step_4_repro: Reproducibility check completed")
            _advance_delivery_state(self.project, DeliveryState.CITATION_QA)

            # §4.4 Deliv-Loop2: Human checkpoint — 确认可复现性验证结果
            try:
                from app.services.hil_service import HILService
                from app.models.hil import HILTicketCreate, TicketPriority, QuestionType
                hil = HILService()
                await hil.create_ticket(HILTicketCreate(
                    project_id=self.project.project_id,
                    step_id="step_4_repro",
                    question_type=QuestionType.VALIDATION,
                    question=f"Deliv-Loop2: 可复现性验证完成 ({passed}/{total} passed)。请确认结果。",
                    context={"checkpoint": "Deliv-Loop2", "passed": passed, "total": total},
                    priority=TicketPriority.HIGH,
                    blocking=True,
                ))
            except Exception as cp_err:
                logger.warning(f"v1.2: Deliv-Loop2 checkpoint HIL failed (non-blocking): {cp_err}")

            return document

        except StepExecutionError:
            raise
        except Exception as e:
            logger.error(f"Step 4 Repro Check failed: {e}")
            raise StepExecutionError(f"Step 4 Repro Check failed: {e}")


class Step4_Package(BaseStep):
    """Step 4 Package (D5): 按 delivery_profile 打包"""

    @property
    def step_id(self) -> str:
        return "step_4_package"

    @property
    def step_name(self) -> str:
        return "Delivery Packaging"

    @property
    def output_doc_type(self) -> DocumentType:
        return DocumentType.DELIVERY_MANIFEST

    @property
    def ai_model(self) -> str:
        from app.config import settings
        return settings.claude_model

    async def execute(self) -> Document:
        try:
            logger.info(f"Starting {self.step_name} for project {self.project.project_id}")
            _check_delivery_state(self.project, self.step_id)

            # v1.2 §4.4 Deliv-Loop3: Checkpoint — 确认 delivery_profile 选择
            try:
                from app.services.hil_service import HILService
                from app.models.hil import HILTicketCreate, TicketPriority, QuestionType
                hil = HILService()
                await hil.create_ticket(HILTicketCreate(
                    project_id=self.project.project_id,
                    step_id="step_4_package",
                    question_type=QuestionType.VALIDATION,
                    question="请确认 delivery_profile 选择（external_assembly_kit / internal_draft）",
                    context={"checkpoint": "Deliv-Loop3"},
                    priority=TicketPriority.HIGH,
                    blocking=True,
                ))
            except Exception as cp_err:
                logger.warning(f"v1.2: Deliv-Loop3 checkpoint HIL failed (non-blocking): {cp_err}")

            # §4.3 D5: Pre-package gate checks
            import json as _json
            from app.config import settings as app_settings
            project_path = Path(app_settings.projects_path) / self.project.project_id
            gate_failures = []

            # Check 1: Citation QA passed
            citation_path = project_path / "delivery" / "citation_report.json"
            if citation_path.exists():
                cit_data = _json.loads(citation_path.read_text(encoding="utf-8"))
                if cit_data.get("verdict") != "PASS":
                    gate_failures.append(f"Citation QA verdict: {cit_data.get('verdict')}")
            else:
                gate_failures.append("Citation QA report not found")

            # Check 2: Repro check passed
            repro_path = project_path / "delivery" / "repro_check_report.json"
            if repro_path.exists():
                repro_data = _json.loads(repro_path.read_text(encoding="utf-8"))
                if repro_data.get("verdict") != "PASS":
                    gate_failures.append(f"Repro check verdict: {repro_data.get('verdict')}")
            else:
                gate_failures.append("Repro check report not found")

            # Check 3: Assembly kit exists
            assembly_doc = await self.load_context_with_fallback(
                step_id="step_4_assembly", doc_type=DocumentType.ASSEMBLY_KIT_OUTLINE
            )
            if not assembly_doc:
                gate_failures.append("Assembly Kit not found")

            # Check 4: D8 Forbidden output — external_assembly_kit 禁止 draft.tex/draft.md
            delivery_profile = _resolve_delivery_profile(self.project)
            if delivery_profile == "external_assembly_kit":
                paper_dir = project_path / "delivery" / "paper"
                if paper_dir.exists():
                    forbidden = [f.name for f in paper_dir.iterdir()
                                 if f.name in ("draft.tex", "draft.md")]
                    if forbidden:
                        gate_failures.append(
                            f"D8: external_assembly_kit 禁止输出 {', '.join(forbidden)}"
                        )

            if gate_failures:
                raise StepExecutionError(f"Pre-package gate FAIL: {'; '.join(gate_failures)}")

            manifest = await self.load_context_with_fallback(
                step_id="step_4_collect", doc_type=DocumentType.DELIVERY_MANIFEST
            ) or ""

            assembly = await self.load_context_with_fallback(
                step_id="step_4_assembly", doc_type=DocumentType.ASSEMBLY_KIT_OUTLINE
            ) or ""

            citation_report = await self.load_context_with_fallback(
                step_id="step_4_citation_qa", doc_type=DocumentType.CITATION_REPORT
            ) or ""

            prompt = render_package_prompt(manifest, assembly, citation_report)

            response = await self._dispatch_ai("packaging").chat(
                prompt,
                system_prompt="You are a Research Delivery Packager.",
            )

            self.log_ai_conversation(
                model=self.ai_model, system_prompt="Delivery packaging",
                user_prompt=prompt[:500], response=response[:1000]
            )

            # 更新项目标志
            self.project.step4_completed = True

            document = self.create_document(
                doc_type=DocumentType.DELIVERY_MANIFEST,
                content=response,
                status=DocumentStatus.COMPLETED,
                inputs=["06_Delivery_Manifest", "06_Assembly_Kit_Outline", "06_Citation_Report"],
                outputs=["06_Delivery_Package"],
            )

            await self.save_and_commit(document, "step_4_package: Delivery package created")
            await self.save_to_artifact_store(response, DocumentType.DELIVERY_MANIFEST, ArtifactStatus.FROZEN)
            _advance_delivery_state(self.project, DeliveryState.REPRO_CHECK)

            # ── Phase D: Handoff audit + convergence stats (non-blocking) ──
            try:
                _export_handoff_audit(project_path)
            except Exception as ha_err:
                logger.warning(f"Handoff audit export failed (non-blocking): {ha_err}")

            # v7.1 S3-2: Export error chain trace bundle
            try:
                from app.services.memory_store import MemoryStore
                from app.config import settings
                project_path = str(Path(settings.projects_path) / self.project.project_id)
                memory_store = MemoryStore(project_path)
                bundle = memory_store.export_to_trace_bundle()
                logger.info(f"Trace bundle exported: {len(bundle.get('error_patterns', []))} error patterns")
            except Exception as tb_err:
                logger.warning(f"Trace bundle export failed (non-blocking): {tb_err}")

            return document

        except StepExecutionError:
            raise
        except Exception as e:
            logger.error(f"Step 4 Package failed: {e}")
            raise StepExecutionError(f"Step 4 Package failed: {e}")
