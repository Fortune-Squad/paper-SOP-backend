"""
文档数据模型
定义文档的结构和 YAML front-matter 格式
"""
from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class DocumentStatus(str, Enum):
    """文档状态枚举"""
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class GateStatus(str, Enum):
    """Gate 状态枚举"""
    PASSED = "passed"
    FAILED = "failed"
    PENDING = "pending"


class DocumentType(str, Enum):
    """文档类型枚举 (v6.0 - 27 types)"""
    # S-1 Bootloader (NEW v6.0)
    DOMAIN_DICTIONARY = "S-1_Domain_Dictionary"
    OOT_CANDIDATES = "S-1_OOT_Candidates"
    RESOURCE_CARD = "S-1_Resource_Card"

    # Step 0 - Project Bootstrapping
    PROJECT_INTAKE_CARD = "00_Project_Intake_Card"
    VENUE_TASTE_NOTES = "00_Venue_Taste_Notes"

    # Step 1 - Deep Research & Topic Freeze
    DEEP_RESEARCH_SUMMARY = "00_Deep_Research_Summary"
    SEARCH_QUERY_LOG = "00_Search_Query_Log"  # NEW v4.0
    LITERATURE_MATRIX = "00_Literature_Matrix"  # NEW v4.0
    REFERENCE_QA_REPORT = "00_Reference_QA_Report"  # NEW v4.0
    VERIFIED_REFERENCES = "00_Verified_References"  # NEW v4.0 (.bib file)

    SELECTED_TOPIC = "01_Selected_Topic"
    DRAFT_CLAIMS = "01_Draft_Claims"
    TOPIC_ALIGNMENT_CHECK = "01_Topic_Alignment_Check"  # NEW v4.0 (Gate 1.25)
    KILLER_PRIOR_CHECK = "01_Killer_Prior_Check"
    CLAIMS_AND_NONCLAIMS = "01_Claims_and_NonClaims"
    MINIMAL_VERIFICATION_SET = "01_Minimal_Verification_Set"
    PIVOT_RULES = "01_Pivot_Rules"
    FIGURE_FIRST_STORY = "01_Figure_First_Story"
    TITLE_ABSTRACT_CANDIDATES = "01_Title_Abstract_Candidates"

    # Step 2 - Blueprint & Engineering
    FIGURE_TABLE_LIST = "02_Figure_Table_List"  # NEW v4.0
    FULL_PROPOSAL = "02_Full_Proposal"
    DATA_SIM_SPEC = "02_Data_or_Sim_Spec"
    ENGINEERING_SPEC = "03_Engineering_Spec"
    TEST_PLAN = "03_TestPlan"
    REDTEAM_REVIEW = "03_RedTeam_Reviewer2"
    PATCH_DIFF = "03_Patch_Diff"  # NEW v4.0
    RESEARCH_PLAN_FROZEN = "04_Research_Plan_FROZEN"
    EXECUTION_ORDER = "04_Execution_Order"  # NEW v4.0
    STOP_OR_PIVOT_CHECKPOINTS = "04_Stop_or_Pivot_Checkpoints"  # NEW v4.0


class DocumentMetadata(BaseModel):
    """
    文档元数据（YAML front-matter）

    v4.0 Enhanced: Added evidence_quality, doi_validation, consistency_score
    v6.0 Enhanced: Added created_by, rigor_profile, gate_relevance for Artifact compatibility
    """
    model_config = ConfigDict(use_enum_values=True)

    doc_type: DocumentType = Field(..., description="文档类型")
    version: str = Field(default="1.0", description="文档版本")
    status: DocumentStatus = Field(default=DocumentStatus.DRAFT, description="文档状态")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")
    inputs: List[str] = Field(default_factory=list, description="输入文档列表")
    outputs: List[str] = Field(default_factory=list, description="输出文档列表")
    gate_status: Optional[GateStatus] = Field(default=None, description="Gate 状态")
    project_id: str = Field(..., description="项目 ID")

    # v4.0 New Fields
    north_star_question: Optional[str] = Field(default=None, description="北极星问题（来自 Intake Card）")
    evidence_quality: Optional[float] = Field(default=None, description="证据质量评分（0-1，用于 Reference QA）")
    doi_validation_passed: Optional[bool] = Field(default=None, description="DOI 验证是否通过")
    consistency_score: Optional[float] = Field(default=None, description="跨文档一致性评分（0-1）")

    # v6.0 New Fields (for Artifact compatibility)
    created_by: Optional[str] = Field(default="system", description="创建者（human/chatgpt/gemini/system）")
    rigor_profile: Optional[str] = Field(default=None, description="研究强度档位（top_journal/fast_track）")
    gate_relevance: Optional[str] = Field(default=None, description="关联的 Gate（如 gate_1_5, gate_2）")

    @field_validator('evidence_quality', 'consistency_score')
    @classmethod
    def validate_score_range(cls, v: Optional[float]) -> Optional[float]:
        """验证评分字段在 0-1 范围内"""
        if v is not None and (v < 0 or v > 1):
            raise ValueError(f'Score must be between 0 and 1, got {v}')
        return v


class Document(BaseModel):
    """文档模型"""
    metadata: DocumentMetadata = Field(..., description="文档元数据")
    content: str = Field(..., description="文档内容（Markdown）")

    def to_markdown(self) -> str:
        """
        将文档转换为带 YAML front-matter 的 Markdown 格式

        v6.0 Enhanced: Includes created_by, rigor_profile, gate_relevance

        Returns:
            str: 完整的 Markdown 文档
        """
        # 生成 YAML front-matter
        yaml_lines = ["---"]
        # 使用 getattr 处理枚举值，兼容 use_enum_values=True 的情况
        yaml_lines.append(f"doc_type: \"{getattr(self.metadata.doc_type, 'value', self.metadata.doc_type)}\"")
        yaml_lines.append(f"version: \"{self.metadata.version}\"")
        yaml_lines.append(f"status: \"{getattr(self.metadata.status, 'value', self.metadata.status)}\"")
        yaml_lines.append(f"created_at: \"{self.metadata.created_at.isoformat()}\"")
        yaml_lines.append(f"updated_at: \"{self.metadata.updated_at.isoformat()}\"")
        yaml_lines.append(f"inputs: {self.metadata.inputs}")
        yaml_lines.append(f"outputs: {self.metadata.outputs}")
        if self.metadata.gate_status:
            yaml_lines.append(f"gate_status: \"{getattr(self.metadata.gate_status, 'value', self.metadata.gate_status)}\"")
        yaml_lines.append(f"project_id: \"{self.metadata.project_id}\"")

        # v4.0 新增字段（可选）
        if self.metadata.north_star_question:
            yaml_lines.append(f"north_star_question: \"{self.metadata.north_star_question}\"")
        if self.metadata.evidence_quality is not None:
            yaml_lines.append(f"evidence_quality: {self.metadata.evidence_quality}")
        if self.metadata.doi_validation_passed is not None:
            yaml_lines.append(f"doi_validation_passed: {self.metadata.doi_validation_passed}")
        if self.metadata.consistency_score is not None:
            yaml_lines.append(f"consistency_score: {self.metadata.consistency_score}")

        # v6.0 新增字段（可选）
        if self.metadata.created_by:
            yaml_lines.append(f"created_by: \"{self.metadata.created_by}\"")
        if self.metadata.rigor_profile:
            yaml_lines.append(f"rigor_profile: \"{self.metadata.rigor_profile}\"")
        if self.metadata.gate_relevance:
            yaml_lines.append(f"gate_relevance: \"{self.metadata.gate_relevance}\"")

        yaml_lines.append("---")
        yaml_lines.append("")  # 空行分隔

        # 组合 YAML front-matter 和内容
        return "\n".join(yaml_lines) + self.content

    @classmethod
    def from_markdown(cls, markdown_text: str) -> "Document":
        """
        从带 YAML front-matter 的 Markdown 文本解析文档

        Args:
            markdown_text: 完整的 Markdown 文档

        Returns:
            Document: 解析后的文档对象
        """
        import yaml

        # 分离 YAML front-matter 和内容
        parts = markdown_text.split("---", 2)
        if len(parts) < 3:
            raise ValueError("Invalid document format: missing YAML front-matter")

        # 解析 YAML
        yaml_text = parts[1].strip()
        yaml_data = yaml.safe_load(yaml_text)

        # 解析时间字段
        if isinstance(yaml_data.get("created_at"), str):
            yaml_data["created_at"] = datetime.fromisoformat(yaml_data["created_at"])
        if isinstance(yaml_data.get("updated_at"), str):
            yaml_data["updated_at"] = datetime.fromisoformat(yaml_data["updated_at"])

        # 创建元数据对象
        metadata = DocumentMetadata(**yaml_data)

        # 提取内容
        content = parts[2].strip()

        return cls(metadata=metadata, content=content)

    def update_status(self, status: DocumentStatus):
        """更新文档状态"""
        self.metadata.status = status
        self.metadata.updated_at = datetime.now()

    def update_gate_status(self, gate_status: GateStatus):
        """更新 Gate 状态"""
        self.metadata.gate_status = gate_status
        self.metadata.updated_at = datetime.now()


class DocumentCreate(BaseModel):
    """创建文档的请求模型"""
    doc_type: DocumentType
    project_id: str
    content: str
    inputs: List[str] = Field(default_factory=list)
    outputs: List[str] = Field(default_factory=list)


class DocumentUpdate(BaseModel):
    """更新文档的请求模型"""
    content: Optional[str] = None
    status: Optional[DocumentStatus] = None
    gate_status: Optional[GateStatus] = None
