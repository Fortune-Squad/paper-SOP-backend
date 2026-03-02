"""
HIL (Human-in-the-Loop) Ticket Models

Defines data models for HIL tickets that allow AI to request human input.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


class TicketStatus(str, Enum):
    """Ticket status"""
    PENDING = "pending"
    ANSWERED = "answered"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class TicketPriority(str, Enum):
    """Ticket priority"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class QuestionType(str, Enum):
    """Question type"""
    CLARIFICATION = "clarification"  # 澄清问题
    DECISION = "decision"  # 决策问题
    FEEDBACK = "feedback"  # 反馈问题
    VALIDATION = "validation"  # 验证问题
    PREFERENCE = "preference"  # 偏好问题


class HILTicketCreate(BaseModel):
    """HIL ticket creation request"""
    project_id: str = Field(..., description="Project ID")
    step_id: str = Field(..., description="Step ID where question arose")
    question_type: QuestionType = Field(..., description="Type of question")
    question: str = Field(..., description="The question to ask human")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Context information")
    options: Optional[List[str]] = Field(default=None, description="Predefined answer options")
    default_answer: Optional[str] = Field(default=None, description="Default answer if timeout")
    priority: TicketPriority = Field(default=TicketPriority.MEDIUM, description="Priority level")
    blocking: bool = Field(default=False, description="Whether this blocks step execution")
    timeout_hours: Optional[float] = Field(default=24.0, description="Hours until timeout")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")


class HILTicketAnswer(BaseModel):
    """HIL ticket answer"""
    answer: str = Field(..., description="The answer to the question")
    explanation: Optional[str] = Field(default=None, description="Explanation for the answer")
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Confidence score")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")


class HILTicket(BaseModel):
    """Complete HIL ticket"""
    ticket_id: str = Field(..., description="Unique ticket ID")
    project_id: str = Field(..., description="Project ID")
    step_id: str = Field(..., description="Step ID")
    question_type: QuestionType = Field(..., description="Question type")
    question: str = Field(..., description="The question")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Context")
    options: Optional[List[str]] = Field(default=None, description="Answer options")
    default_answer: Optional[str] = Field(default=None, description="Default answer")
    priority: TicketPriority = Field(..., description="Priority")
    blocking: bool = Field(..., description="Is blocking")
    status: TicketStatus = Field(..., description="Current status")

    # Answer fields
    answer: Optional[str] = Field(default=None, description="The answer")
    explanation: Optional[str] = Field(default=None, description="Answer explanation")
    confidence: Optional[float] = Field(default=None, description="Answer confidence")

    # Timestamps
    created_at: datetime = Field(..., description="Creation timestamp")
    expires_at: Optional[datetime] = Field(default=None, description="Expiration timestamp")
    answered_at: Optional[datetime] = Field(default=None, description="Answer timestamp")

    # Metadata
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")


class HILTicketSummary(BaseModel):
    """HIL ticket summary for list views"""
    ticket_id: str
    project_id: str
    step_id: str
    question_type: QuestionType
    question: str
    priority: TicketPriority
    blocking: bool
    status: TicketStatus
    created_at: datetime
    answered_at: Optional[datetime] = None
