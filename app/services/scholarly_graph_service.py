"""
Scholarly Graph Service
v7.1 S1-1: 术语有效性检查 via OpenAlex + Crossref APIs

检查核心术语在学术文献中的命中率，用于 Gate 1.25 术语验证。
"""
import logging
import asyncio
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class TermStatus(str, Enum):
    """术语命中状态"""
    VALID = "valid"          # 两个 API 均有足够命中
    UNCERTAIN = "uncertain"  # 命中不足，需人工确认
    INVALID = "invalid"      # 几乎无命中


@dataclass
class TermHitResult:
    """单个术语的检查结果"""
    term: str
    openalex_count: int = 0
    crossref_count: int = 0
    status: TermStatus = TermStatus.UNCERTAIN
    also_known_as: List[str] = field(default_factory=list)


# 按 rigor_profile 配置的阈值
TERM_THRESHOLDS = {
    "top_journal": {"valid_min": 50, "uncertain_min": 5},
    "fast_track": {"valid_min": 20, "uncertain_min": 2},
    "clinical_high_value": {"valid_min": 100, "uncertain_min": 10},
    "structural_io": {"valid_min": 50, "uncertain_min": 5},
}

class ScholarlyGraphService:
    """
    学术图谱服务：通过 OpenAlex + Crossref 验证术语有效性

    用法:
        svc = ScholarlyGraphService(rigor_profile="top_journal")
        result = await svc.check_term("reconfigurable intelligent surface")
        results = await svc.check_terms_batch(["RIS", "MIMO", "fake_term_xyz"])
    """

    def __init__(self, rigor_profile: str = "top_journal", timeout: float = 10.0):
        self.rigor_profile = rigor_profile
        self.timeout = timeout
        thresholds = TERM_THRESHOLDS.get(rigor_profile, TERM_THRESHOLDS["top_journal"])
        self.valid_min = thresholds["valid_min"]
        self.uncertain_min = thresholds["uncertain_min"]

    async def check_term(self, term: str) -> TermHitResult:
        """
        检查单个术语在 OpenAlex + Crossref 中的命中数

        Args:
            term: 待检查术语

        Returns:
            TermHitResult
        """
        result = TermHitResult(term=term)

        # Parallel API calls with graceful degradation
        openalex_task = self._query_openalex(term)
        crossref_task = self._query_crossref(term)

        try:
            counts = await asyncio.wait_for(
                asyncio.gather(openalex_task, crossref_task, return_exceptions=True),
                timeout=self.timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(f"Timeout checking term '{term}', degrading gracefully")
            result.status = TermStatus.UNCERTAIN
            return result

        # Process OpenAlex result
        if isinstance(counts[0], int):
            result.openalex_count = counts[0]
        else:
            logger.warning(f"OpenAlex error for '{term}': {counts[0]}")

        # Process Crossref result
        if isinstance(counts[1], int):
            result.crossref_count = counts[1]
        else:
            logger.warning(f"Crossref error for '{term}': {counts[1]}")

        # Classify status
        total = result.openalex_count + result.crossref_count
        if total >= self.valid_min:
            result.status = TermStatus.VALID
        elif total >= self.uncertain_min:
            result.status = TermStatus.UNCERTAIN
        else:
            result.status = TermStatus.INVALID

        logger.info(
            f"Term '{term}': OpenAlex={result.openalex_count}, "
            f"Crossref={result.crossref_count}, status={result.status.value}"
        )
        return result

    async def check_terms_batch(self, terms: List[str]) -> List[TermHitResult]:
        """批量检查术语"""
        tasks = [self.check_term(t) for t in terms]
        return await asyncio.gather(*tasks)

    async def _query_openalex(self, term: str) -> int:
        """查询 OpenAlex API"""
        try:
            import httpx
            url = "https://api.openalex.org/works"
            params = {"filter": f"title.search:{term}", "per_page": 1}
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                return data.get("meta", {}).get("count", 0)
        except ImportError:
            logger.warning("httpx not installed, OpenAlex query skipped")
            return 0
        except Exception as e:
            logger.warning(f"OpenAlex query failed for '{term}': {e}")
            return 0

    async def _query_crossref(self, term: str) -> int:
        """查询 Crossref API"""
        try:
            import httpx
            url = "https://api.crossref.org/works"
            params = {"query.bibliographic": term, "rows": 0}
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                return data.get("message", {}).get("total-results", 0)
        except ImportError:
            logger.warning("httpx not installed, Crossref query skipped")
            return 0
        except Exception as e:
            logger.warning(f"Crossref query failed for '{term}': {e}")
            return 0
