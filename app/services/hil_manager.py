"""
HIL Manager 服务

管理 HIL Tickets 的创建、存储、查询和回答

v6.0 NEW: 主动人机协作管理
"""
import json
import asyncio
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime
import logging

from app.models.hil_ticket import (
    HILTicket,
    HILTicketCreate,
    HILTicketAnswer,
    HILTicketSummary,
    TicketStatus,
    TicketPriority
)

logger = logging.getLogger(__name__)


class HILManager:
    """
    HIL Ticket 管理器

    负责 HIL Tickets 的生命周期管理
    """

    def __init__(self, base_path: str = "hil"):
        """
        初始化 HIL Manager

        Args:
            base_path: HIL 根目录路径
        """
        self.base_path = Path(base_path)
        self.tickets_path = self.base_path / "tickets"
        self.index_file = self.base_path / "ticket_index.json"
        self.index: Dict[str, Dict] = {}  # ticket_id -> metadata

        # 确保目录存在
        self.tickets_path.mkdir(parents=True, exist_ok=True)

        # 加载索引
        self._load_index()

    def _load_index(self):
        """从文件加载索引"""
        if self.index_file.exists():
            try:
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    self.index = json.load(f)
                logger.info(f"Loaded HIL ticket index: {len(self.index)} tickets")
            except Exception as e:
                logger.error(f"Failed to load HIL ticket index: {e}")
                self.index = {}
        else:
            self.index = {}

    def _save_index(self):
        """保存索引到文件"""
        try:
            with open(self.index_file, 'w', encoding='utf-8') as f:
                json.dump(self.index, f, indent=2, ensure_ascii=False)
            logger.debug("Saved HIL ticket index")
        except Exception as e:
            logger.error(f"Failed to save HIL ticket index: {e}")

    def _get_ticket_path(self, ticket_id: str) -> Path:
        """
        获取 ticket 文件路径

        Args:
            ticket_id: Ticket ID

        Returns:
            Path: 文件路径
        """
        return self.tickets_path / f"{ticket_id}.md"

    async def create_ticket(self, ticket_create: HILTicketCreate) -> HILTicket:
        """
        创建新的 HIL Ticket

        Args:
            ticket_create: Ticket 创建请求

        Returns:
            HILTicket: 创建的 ticket
        """
        try:
            # 创建 ticket
            ticket = HILTicket(
                project_id=ticket_create.project_id,
                step_id=ticket_create.step_id,
                question=ticket_create.question,
                context=ticket_create.context,
                options=ticket_create.options,
                allow_custom_input=ticket_create.allow_custom_input,
                priority=ticket_create.priority,
                timeout_hours=ticket_create.timeout_hours,
                default_option_id=ticket_create.default_option_id,
                ai_model=ticket_create.ai_model,
                reasoning=ticket_create.reasoning
            )

            # 保存 JSON 和 Markdown
            await self.save_ticket(ticket)

            logger.info(f"Created HIL ticket: {ticket.ticket_id} for project {ticket.project_id}")
            return ticket

        except Exception as e:
            logger.error(f"Failed to create HIL ticket: {e}")
            raise

    async def get_ticket(self, ticket_id: str) -> Optional[HILTicket]:
        """
        获取 HIL Ticket

        Args:
            ticket_id: Ticket ID

        Returns:
            Optional[HILTicket]: Ticket 对象，如果不存在则返回 None
        """
        try:
            # 从索引获取文件路径
            if ticket_id not in self.index:
                logger.warning(f"Ticket not found in index: {ticket_id}")
                return None

            ticket_path = Path(self.index[ticket_id]["file_path"])
            if not ticket_path.exists():
                logger.warning(f"Ticket file not found: {ticket_path}")
                return None

            # 读取文件（注意：这里简化处理，实际应该解析 markdown）
            # 由于 ticket 主要通过 API 操作，我们直接从索引重建
            # 完整实现应该解析 markdown 文件

            # 这里我们使用一个简化的方法：存储 JSON 而不是 markdown
            # 让我们修改存储格式
            json_path = self.tickets_path / f"{ticket_id}.json"
            if json_path.exists():
                with open(json_path, 'r', encoding='utf-8') as f:
                    ticket_data = json.load(f)
                    # 转换时间字符串为 datetime
                    if 'created_at' in ticket_data:
                        ticket_data['created_at'] = datetime.fromisoformat(ticket_data['created_at'])
                    if 'answered_at' in ticket_data and ticket_data['answered_at']:
                        ticket_data['answered_at'] = datetime.fromisoformat(ticket_data['answered_at'])
                    if 'timeout_at' in ticket_data and ticket_data['timeout_at']:
                        ticket_data['timeout_at'] = datetime.fromisoformat(ticket_data['timeout_at'])
                    return HILTicket(**ticket_data)

            logger.warning(f"Ticket JSON not found: {json_path}")
            return None

        except Exception as e:
            logger.error(f"Failed to load ticket {ticket_id}: {e}")
            return None

    async def save_ticket(self, ticket: HILTicket):
        """
        保存 ticket（更新）

        Args:
            ticket: Ticket 对象
        """
        try:
            # 保存 JSON
            json_path = self.tickets_path / f"{ticket.ticket_id}.json"
            ticket_dict = ticket.dict()
            # 转换 datetime 为字符串
            ticket_dict['created_at'] = ticket.created_at.isoformat()
            if ticket.answered_at:
                ticket_dict['answered_at'] = ticket.answered_at.isoformat()
            if ticket.timeout_at:
                ticket_dict['timeout_at'] = ticket.timeout_at.isoformat()

            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(ticket_dict, f, indent=2, ensure_ascii=False)

            # 保存 Markdown（用于人类阅读）
            markdown_path = self._get_ticket_path(ticket.ticket_id)
            with open(markdown_path, 'w', encoding='utf-8') as f:
                f.write(ticket.to_markdown())

            # 更新索引
            self.index[ticket.ticket_id] = {
                "project_id": ticket.project_id,
                "step_id": ticket.step_id,
                "status": ticket.status.value,
                "priority": ticket.priority.value,
                "created_at": ticket.created_at.isoformat(),
                "timeout_at": ticket.timeout_at.isoformat() if ticket.timeout_at else None,
                "file_path": str(markdown_path)
            }
            self._save_index()

            logger.info(f"Saved ticket: {ticket.ticket_id}")

        except Exception as e:
            logger.error(f"Failed to save ticket {ticket.ticket_id}: {e}")
            raise

    async def answer_ticket(self, ticket_id: str, answer: HILTicketAnswer) -> HILTicket:
        """
        回答 HIL Ticket

        Args:
            ticket_id: Ticket ID
            answer: 回答内容

        Returns:
            HILTicket: 更新后的 ticket
        """
        ticket = await self.get_ticket(ticket_id)
        if not ticket:
            raise ValueError(f"Ticket not found: {ticket_id}")

        # 回答 ticket
        ticket.answer(
            option_id=answer.option_id,
            custom_input=answer.custom_input
        )

        # 保存
        await self.save_ticket(ticket)

        logger.info(f"Answered ticket: {ticket_id}")
        return ticket

    async def list_tickets(
        self,
        project_id: Optional[str] = None,
        status: Optional[TicketStatus] = None,
        priority: Optional[TicketPriority] = None,
        include_expired: bool = False
    ) -> List[HILTicketSummary]:
        """
        列出 HIL Tickets

        Args:
            project_id: 项目 ID 过滤
            status: 状态过滤
            priority: 优先级过滤
            include_expired: 是否包含已过期的 tickets

        Returns:
            List[HILTicketSummary]: Ticket 摘要列表
        """
        summaries = []

        for ticket_id, metadata in self.index.items():
            # 过滤条件
            if project_id and metadata["project_id"] != project_id:
                continue
            if status and metadata["status"] != status.value:
                continue
            if priority and metadata["priority"] != priority.value:
                continue

            # 检查是否过期
            is_expired = False
            if metadata.get("timeout_at"):
                timeout_at = datetime.fromisoformat(metadata["timeout_at"])
                is_expired = datetime.now() > timeout_at

            if not include_expired and is_expired and metadata["status"] == TicketStatus.PENDING.value:
                continue

            # 创建摘要
            summary = HILTicketSummary(
                ticket_id=ticket_id,
                project_id=metadata["project_id"],
                step_id=metadata["step_id"],
                question="",  # 需要加载完整 ticket 才能获取
                priority=TicketPriority(metadata["priority"]),
                status=TicketStatus(metadata["status"]),
                created_at=datetime.fromisoformat(metadata["created_at"]),
                is_expired=is_expired,
                is_blocking=TicketPriority(metadata["priority"]) in [TicketPriority.HIGH, TicketPriority.CRITICAL]
            )
            summaries.append(summary)

        # 按创建时间排序（最新的在前）
        summaries.sort(key=lambda x: x.created_at, reverse=True)

        logger.debug(f"Listed {len(summaries)} tickets")
        return summaries

    async def get_pending_tickets(self, project_id: str) -> List[HILTicket]:
        """
        获取项目的所有待处理 tickets

        Args:
            project_id: 项目 ID

        Returns:
            List[HILTicket]: 待处理的 tickets
        """
        summaries = await self.list_tickets(
            project_id=project_id,
            status=TicketStatus.PENDING,
            include_expired=False
        )

        tickets = []
        for summary in summaries:
            ticket = await self.get_ticket(summary.ticket_id)
            if ticket:
                tickets.append(ticket)

        return tickets

    async def get_blocking_tickets(self, project_id: str) -> List[HILTicket]:
        """
        获取项目的所有阻塞性 tickets（高优先级或关键）

        Args:
            project_id: 项目 ID

        Returns:
            List[HILTicket]: 阻塞性 tickets
        """
        all_pending = await self.get_pending_tickets(project_id)
        return [t for t in all_pending if t.is_blocking()]

    async def process_expired_tickets(self):
        """
        处理所有过期的 tickets（使用默认值）

        Returns:
            int: 处理的 ticket 数量
        """
        processed_count = 0

        for ticket_id, metadata in list(self.index.items()):
            if metadata["status"] != TicketStatus.PENDING.value:
                continue

            if not metadata.get("timeout_at"):
                continue

            timeout_at = datetime.fromisoformat(metadata["timeout_at"])
            if datetime.now() <= timeout_at:
                continue

            # 过期了，使用默认值
            try:
                ticket = await self.get_ticket(ticket_id)
                if ticket:
                    ticket.timeout()
                    await self.save_ticket(ticket)
                    processed_count += 1
                    logger.info(f"Processed expired ticket: {ticket_id}")
            except Exception as e:
                logger.error(f"Failed to process expired ticket {ticket_id}: {e}")

        return processed_count

    async def cancel_ticket(self, ticket_id: str) -> HILTicket:
        """
        取消 HIL Ticket

        Args:
            ticket_id: Ticket ID

        Returns:
            HILTicket: 更新后的 ticket
        """
        ticket = await self.get_ticket(ticket_id)
        if not ticket:
            raise ValueError(f"Ticket not found: {ticket_id}")

        ticket.cancel()
        await self.save_ticket(ticket)

        logger.info(f"Cancelled ticket: {ticket_id}")
        return ticket

    def rebuild_index(self):
        """重建索引（扫描所有 ticket 文件）"""
        logger.info("Rebuilding HIL ticket index...")
        self.index = {}

        # 扫描所有 .json 文件
        for json_path in self.tickets_path.glob("*.json"):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    ticket_data = json.load(f)

                ticket_id = ticket_data["ticket_id"]
                markdown_path = self.tickets_path / f"{ticket_id}.md"

                self.index[ticket_id] = {
                    "project_id": ticket_data["project_id"],
                    "step_id": ticket_data["step_id"],
                    "status": ticket_data["status"],
                    "priority": ticket_data["priority"],
                    "created_at": ticket_data["created_at"],
                    "timeout_at": ticket_data.get("timeout_at"),
                    "file_path": str(markdown_path)
                }

            except Exception as e:
                logger.warning(f"Failed to parse ticket {json_path}: {e}")

        self._save_index()
        logger.info(f"Rebuilt index: {len(self.index)} tickets")


# 全局 HIL Manager 实例
_hil_manager_instance = None


def get_hil_manager() -> HILManager:
    """获取全局 HIL Manager 实例"""
    global _hil_manager_instance
    if _hil_manager_instance is None:
        _hil_manager_instance = HILManager()
    return _hil_manager_instance
