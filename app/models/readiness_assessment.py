"""
Readiness Assessment 数据模型
v1.2 §5.9: RA 输出的 JSON schema

RA 在每个 WP 完成后由 Gemini 执行，判定是否可以推进到下一个 WP。
"""
from pydantic import BaseModel, Field
from typing import List


class ReadinessAssessmentResult(BaseModel):
    """Readiness Assessment 结果

    verdict 取值:
      - ADVANCE: 通过，推进到下一个 WP
      - POLISH: 需要修补，附带 polish_suggestions
      - BLOCK: 阻塞，需要人工介入
    """
    verdict: str = Field(..., description="RA 判定 (ADVANCE/POLISH/BLOCK)")
    reasoning: str = Field(..., description="判定理由 (<= 200 words)")
    north_star_alignment: str = Field(..., description="与北极星问题的对齐程度")
    missing_pieces: List[str] = Field(default_factory=list, description="缺失的关键部分")
    polish_suggestions: List[str] = Field(default_factory=list, description="POLISH 时的修补建议")
    next_wp_readiness: str = Field(default="", description="下一个 WP 的就绪评估")
