"""
Citation QA Checker (v1.2 DevSpec §9.3 D7)
结构化引用验证 — 解析 outline 中的 citation keys 并与 refs.bib 比对
"""
import re
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class CitationReport:
    """引用验证报告"""
    used_keys: List[str] = field(default_factory=list)
    bib_keys: List[str] = field(default_factory=list)
    missing_keys: List[str] = field(default_factory=list)
    orphan_keys: List[str] = field(default_factory=list)
    verdict: str = "PENDING"

    @property
    def total_used(self) -> int:
        return len(self.used_keys)

    @property
    def total_bib(self) -> int:
        return len(self.bib_keys)

    def to_dict(self) -> Dict:
        return {
            "used_keys": self.used_keys,
            "bib_keys": self.bib_keys,
            "missing_keys": self.missing_keys,
            "orphan_keys": self.orphan_keys,
            "verdict": self.verdict,
            "total_used": self.total_used,
            "total_bib": self.total_bib,
        }


class CitationQAChecker:
    """轻量级引用完整性检查器"""

    # LaTeX: \cite{key}, \citep{key}, \citet{key}, \cite{k1,k2}
    LATEX_CITE_RE = re.compile(r'\\cite[pt]?\{([^}]+)\}')
    # Pandoc/Markdown: [@key], [@key1; @key2]
    PANDOC_CITE_RE = re.compile(r'\[@([^\]]+)\]')
    # BibTeX entry: @article{key, or @inproceedings{key,
    BIB_ENTRY_RE = re.compile(r'@\w+\{([^,\s]+)\s*,', re.MULTILINE)

    def check(self, outline_content: str, refs_bib_content: str) -> CitationReport:
        """
        执行引用完整性检查

        Args:
            outline_content: outline/assembly kit 内容（含 citation keys）
            refs_bib_content: refs.bib 内容

        Returns:
            CitationReport: 验证报告
        """
        used_keys = self._extract_citation_keys(outline_content)
        bib_keys = self._extract_bib_keys(refs_bib_content)

        used_set = set(used_keys)
        bib_set = set(bib_keys)

        missing_keys = sorted(used_set - bib_set)
        orphan_keys = sorted(bib_set - used_set)

        verdict = "PASS" if len(missing_keys) == 0 else "FAIL"

        report = CitationReport(
            used_keys=sorted(used_set),
            bib_keys=sorted(bib_set),
            missing_keys=missing_keys,
            orphan_keys=orphan_keys,
            verdict=verdict,
        )

        logger.info(
            f"CitationQA: {report.total_used} used, {report.total_bib} in bib, "
            f"{len(missing_keys)} missing, {len(orphan_keys)} orphan → {verdict}"
        )
        return report

    def _extract_citation_keys(self, content: str) -> List[str]:
        """从 outline 内容中提取所有 citation keys"""
        keys = []

        # LaTeX citations
        for match in self.LATEX_CITE_RE.finditer(content):
            raw = match.group(1)
            for key in raw.split(","):
                key = key.strip()
                if key:
                    keys.append(key)

        # Pandoc citations
        for match in self.PANDOC_CITE_RE.finditer(content):
            raw = match.group(1)
            for part in raw.split(";"):
                key = part.strip().lstrip("@").strip()
                if key:
                    keys.append(key)

        return keys

    def _extract_bib_keys(self, bib_content: str) -> List[str]:
        """从 .bib 内容中提取所有 entry keys"""
        keys = []
        for match in self.BIB_ENTRY_RE.finditer(bib_content):
            key = match.group(1).strip()
            if key:
                keys.append(key)
        return keys
