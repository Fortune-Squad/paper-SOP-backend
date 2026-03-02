"""
S-1 Bootloader

预项目启动阶段，生成 Domain Dictionary、OOT Candidates 和 Resource Card

v6.0 NEW: Pre-project initialization phase
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class DomainTerm(BaseModel):
    """领域术语"""
    term: str = Field(..., description="术语名称")
    definition: str = Field(..., description="术语定义")
    synonyms: List[str] = Field(default_factory=list, description="同义词")
    related_terms: List[str] = Field(default_factory=list, description="相关术语")
    importance: str = Field(..., description="重要性 (high/medium/low)")


class DomainDictionary(BaseModel):
    """领域词典"""
    domain: str = Field(..., description="研究领域")
    terms: List[DomainTerm] = Field(default_factory=list, description="术语列表")
    created_at: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class OOTCandidate(BaseModel):
    """Out-of-Tree (OOT) 候选主题"""
    topic: str = Field(..., description="主题名称")
    description: str = Field(..., description="主题描述")
    novelty_score: float = Field(..., ge=0, le=1, description="新颖性评分 (0-1)")
    feasibility_score: float = Field(..., ge=0, le=1, description="可行性评分 (0-1)")
    impact_score: float = Field(..., ge=0, le=1, description="影响力评分 (0-1)")
    rationale: str = Field(..., description="推荐理由")
    risks: List[str] = Field(default_factory=list, description="潜在风险")


class OOTCandidates(BaseModel):
    """OOT 候选主题列表"""
    domain: str = Field(..., description="研究领域")
    candidates: List[OOTCandidate] = Field(default_factory=list, description="候选主题列表")
    created_at: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ResourceItem(BaseModel):
    """资源项"""
    resource_type: str = Field(..., description="资源类型 (dataset/tool/paper/expert)")
    name: str = Field(..., description="资源名称")
    description: str = Field(..., description="资源描述")
    url: Optional[str] = Field(None, description="资源链接")
    availability: str = Field(..., description="可用性 (public/restricted/private)")
    relevance_score: float = Field(..., ge=0, le=1, description="相关性评分 (0-1)")


class ResourceCard(BaseModel):
    """资源卡片"""
    domain: str = Field(..., description="研究领域")
    resources: List[ResourceItem] = Field(default_factory=list, description="资源列表")
    created_at: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BootloaderResult(BaseModel):
    """Bootloader 执行结果"""
    domain_dictionary: DomainDictionary
    oot_candidates: OOTCandidates
    resource_card: ResourceCard
    execution_time: float = Field(..., description="执行时间（秒）")
    created_at: datetime = Field(default_factory=datetime.now)
