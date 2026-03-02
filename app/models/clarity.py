"""
Input Clarity Scoring Models

This module defines data models for analyzing input clarity and making
Bootloader execution decisions.

v6.0 Phase 3: User Experience Optimization
"""

from pydantic import BaseModel, Field
from typing import List, Optional


class InputClarityScore(BaseModel):
    """
    Input clarity analysis result.

    Scores range from 0-100 for each component:
    - topic_clarity: How specific and clear the research topic is
    - context_clarity: How complete the project context/background is
    - constraint_clarity: How well-defined the constraints are
    - overall_score: Weighted average of all components

    Recommendation values:
    - "skip_bootloader": Input is clear (score >= 80), can skip Bootloader
    - "run_bootloader": Input is fuzzy (score < 50), should run Bootloader
    - "review_required": Input is medium (50-80), user decides
    """
    topic_clarity: float = Field(..., ge=0, le=100, description="Topic clarity score (0-100)")
    context_clarity: float = Field(..., ge=0, le=100, description="Context clarity score (0-100)")
    constraint_clarity: float = Field(..., ge=0, le=100, description="Constraint clarity score (0-100)")
    overall_score: float = Field(..., ge=0, le=100, description="Overall clarity score (0-100)")
    recommendation: str = Field(..., description="Recommendation: skip_bootloader | run_bootloader | review_required")
    reasons: List[str] = Field(default_factory=list, description="Specific reasons for the score")


class BootloaderDecision(BaseModel):
    """
    Bootloader execution decision.

    Tracks whether Bootloader should run and why:
    - should_run: Based on clarity score or user override
    - user_override: If user manually chose to skip/run
    - skip_reason: User-provided reason for skipping
    """
    should_run: bool = Field(..., description="Whether Bootloader should run")
    user_override: Optional[bool] = Field(None, description="User manually overrode recommendation")
    skip_reason: Optional[str] = Field(None, description="Reason for skipping Bootloader")
