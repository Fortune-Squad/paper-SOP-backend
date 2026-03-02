"""
MEMORY.md 管理器
v1.2 DevSpec §5.7 - 四层持久化记忆体系之纠错记忆层
v7.1: 升级为 4 层记忆 (error_patterns, strategies, decisions, corrections)

管理 [LEARN:tag] 条目和 Key Facts，控制 token 预算 (< 500 tokens)
"""
import json
import re
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum

logger = logging.getLogger(__name__)

LEARN_DOMAINS = [
    "numerical", "wireless", "gpt-drift", "gemini-cite",
    "workflow", "freeze", "boundary", "token"
]


class MemoryEntryType(str, Enum):
    """v7.1 记忆条目类型"""
    ERROR_PATTERN = "error_pattern"
    STRATEGY = "strategy"
    DECISION = "decision"
    LEARN = "learn"


class MemoryEntry(BaseModel):
    """v7.1 通用记忆条目"""
    entry_type: MemoryEntryType = Field(..., description="条目类型")
    symptom: str = Field(default="", description="症状/触发条件")
    root_cause: str = Field(default="", description="根因")
    correction: str = Field(default="", description="修正措施")
    prevention: str = Field(default="", description="预防措施")
    source_actor: str = Field(default="system", description="来源角色 (chatgpt/gemini/claude/human)")
    wp_id: str = Field(default="", description="关联 WP ID")
    exportable: bool = Field(default=True, description="是否可导出到 trace bundle")
    added_at: datetime = Field(default_factory=datetime.now)


class LearnEntry(BaseModel):
    """[LEARN:tag] 条目 (backward compatible)"""
    domain: str = Field(..., description="领域标签")
    lesson: str = Field(..., description="教训内容 (<= 100 chars)")
    added_at: datetime = Field(default_factory=datetime.now)
    source: str = Field(default="system", description="来源: gate_failure/escalation/human/conflict")

class MemoryData(BaseModel):
    """MEMORY.md 数据结构 (v7.1: 4 层)"""
    key_facts: List[str] = Field(default_factory=list)
    corrections: List[LearnEntry] = Field(default_factory=list)
    # v7.1 新增 3 层
    error_patterns: List[MemoryEntry] = Field(default_factory=list)
    strategies: List[MemoryEntry] = Field(default_factory=list)
    decisions: List[MemoryEntry] = Field(default_factory=list)

class MemoryStore:
    """
    MEMORY.md 的唯一读写接口
    
    功能:
    - 读写 MEMORY.md 文件
    - 管理 [LEARN:tag] 条目
    - 管理 Key Facts
    - Token 预算控制 (< 500 tokens)
    - 按 tag 过滤相关条目
    """
    
    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.memory_path = self.project_path / "MEMORY.md"
    
    def initialize(self) -> None:
        """首次创建 MEMORY.md"""
        if self.memory_path.exists():
            logger.info(f"MEMORY.md already exists at {self.memory_path}")
            return
        
        template = """# Project Memory

## Key Facts
- Project managed by SignalPass SOP v7.1
- delivery_profile default: external_assembly_kit

## Error Patterns

## Strategies

## Decisions

## Corrections Log
"""
        self.memory_path.write_text(template, encoding="utf-8")
        logger.info(f"Initialized MEMORY.md at {self.memory_path}")
    
    def load(self) -> MemoryData:
        """读取并解析 MEMORY.md"""
        if not self.memory_path.exists():
            return MemoryData()
        
        content = self.memory_path.read_text(encoding="utf-8")
        return self._parse(content)
    
    def save(self, data: MemoryData) -> None:
        """序列化并写回 MEMORY.md"""
        content = self._serialize(data)
        self.memory_path.write_text(content, encoding="utf-8")
        logger.info(f"Saved MEMORY.md ({len(data.corrections)} corrections, {len(data.key_facts)} facts)")
    
    def add_learn_entry(self, domain: str, lesson: str, source: str = "system") -> None:
        """
        添加 [LEARN:tag] 条目
        
        Args:
            domain: 领域标签 (numerical/wireless/gpt-drift/etc.)
            lesson: 教训内容 (<= 100 chars)
            source: 来源 (gate_failure/escalation/human/conflict)
        """
        if len(lesson) > 100:
            lesson = lesson[:97] + "..."
            logger.warning(f"Lesson truncated to 100 chars")
        
        data = self.load()
        entry = LearnEntry(domain=domain, lesson=lesson, source=source)
        data.corrections.append(entry)
        
        # 控制总条目数 < 50
        if len(data.corrections) > 50:
            data.corrections = data.corrections[-50:]
            logger.warning("Corrections log trimmed to 50 entries")
        
        self.save(data)
        logger.info(f"Added [LEARN:{domain}] entry: {lesson[:50]}...")
    
    def remove_learn_entry(self, index: int) -> bool:
        """删除指定索引的 [LEARN:tag] 条目"""
        data = self.load()
        if 0 <= index < len(data.corrections):
            removed = data.corrections.pop(index)
            self.save(data)
            logger.info(f"Removed [LEARN:{removed.domain}] entry at index {index}")
            return True
        return False
    
    def add_key_fact(self, fact: str) -> None:
        """添加 Key Fact"""
        data = self.load()
        data.key_facts.append(fact)
        self.save(data)
        logger.info(f"Added key fact: {fact[:50]}...")

    def add_error_pattern(
        self, symptom: str, root_cause: str, correction: str,
        prevention: str = "", source_actor: str = "system", wp_id: str = ""
    ) -> None:
        """v7.1: 添加 Error Pattern 条目"""
        data = self.load()
        entry = MemoryEntry(
            entry_type=MemoryEntryType.ERROR_PATTERN,
            symptom=symptom[:200], root_cause=root_cause[:200],
            correction=correction[:200], prevention=prevention[:200],
            source_actor=source_actor, wp_id=wp_id,
        )
        data.error_patterns.append(entry)
        if len(data.error_patterns) > 50:
            data.error_patterns = data.error_patterns[-50:]
        self.save(data)
        logger.info(f"Added error_pattern: {symptom[:50]}...")

    def add_strategy(
        self, symptom: str, correction: str,
        source_actor: str = "system", wp_id: str = ""
    ) -> None:
        """v7.1: 添加 Strategy 条目"""
        data = self.load()
        entry = MemoryEntry(
            entry_type=MemoryEntryType.STRATEGY,
            symptom=symptom[:200], correction=correction[:200],
            source_actor=source_actor, wp_id=wp_id,
        )
        data.strategies.append(entry)
        if len(data.strategies) > 50:
            data.strategies = data.strategies[-50:]
        self.save(data)
        logger.info(f"Added strategy: {symptom[:50]}...")

    def add_decision(
        self, symptom: str, correction: str, root_cause: str = "",
        source_actor: str = "human", wp_id: str = ""
    ) -> None:
        """v7.1: 添加 Decision 条目"""
        data = self.load()
        entry = MemoryEntry(
            entry_type=MemoryEntryType.DECISION,
            symptom=symptom[:200], correction=correction[:200],
            root_cause=root_cause[:200],
            source_actor=source_actor, wp_id=wp_id,
        )
        data.decisions.append(entry)
        if len(data.decisions) > 50:
            data.decisions = data.decisions[-50:]
        self.save(data)
        logger.info(f"Added decision: {symptom[:50]}...")
    
    def add_conflict_resolution(
        self, wp_id: str, actor_a: str, actor_b: str,
        conflict_desc: str, resolution: str, arbiter: str = "human"
    ) -> None:
        """§2.2.7: 跨模型冲突裁决后写入 decision + learn 两层"""
        self.add_decision(
            symptom=f"Conflict [{actor_a} vs {actor_b}]: {conflict_desc[:150]}",
            correction=resolution[:200],
            root_cause=f"Cross-model disagreement on WP {wp_id}",
            source_actor=arbiter,
            wp_id=wp_id,
        )
        self.add_learn_entry(
            domain="conflict",
            lesson=f"[{actor_a} vs {actor_b}] {conflict_desc[:60]} → {resolution[:60]}",
            source="conflict",
        )

    def get_relevant_entries(self, tags: List[str]) -> List[str]:
        """
        按 tag 过滤相关 [LEARN:tag] 条目
        
        Args:
            tags: 要过滤的领域标签列表
            
        Returns:
            格式化的相关条目列表
        """
        data = self.load()
        entries = []
        for entry in data.corrections:
            if entry.domain in tags:
                entries.append(f"[LEARN:{entry.domain}] {entry.lesson}")
        return entries
    
    def get_all_entries_formatted(self) -> str:
        """获取所有条目的格式化文本（用于 prompt 注入）"""
        data = self.load()
        lines = []
        if data.key_facts:
            lines.append("Key Facts:")
            for fact in data.key_facts:
                lines.append(f"- {fact}")
        if data.error_patterns:
            lines.append("\nError Patterns:")
            for entry in data.error_patterns:
                lines.append(f"- {entry.symptom} → {entry.correction}")
        if data.strategies:
            lines.append("\nStrategies:")
            for entry in data.strategies:
                lines.append(f"- {entry.symptom} → {entry.correction}")
        if data.decisions:
            lines.append("\nDecisions:")
            for entry in data.decisions:
                lines.append(f"- {entry.symptom} → {entry.correction}")
        if data.corrections:
            lines.append("\nCorrections:")
            for entry in data.corrections:
                lines.append(f"- [LEARN:{entry.domain}] {entry.lesson}")
        return "\n".join(lines)
    
    def get_token_count(self) -> int:
        """
        估算 MEMORY.md 的 token 数
        粗略估算: 1 token ≈ 4 chars (英文) 或 1.5 chars (中文混合)
        """
        if not self.memory_path.exists():
            return 0
        content = self.memory_path.read_text(encoding="utf-8")
        # 混合语言估算: 平均 2.5 chars per token
        return len(content) // 3
    
    def is_within_budget(self) -> bool:
        """检查是否在 token 预算内 (< 500 tokens)"""
        return self.get_token_count() < 500
    
    def get_injection_content(self, relevant_tags: Optional[List[str]] = None, max_tokens: int = 500) -> str:
        """
        获取用于 prompt 注入的内容，控制在 token 预算内
        
        Args:
            relevant_tags: 相关的领域标签（None 则返回全部）
            max_tokens: 最大 token 数
            
        Returns:
            格式化的注入内容
        """
        data = self.load()
        lines = []
        
        # 始终包含 Key Facts
        for fact in data.key_facts:
            lines.append(f"- {fact}")
        
        # 过滤 corrections
        corrections = data.corrections
        if relevant_tags:
            corrections = [e for e in corrections if e.domain in relevant_tags]
        
        for entry in corrections:
            lines.append(f"- [LEARN:{entry.domain}] {entry.lesson}")
        
        content = "\n".join(lines)
        
        # Token 预算控制: 如果超出，只保留 Key Facts + 最近 10 条
        estimated_tokens = len(content) // 3
        if estimated_tokens > max_tokens:
            lines = []
            for fact in data.key_facts:
                lines.append(f"- {fact}")
            recent = corrections[-10:] if len(corrections) > 10 else corrections
            for entry in recent:
                lines.append(f"- [LEARN:{entry.domain}] {entry.lesson}")
            content = "\n".join(lines)
        
        return content
    
    def _parse(self, content: str) -> MemoryData:
        """解析 MEMORY.md 内容 (v7.1: 4 层)"""
        key_facts = []
        corrections = []
        error_patterns = []
        strategies = []
        decisions = []

        current_section = None

        for line in content.split("\n"):
            line = line.strip()

            if line.startswith("## Key Facts"):
                current_section = "facts"
                continue
            elif line.startswith("## Error Patterns"):
                current_section = "error_patterns"
                continue
            elif line.startswith("## Strategies"):
                current_section = "strategies"
                continue
            elif line.startswith("## Decisions"):
                current_section = "decisions"
                continue
            elif line.startswith("## Corrections Log"):
                current_section = "corrections"
                continue
            elif line.startswith("## "):
                current_section = None
                continue

            if not line.startswith("- "):
                continue

            text = line[2:].strip()

            if current_section == "facts":
                key_facts.append(text)
            elif current_section == "corrections":
                match = re.match(r'\[LEARN:(\w[\w-]*)\]\s*(.*)', text)
                if match:
                    corrections.append(LearnEntry(domain=match.group(1), lesson=match.group(2)))
                else:
                    corrections.append(LearnEntry(domain="general", lesson=text))
            elif current_section == "error_patterns":
                error_patterns.append(self._parse_memory_entry(MemoryEntryType.ERROR_PATTERN, text))
            elif current_section == "strategies":
                strategies.append(self._parse_memory_entry(MemoryEntryType.STRATEGY, text))
            elif current_section == "decisions":
                decisions.append(self._parse_memory_entry(MemoryEntryType.DECISION, text))

        return MemoryData(
            key_facts=key_facts, corrections=corrections,
            error_patterns=error_patterns, strategies=strategies, decisions=decisions,
        )

    @staticmethod
    def _parse_memory_entry(entry_type: MemoryEntryType, text: str) -> MemoryEntry:
        """解析单条 MemoryEntry 行: [symptom] → correction (actor, wp_id)"""
        actor = "system"
        wp_id = ""
        # Try to extract (actor, wp_id) suffix
        paren_match = re.search(r'\((\w+)(?:,\s*([\w-]+))?\)\s*$', text)
        if paren_match:
            actor = paren_match.group(1)
            wp_id = paren_match.group(2) or ""
            text = text[:paren_match.start()].strip()
        # Split on →
        parts = text.split("→", 1)
        symptom = parts[0].strip()
        correction = parts[1].strip() if len(parts) > 1 else ""
        return MemoryEntry(
            entry_type=entry_type, symptom=symptom, correction=correction,
            source_actor=actor, wp_id=wp_id,
        )

    def _serialize(self, data: MemoryData) -> str:
        """序列化为 MEMORY.md 格式 (v7.1: 4 层)"""
        lines = ["# Project Memory", ""]

        lines.append("## Key Facts")
        for fact in data.key_facts:
            lines.append(f"- {fact}")
        lines.append("")

        lines.append("## Error Patterns")
        for entry in data.error_patterns:
            lines.append(f"- {self._serialize_memory_entry(entry)}")
        lines.append("")

        lines.append("## Strategies")
        for entry in data.strategies:
            lines.append(f"- {self._serialize_memory_entry(entry)}")
        lines.append("")

        lines.append("## Decisions")
        for entry in data.decisions:
            lines.append(f"- {self._serialize_memory_entry(entry)}")
        lines.append("")

        lines.append("## Corrections Log")
        for entry in data.corrections:
            lines.append(f"- [LEARN:{entry.domain}] {entry.lesson}")
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _serialize_memory_entry(entry: MemoryEntry) -> str:
        """序列化单条 MemoryEntry"""
        suffix = f"({entry.source_actor}"
        if entry.wp_id:
            suffix += f", {entry.wp_id}"
        suffix += ")"
        if entry.correction:
            return f"{entry.symptom} → {entry.correction} {suffix}"
        return f"{entry.symptom} {suffix}"

    def export_to_trace_bundle(self) -> Dict[str, Any]:
        """
        v7.1 S3-2: 导出 error_patterns 为 JSON trace bundle

        Returns:
            Dict: trace bundle 数据
        """
        data = self.load()
        bundle = {
            "exported_at": datetime.now().isoformat(),
            "error_patterns": [
                {
                    "symptom": e.symptom,
                    "root_cause": e.root_cause,
                    "correction": e.correction,
                    "prevention": e.prevention,
                    "source_actor": e.source_actor,
                    "wp_id": e.wp_id,
                }
                for e in data.error_patterns if e.exportable
            ],
            "strategies": [
                {
                    "symptom": e.symptom,
                    "correction": e.correction,
                    "source_actor": e.source_actor,
                    "wp_id": e.wp_id,
                }
                for e in data.strategies if e.exportable
            ],
            "total_corrections": len(data.corrections),
            "total_decisions": len(data.decisions),
        }
        # Save to file (JSONL format: one JSON object per line)
        bundle_path = self.project_path / "logs" / "trace_bundle.jsonl"
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        # Header line
        lines.append(json.dumps({"exported_at": bundle["exported_at"], "total_corrections": bundle["total_corrections"], "total_decisions": bundle["total_decisions"]}, ensure_ascii=False))
        # Error patterns
        for ep in bundle["error_patterns"]:
            lines.append(json.dumps({"type": "error_pattern", **ep}, ensure_ascii=False))
        # Strategies
        for st in bundle["strategies"]:
            lines.append(json.dumps({"type": "strategy", **st}, ensure_ascii=False))
        bundle_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"Exported trace bundle to {bundle_path}")
        return bundle
