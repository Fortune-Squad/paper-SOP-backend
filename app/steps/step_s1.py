"""
Step S-1 实现
Bootloader（预项目启动阶段）
"""
import logging
from typing import Dict, Any, List

from app.steps.base import BaseStep, StepExecutionError
from app.models.document import Document, DocumentType, DocumentStatus
from app.models.project import Project
from app.models.artifact import ArtifactStatus

logger = logging.getLogger(__name__)


class Step_S1_Bootloader(BaseStep):
    """Step S-1: Fuzzy Bootloader (Gemini)"""

    @property
    def step_id(self) -> str:
        return "step_s_1"

    @property
    def step_name(self) -> str:
        return "Fuzzy Bootloader"

    @property
    def output_doc_type(self) -> DocumentType:
        return DocumentType.DOMAIN_DICTIONARY

    @property
    def ai_model(self) -> str:
        from app.config import settings
        return settings.gemini_model

    async def execute(self) -> Document:
        """
        执行 Step S-1: Fuzzy Bootloader

        生成三个文档：
        1. Domain Dictionary (领域词典)
        2. OOT Candidates (Out-of-Tree 候选主题)
        3. Resource Card (资源卡片)

        Returns:
            Document: Domain Dictionary 文档（主文档）

        Raises:
            StepExecutionError: 执行失败时抛出
        """
        try:
            logger.info(f"Starting {self.step_name} for project {self.project.project_id}")

            # 获取用户输入
            domain = self.project.config.topic or "未指定领域"
            context = self.project.config.project_context or ""
            constraints = self.project.config.hard_constraints or []

            # v7.2 NEW: 读取用户填写的 Resource Card 表单数据
            user_resource_card = getattr(self.project.config, 'resource_card_input', None)

            logger.info(f"Bootloader input - Domain: {domain}, Context length: {len(context)}, "
                       f"Resource Card: {'user_input' if user_resource_card and not user_resource_card.get('is_skipped') else 'skipped' if user_resource_card else 'ai_generated'}")

            # 调用 Bootloader Service
            from app.services.bootloader_service import get_bootloader_service
            bootloader_service = get_bootloader_service()

            logger.info("Running Bootloader (3-phase generation)")
            bootloader_result = await bootloader_service.run_bootloader(
                domain=domain,
                context=context if context else None,
                constraints="\n".join(constraints) if constraints else None,
                focus_areas=None,
                user_resource_card=user_resource_card
            )

            logger.info(f"Bootloader completed: {len(bootloader_result.domain_dictionary.terms)} terms, "
                       f"{len(bootloader_result.oot_candidates.candidates)} candidates, "
                       f"{len(bootloader_result.resource_card.resources)} resources")

            # 生成三个文档
            documents = await self._save_bootloader_results(bootloader_result)

            # 记录 AI 对话（记录完整流程）
            self.log_ai_conversation(
                model=self.ai_model,
                system_prompt="Bootloader (3-phase generation)",
                user_prompt=f"Domain: {domain}",
                context=[context[:500]] if context else [],
                response=f"Generated {len(bootloader_result.domain_dictionary.terms)} terms, "
                         f"{len(bootloader_result.oot_candidates.candidates)} candidates, "
                         f"{len(bootloader_result.resource_card.resources)} resources",
                metadata={
                    "step_name": self.step_name,
                    "domain": domain,
                    "terms_count": len(bootloader_result.domain_dictionary.terms),
                    "candidates_count": len(bootloader_result.oot_candidates.candidates),
                    "resources_count": len(bootloader_result.resource_card.resources),
                    "execution_time": bootloader_result.execution_time
                }
            )

            # 保存主文档（Domain Dictionary）并提交
            main_document = documents[0]
            await self.save_and_commit(
                document=main_document,
                commit_message=f"{self.step_id}: Generate Bootloader artifacts (Domain Dictionary, OOT Candidates, Resource Card)"
            )

            logger.info(f"Completed {self.step_name}")
            return main_document

        except Exception as e:
            logger.error(f"Failed to execute {self.step_name}: {e}")
            raise StepExecutionError(f"Step S-1 failed: {e}")

    async def _save_bootloader_results(self, result) -> List[Document]:
        """
        保存 Bootloader 结果到文件

        Args:
            result: BootloaderResult 对象

        Returns:
            List[Document]: 生成的三个文档
        """
        from app.utils.file_manager import FileManager
        from pathlib import Path

        file_manager = FileManager()
        project_path = file_manager.get_project_path(self.project.project_id)

        # 创建 S-1_bootloader 目录
        bootloader_dir = project_path / "artifacts" / "S-1_bootloader"
        bootloader_dir.mkdir(parents=True, exist_ok=True)

        documents = []

        # 1. 保存 Domain Dictionary
        domain_dict_doc = self._create_domain_dictionary_document(result.domain_dictionary)
        domain_dict_path = bootloader_dir / "S-1_Domain_Dictionary.md"
        with open(domain_dict_path, 'w', encoding='utf-8') as f:
            f.write(domain_dict_doc.to_markdown())
        logger.info(f"Saved Domain Dictionary to: {domain_dict_path}")
        documents.append(domain_dict_doc)

        # 保存到 Artifact Store
        await self.save_to_artifact_store(
            content=domain_dict_doc.content,
            doc_type=DocumentType.DOMAIN_DICTIONARY,
            status=ArtifactStatus.FROZEN
        )

        # 2. 保存 OOT Candidates
        oot_doc = self._create_oot_candidates_document(result.oot_candidates)
        oot_path = bootloader_dir / "S-1_OOT_Candidates.md"
        with open(oot_path, 'w', encoding='utf-8') as f:
            f.write(oot_doc.to_markdown())
        logger.info(f"Saved OOT Candidates to: {oot_path}")
        documents.append(oot_doc)

        # 保存到 Artifact Store
        await self.save_to_artifact_store(
            content=oot_doc.content,
            doc_type=DocumentType.OOT_CANDIDATES,
            status=ArtifactStatus.FROZEN
        )

        # 3. 保存 Resource Card
        resource_doc = self._create_resource_card_document(result.resource_card)
        resource_path = bootloader_dir / "S-1_Resource_Card.md"
        with open(resource_path, 'w', encoding='utf-8') as f:
            f.write(resource_doc.to_markdown())
        logger.info(f"Saved Resource Card to: {resource_path}")
        documents.append(resource_doc)

        # 保存到 Artifact Store
        await self.save_to_artifact_store(
            content=resource_doc.content,
            doc_type=DocumentType.RESOURCE_CARD,
            status=ArtifactStatus.FROZEN
        )

        return documents

    def _create_domain_dictionary_document(self, domain_dict) -> Document:
        """生成 Domain Dictionary 文档 — 优先使用 AI 原始响应"""
        raw_response = domain_dict.metadata.get("raw_response", "")

        if raw_response:
            content = f"""# Domain Dictionary

**Domain**: {domain_dict.domain}
**Generated**: {domain_dict.created_at.strftime('%Y-%m-%d %H:%M:%S')}
**Generated By**: {domain_dict.metadata.get('generated_by', 'AI')}
**Terms Extracted**: {len(domain_dict.terms)}

---

{raw_response}
"""
        else:
            # fallback: 使用解析后的结构化数据
            content = f"""# Domain Dictionary

**Domain**: {domain_dict.domain}
**Generated**: {domain_dict.created_at.strftime('%Y-%m-%d %H:%M:%S')}

---

## Terms

"""
            for term in domain_dict.terms:
                content += f"""### {term.term}

**Importance**: {term.importance}

**Definition**: {term.definition}

**Synonyms**: {', '.join(term.synonyms) if term.synonyms else 'None'}

**Related Terms**: {', '.join(term.related_terms) if term.related_terms else 'None'}

---

"""

        document = self.create_document(
            doc_type=DocumentType.DOMAIN_DICTIONARY,
            content=content,
            status=DocumentStatus.COMPLETED,
            inputs=[],
            outputs=[DocumentType.OOT_CANDIDATES.value, DocumentType.RESOURCE_CARD.value]
        )

        return document

    def _create_oot_candidates_document(self, oot_candidates) -> Document:
        """生成 OOT Candidates 文档 — 优先使用 AI 原始响应"""
        raw_response = oot_candidates.metadata.get("raw_response", "")

        if raw_response:
            content = f"""# Out-of-Tree (OOT) Candidates

**Domain**: {oot_candidates.domain}
**Generated**: {oot_candidates.created_at.strftime('%Y-%m-%d %H:%M:%S')}
**Generated By**: {oot_candidates.metadata.get('generated_by', 'AI')}
**Candidates Extracted**: {len(oot_candidates.candidates)}

---

{raw_response}
"""
        else:
            # fallback: 使用解析后的结构化数据
            content = f"""# Out-of-Tree (OOT) Candidates

**Domain**: {oot_candidates.domain}
**Generated**: {oot_candidates.created_at.strftime('%Y-%m-%d %H:%M:%S')}

---

## Candidates

"""
            for i, candidate in enumerate(oot_candidates.candidates, 1):
                content += f"""### Candidate {i}: {candidate.topic}

**Description**: {candidate.description}

**Scores**:
- Novelty: {candidate.novelty_score:.2f} / 1.0
- Feasibility: {candidate.feasibility_score:.2f} / 1.0
- Impact: {candidate.impact_score:.2f} / 1.0

**Rationale**: {candidate.rationale}

**Potential Risks**:
"""
                for risk in candidate.risks:
                    content += f"- {risk}\n"
                content += "\n---\n\n"

        document = self.create_document(
            doc_type=DocumentType.OOT_CANDIDATES,
            content=content,
            status=DocumentStatus.COMPLETED,
            inputs=[DocumentType.DOMAIN_DICTIONARY.value],
            outputs=[DocumentType.RESOURCE_CARD.value]
        )

        return document

    def _create_resource_card_document(self, resource_card) -> Document:
        """生成 Resource Card 文档 — 根据来源选择不同模板"""
        source = resource_card.metadata.get("source", "")
        raw_response = resource_card.metadata.get("raw_response", "")

        if source in ("user_input", "default_skip"):
            # v7.2: 用户填写或跳过 → 使用 6 分类 markdown 模板
            content = self._render_user_resource_card(resource_card, source)
        elif raw_response:
            content = f"""# Resource Card

**Domain**: {resource_card.domain}
**Generated**: {resource_card.created_at.strftime('%Y-%m-%d %H:%M:%S')}
**Generated By**: {resource_card.metadata.get('generated_by', 'AI')}
**Resources Extracted**: {len(resource_card.resources)}

---

{raw_response}
"""
        else:
            # fallback: 使用解析后的结构化数据
            resources_by_type: Dict[str, List] = {}
            for resource in resource_card.resources:
                if resource.resource_type not in resources_by_type:
                    resources_by_type[resource.resource_type] = []
                resources_by_type[resource.resource_type].append(resource)

            content = f"""# Resource Card

**Domain**: {resource_card.domain}
**Generated**: {resource_card.created_at.strftime('%Y-%m-%d %H:%M:%S')}

---

## Resources by Type

"""
            for resource_type, resources in resources_by_type.items():
                content += f"""### {resource_type.upper()}

**Count**: {len(resources)}

"""
                for resource in resources:
                    content += f"""#### {resource.name}

**Availability**: {resource.availability}
**Relevance**: {resource.relevance_score:.2f} / 1.0

**Description**: {resource.description}

**URL**: {resource.url if resource.url else 'N/A'}

---

"""

        document = self.create_document(
            doc_type=DocumentType.RESOURCE_CARD,
            content=content,
            status=DocumentStatus.COMPLETED,
            inputs=[DocumentType.DOMAIN_DICTIONARY.value, DocumentType.OOT_CANDIDATES.value],
            outputs=[]
        )

        return document

    def _render_user_resource_card(self, resource_card, source: str) -> str:
        """
        渲染用户填写/跳过的 Resource Card 为 v7 SOP 6 分类 markdown

        Args:
            resource_card: ResourceCard 对象
            source: 来源 ("user_input" 或 "default_skip")

        Returns:
            str: markdown 内容
        """
        # 按 resource_type 建立查找表
        by_type = {}
        for r in resource_card.resources:
            by_type[r.resource_type] = r.description

        source_label = "用户填写" if source == "user_input" else "默认（纯理论/仿真研究）"
        note = resource_card.metadata.get("note", "")

        content = f"""# Resource Card — 资源盘点

**Domain**: {resource_card.domain}
**Generated**: {resource_card.created_at.strftime('%Y-%m-%d %H:%M:%S')}
**Source**: {source_label}

---

## 1. Data Access — 数据访问

{by_type.get('dataset', '_未填写_')}

## 2. Compute & Equipment — 计算与设备

{by_type.get('tool', '_未填写_')}

## 3. Domain Expertise — 领域专长

{by_type.get('expertise', '_未填写_')}

## 4. Reusable Code & Libraries — 可复用代码

{by_type.get('code', '_未填写_')}

## 5. Hard Constraints — 硬约束

{by_type.get('constraint', '_未填写_')}

## 6. Explicit Gaps — 显式缺口

{by_type.get('gap', '_未填写_')}
"""
        if note:
            content += f"\n---\n\n> **Note**: {note}\n"

        return content
