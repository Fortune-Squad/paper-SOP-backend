"""
HIL (Human-in-the-Loop) Ticket 数据模型

v6.0 NEW: 主动人机协作机制
- AI 可以主动创建 ticket 请求人类输入
- 结构化的问题和选项
- 支持超时和默认值
- 存储在 hil/tickets/ 目录
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from enum import Enum
import uuid


class TicketStatus(str, Enum):
    """Ticket 状态"""
    PENDING = "pending"  # 等待人类回答
    ANSWERED = "answered"  # 已回答
    TIMEOUT = "timeout"  # 超时（使用默认值）
    CANCELLED = "cancelled"  # 已取消


class TicketPriority(str, Enum):
    """Ticket 优先级"""
    LOW = "low"  # 低优先级（可选）
    MEDIUM = "medium"  # 中优先级（建议回答）
    HIGH = "high"  # 高优先级（必须回答）
    CRITICAL = "critical"  # 关键（阻塞流程）


class TicketOption(BaseModel):
    """Ticket 选项"""
    option_id: str = Field(..., description="选项 ID")
    label: str = Field(..., description="选项标签")
    description: Optional[str] = Field(None, description="选项描述")
    is_default: bool = Field(default=False, description="是否为默认选项")


class HILTicket(BaseModel):
    """
    HIL Ticket 模型

    表示一个人机协作请求
    """
    ticket_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Ticket ID")
    project_id: str = Field(..., description="项目 ID")
    step_id: str = Field(..., description="触发 ticket 的步骤 ID")

    # Ticket 内容
    question: str = Field(..., description="问题描述")
    context: Optional[str] = Field(None, description="问题上下文（帮助人类理解）")
    options: List[TicketOption] = Field(..., description="可选项列表")
    allow_custom_input: bool = Field(default=True, description="是否允许自定义输入")

    # Ticket 元数据
    priority: TicketPriority = Field(default=TicketPriority.MEDIUM, description="优先级")
    status: TicketStatus = Field(default=TicketStatus.PENDING, description="状态")

    # 超时设置
    timeout_hours: Optional[int] = Field(default=24, description="超时时间（小时）")
    default_option_id: Optional[str] = Field(None, description="超时时使用的默认选项 ID")

    # 回答
    selected_option_id: Optional[str] = Field(None, description="选中的选项 ID")
    custom_input: Optional[str] = Field(None, description="自定义输入")

    # 时间戳
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    answered_at: Optional[datetime] = Field(None, description="回答时间")
    timeout_at: Optional[datetime] = Field(None, description="超时时间")

    # AI 元数据
    ai_model: Optional[str] = Field(None, description="创建 ticket 的 AI 模型")
    reasoning: Optional[str] = Field(None, description="AI 创建 ticket 的理由")

    def __init__(self, **data):
        super().__init__(**data)
        # 计算超时时间
        if self.timeout_hours and not self.timeout_at:
            self.timeout_at = self.created_at + timedelta(hours=self.timeout_hours)

    def is_expired(self) -> bool:
        """检查是否已超时"""
        if not self.timeout_at:
            return False
        return datetime.now() > self.timeout_at

    def is_blocking(self) -> bool:
        """检查是否阻塞流程（高优先级或关键）"""
        return self.priority in [TicketPriority.HIGH, TicketPriority.CRITICAL]

    def get_selected_option(self) -> Optional[TicketOption]:
        """获取选中的选项"""
        if not self.selected_option_id:
            return None
        for option in self.options:
            if option.option_id == self.selected_option_id:
                return option
        return None

    def get_default_option(self) -> Optional[TicketOption]:
        """获取默认选项"""
        if self.default_option_id:
            for option in self.options:
                if option.option_id == self.default_option_id:
                    return option
        # 如果没有指定默认选项，返回第一个标记为 default 的选项
        for option in self.options:
            if option.is_default:
                return option
        return None

    def answer(self, option_id: Optional[str] = None, custom_input: Optional[str] = None):
        """
        回答 ticket

        Args:
            option_id: 选中的选项 ID
            custom_input: 自定义输入
        """
        if self.status != TicketStatus.PENDING:
            raise ValueError(f"Ticket {self.ticket_id} is not pending (status: {self.status})")

        if not option_id and not custom_input:
            raise ValueError("Must provide either option_id or custom_input")

        if option_id:
            # 验证选项 ID 是否有效
            if not any(opt.option_id == option_id for opt in self.options):
                raise ValueError(f"Invalid option_id: {option_id}")
            self.selected_option_id = option_id

        if custom_input:
            if not self.allow_custom_input:
                raise ValueError("Custom input is not allowed for this ticket")
            self.custom_input = custom_input

        self.status = TicketStatus.ANSWERED
        self.answered_at = datetime.now()

    def timeout(self):
        """
        超时处理（使用默认 """
        if self.status != TicketStatus.PENDING:
            raise ValueError(f"Ticket {self.ticket_id} is not pending (status: {self.status})")

        default_option = self.get_default_option()
        if default_option:
            self.selected_option_id = default_option.option_id
            self.status = TicketStatus.TIMEOUT
            self.answered_at = datetime.now()
        else:
            raise ValueError(f"No default option available for ticket {self.ticket_id}")

    def cancel(self):
        """取消 ticket"""
        if self.status != TicketStatus.PENDING:
            raise ValueError(f"Ticket {self.ticket_id} is not pending (status: {self.status})")
        self.status = TicketStatus.CANCELLED

    def to_markdown(self) -> str:
        """
        序列化为 Markdown 格式

        Returns:
            str: Markdown 内容
        """
        lines = [
            f"# HIL Ticket: {self.ticket_id}",
            "",
            f"**Project**: {self.project_id}",
            f"**Step**: {self.step_id}",
            f"**Priority**: {self.priority.value}",
            f"**Status**: {self.status.value}",
            f"**Created**: {self.created_at.isoformat()}",
            "",
            "## Question",
            "",
            self.question,
            "",
        ]

        if self.context:
            lines.extend([
                "## Context",
                "",
                self.context,
                "",
            ])

        lines.extend([
            "## Options",
            "",
        ])

        for i, option in enumerate(self.options, 1):
            default_marker = " (DEFAULT)" if option.is_default else ""
            lines.append(f"{i}. **{option.label}**{default_marker}")
            if option.description:
                lines.append(f"   - {option.description}")
            lines.append("")

        if self.allow_custom_input:
            lines.extend([
                "## Custom Input",
                "",
                "Custom input is allowed for this ticket.",
                "",
            ])

        if self.status == TicketStatus.ANSWERED:
            lines.extend([
                "## Answer",
                "",
                f"**Answered at**: {self.answered_at.isoformat()}",
                "",
            ])
            if self.selected_option_id:
                selected = self.get_selected_option()
                if selected:
                    lines.append(f"**Selected option**: {selected.label}")
            if self.custom_input:
                lines.extend([
                    "",
                    "**Custom input**:",
                    "",
                    self.custom_input,
                ])

        if self.reasoning:
            lines.extend([
                "",
                "## AI Reasoning",
                "",
                self.reasoning,
            ])

        return "\n".join(lines)


class HILTicketCreate(BaseModel):
    """创建 HIL Ticket 的请求模型"""
    project_id: str
    step_id: str
    question: str
    context: Optional[str] = None
    options: List[TicketOption]
    allow_custom_input: bool = True
    priority: TicketPriority = TicketPriority.MEDIUM
    timeout_hours: Optional[int] = 24
    default_option_id: Optional[str] = None
    ai_model: Optional[str] = None
    reasoning: Optional[str] = None


class HILTicketAnswer(BaseModel):
    """回答 HIL Ticket 的请求模型"""
    option_id: Optional[str] = None
    custom_input: Optional[str] = None


class HILTicketSummary(BaseModel):
    """HIL Ticket 摘要（用于列表显示）"""
    ticket_id: str
    project_id: str
    step_id: str
    question: str
    priority: TicketPriority
    status: TicketStatus
    created_at: datetime
    is_expired: bool
    is_blocking: bool
