"""
基础步骤类
所有 SOP 步骤的抽象基类
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
import logging
from datetime import datetime

from app.models.document import Document, DocumentMetadata, DocumentType, DocumentStatus
from app.models.project import Project
from app.models.artifact import Artifact, ArtifactMetadata, ArtifactStatus, CreatedBy
from app.models.hil import HILTicketCreate, HILTicket, HILTicketAnswer, QuestionType, TicketPriority
from app.services.ai_client import ChatGPTClient, GeminiClient
from app.services.artifact_store import get_artifact_store
from app.services.hil_service import HILService
from app.utils.file_manager import FileManager
from app.services.vector_store import VectorStore
from app.utils.git_manager import GitManager
from app.utils.conversation_logger import conversation_logger
from pathlib import Path
import asyncio

logger = logging.getLogger(__name__)


class StepExecutionError(Exception):
    """步骤执行错误"""
    pass


class BaseStep(ABC):
    """SOP 步骤基类"""

    def __init__(
        self,
        project: Project,
        chatgpt_client: Optional[ChatGPTClient] = None,
        gemini_client: Optional[GeminiClient] = None,
        file_manager: Optional[FileManager] = None,
        vector_store: Optional[VectorStore] = None,
        git_manager: Optional[GitManager] = None
    ):
        """
        初始化步骤

        Args:
            project: 项目对象
            chatgpt_client: ChatGPT 客户端
            gemini_client: Gemini 客户端
            file_manager: 文件管理器
            vector_store: 向量数据库
            git_manager: Git 管理器
        """
        self.project = project
        self.chatgpt_client = chatgpt_client or ChatGPTClient()
        self.gemini_client = gemini_client or GeminiClient()
        self.file_manager = file_manager or FileManager()
        self.vector_store = vector_store or VectorStore()
        self.git_manager = git_manager or GitManager()
        self.artifact_store = get_artifact_store()
        self.hil_service = HILService()

    @property
    @abstractmethod
    def step_id(self) -> str:
        """步骤 ID"""
        pass

    @property
    @abstractmethod
    def step_name(self) -> str:
        """步骤名称"""
        pass

    @property
    @abstractmethod
    def output_doc_type(self) -> DocumentType:
        """输出文档类型"""
        pass

    @property
    @abstractmethod
    def ai_model(self) -> str:
        """使用的 AI 模型（ChatGPT 或 Gemini）"""
        pass

    @abstractmethod
    async def execute(self) -> Document:
        """
        执行步骤

        Returns:
            Document: 生成的文档

        Raises:
            StepExecutionError: 执行失败时抛出
        """
        pass

    async def get_context_documents(self, doc_types: List[DocumentType]) -> List[Document]:
        """
        获取上下文文档

        Args:
            doc_types: 需要的文档类型列表

        Returns:
            List[Document]: 文档列表
        """
        documents = []
        for doc_type in doc_types:
            doc = await self.file_manager.load_document(self.project.project_id, doc_type)
            if doc:
                documents.append(doc)
        return documents

    async def save_and_commit(self, document: Document, commit_message: str) -> str:
        """
        保存文档并提交到 Git

        Args:
            document: 文档对象
            commit_message: 提交信息

        Returns:
            str: 文件路径
        """
        try:
            # 保存文档
            file_path = await self.file_manager.save_document(
                self.project.project_id,
                document
            )
            logger.info(f"Saved document to {file_path}")

            # 添加到向量数据库
            await self.vector_store.add_document(
                project_id=self.project.project_id,
                doc_id=getattr(document.metadata.doc_type, 'value', document.metadata.doc_type),
                content=document.content,
                metadata={
                    "doc_type": getattr(document.metadata.doc_type, 'value', document.metadata.doc_type),
                    "status": getattr(document.metadata.status, 'value', document.metadata.status),
                    "created_at": document.metadata.created_at.isoformat()
                }
            )
            logger.info(f"Added document to vector store")

            # Git commit
            await self.git_manager.commit(
                project_id=self.project.project_id,
                message=commit_message
            )
            logger.info(f"Committed changes: {commit_message}")

            return file_path

        except Exception as e:
            logger.error(f"Failed to save and commit document: {e}")
            raise StepExecutionError(f"Failed to save and commit: {e}")

    async def retrieve_context(self, query: str, top_k: int = 3) -> List[str]:
        """
        从向量数据库检索相关上下文

        Args:
            query: 查询文本
            top_k: 返回前 k 个结果

        Returns:
            List[str]: 相关文档内容列表
        """
        try:
            results = await self.vector_store.query(
                project_id=self.project.project_id,
                query_text=query,
                top_k=top_k
            )
            return [result["content"] for result in results]
        except Exception as e:
            logger.warning(f"Failed to retrieve context: {e}")
            return []

    def create_document(
        self,
        doc_type: DocumentType,
        content: str,
        status: DocumentStatus = DocumentStatus.COMPLETED,
        inputs: List[str] = None,
        outputs: List[str] = None
    ) -> Document:
        """
        创建文档对象

        Args:
            doc_type: 文档类型
            content: 文档内容
            status: 文档状态
            inputs: 输入文档列表
            outputs: 输出文档列表

        Returns:
            Document: 文档对象
        """
        metadata = DocumentMetadata(
            doc_type=doc_type,
            status=status,
            project_id=self.project.project_id,
            inputs=inputs or [],
            outputs=outputs or []
        )
        return Document(metadata=metadata, content=content)

    def parse_multiple_documents(self, content: str, doc_specs: List[tuple]) -> List[tuple]:
        """
        解析AI返回的多个文档

        Args:
            content: AI返回的完整内容
            doc_specs: 文档规格列表 [(doc_id, doc_type), ...]

        Returns:
            list: [(doc_type, content), ...]

        Raises:
            StepExecutionError: 无法解析任何文档时抛出
        """
        import re

        # Strip outer markdown code blocks if present (e.g., ```yaml ... ``` or ```markdown ... ```)
        # This handles cases where AI wraps the entire output in a code block
        # Use a more flexible pattern that handles various code block formats
        content_stripped = content.strip()

        # Try multiple patterns for code block detection
        patterns = [
            r'^```(?:yaml|markdown)?\s*\n(.*)\n```$',  # Standard markdown code block
            r'^```(?:yaml|markdown)?\s*\n(.*)```$',     # Code block without final newline
            r'^```(?:yaml|markdown)?\s*(.*)\n```$',     # Code block without initial newline
            r'^```(?:yaml|markdown)?\s*(.*)```$'        # Minimal code block
        ]

        stripped = False
        for pattern in patterns:
            code_block_match = re.match(pattern, content_stripped, re.DOTALL)
            if code_block_match:
                content = code_block_match.group(1).strip()
                logger.info(f"Stripped outer markdown code block from AI response (pattern matched)")
                stripped = True
                break

        if not stripped:
            content = content_stripped

        documents = []
        for doc_id, doc_type in doc_specs:
            # 匹配文档内容
            pattern = f"---{doc_id}:.*?---(.*?)---END_{doc_id}---"
            match = re.search(pattern, content, re.DOTALL)

            if match:
                doc_content = match.group(1).strip()
                documents.append((doc_type, doc_content))
                logger.info(f"Parsed document: {doc_type.value} ({len(doc_content)} chars)")
            else:
                logger.warning(f"Could not find document {doc_id} in AI response")
                # 如果找不到分隔符，尝试使用整个内容
                if len(doc_specs) == 1:
                    documents.append((doc_type, content))
                    logger.info(f"Using full content for {doc_type.value}")

        if not documents:
            raise StepExecutionError("Failed to parse any documents from AI response")

        return documents

    def log_ai_conversation(
        self,
        model: str,
        system_prompt: Optional[str],
        user_prompt: str,
        context: Optional[List[str]] = None,
        response: str = "",
        thinking: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        记录 AI 对话到项目日志

        Args:
            model: AI 模型名称
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            context: 上下文文档列表
            response: AI 响应内容
            thinking: 思考过程（如果有）
            metadata: 额外的元数据（如 tokens, latency 等）
        """
        try:
            conversation_logger.log_conversation(
                project_id=self.project.project_id,
                step_id=self.step_id,
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                context=context,
                response=response,
                thinking=thinking,
                metadata=metadata
            )
        except Exception as e:
            logger.warning(f"Failed to log AI conversation: {e}")

    def get_artifact_path(self) -> Path:
        """
        获取 artifact 文件路径

        Returns:
            Path: artifact 文件路径
        """
        return Path(f"artifacts/{self.project.project_id}/{self.step_id}.md")

    def ai_model_to_created_by(self) -> CreatedBy:
        """
        将 AI 模型名称转换为 CreatedBy 枚举

        Returns:
            CreatedBy: 创建者枚举值
        """
        if self.ai_model.lower() == "chatgpt":
            return CreatedBy.CHATGPT
        elif self.ai_model.lower() == "gemini":
            return CreatedBy.GEMINI
        else:
            return CreatedBy.SYSTEM

    async def save_to_artifact_store(
        self,
        content: str,
        doc_type: DocumentType,
        status: ArtifactStatus = ArtifactStatus.DRAFT
    ) -> Artifact:
        """
        保存到 Artifact Store

        Args:
            content: 文档内容
            doc_type: 文档类型
            status: Artifact 状态

        Returns:
            Artifact: 保存的 artifact 对象
        """
        try:
            artifact = Artifact(
                id=f"{self.project.project_id}_{self.step_id}",
                project_id=self.project.project_id,
                metadata=ArtifactMetadata(
                    doc_type=doc_type.value,
                    version="1.0",
                    status=status,
                    created_by=self.ai_model_to_created_by(),
                    project_id=self.project.project_id
                ),
                content=content,
                file_path=str(self.get_artifact_path())
            )
            await self.artifact_store.save_artifact(artifact)
            logger.info(f"Saved artifact to store: {artifact.id}")
            return artifact
        except Exception as e:
            logger.error(f"Failed to save artifact to store: {e}")
            raise StepExecutionError(f"Failed to save artifact: {e}")

    async def load_from_artifact_store(self, step_id: Optional[str] = None) -> Optional[Artifact]:
        """
        从 Artifact Store 加载 artifact

        Args:
            step_id: 步骤 ID，如果为 None 则使用当前步骤 ID

        Returns:
            Optional[Artifact]: artifact 对象，如果不存在则返回 None
        """
        try:
            artifact_id = f"{self.project.project_id}_{step_id or self.step_id}"
            artifact = await self.artifact_store.load_artifact(artifact_id)
            if artifact:
                logger.info(f"Loaded artifact from store: {artifact_id}")
            return artifact
        except Exception as e:
            logger.warning(f"Failed to load artifact from store: {e}")
            return None

    async def get_context_artifacts(self, step_ids: List[str]) -> List[Artifact]:
        """
        获取上下文 artifacts

        Args:
            step_ids: 步骤 ID 列表

        Returns:
            List[Artifact]: artifact 列表
        """
        artifacts = []
        for step_id in step_ids:
            artifact = await self.load_from_artifact_store(step_id)
            if artifact:
                artifacts.append(artifact)
        return artifacts

    async def load_context_with_fallback(self, step_id: str, doc_type: DocumentType) -> Optional[str]:
        """
        加载上下文内容，优先从 Artifact Store，回退到文件系统

        Args:
            step_id: 步骤 ID
            doc_type: 文档类型

        Returns:
            Optional[str]: 文档内容，如果不存在则返回 None
        """
        # 1. 优先从 Artifact Store 读取
        artifact = await self.load_from_artifact_store(step_id)
        if artifact:
            logger.info(f"Loaded context from Artifact Store: {step_id}")
            return artifact.content

        # 2. 回退到文件系统
        try:
            document = await self.file_manager.load_document(self.project.project_id, doc_type)
            if document:
                logger.info(f"Loaded context from file system: {doc_type.value}")
                return document.content
        except Exception as e:
            logger.warning(f"Failed to load context from file system: {e}")

        return None

    # ========== HIL (Human-in-the-Loop) Methods ==========

    async def request_human_input(
        self,
        question: str,
        question_type: QuestionType = QuestionType.CLARIFICATION,
        context: Optional[Dict[str, Any]] = None,
        options: Optional[List[str]] = None,
        default_answer: Optional[str] = None,
        priority: TicketPriority = TicketPriority.MEDIUM,
        blocking: bool = False,
        timeout_hours: float = 24.0
    ) -> HILTicket:
        """
        请求人工输入（创建 HIL Ticket）

        Args:
            question: 问题描述
            question_type: 问题类型
            context: 上下文信息
            options: 预定义选项
            default_answer: 超时默认答案
            priority: 优先级
            blocking: 是否阻塞步骤执行
            timeout_hours: 超时时间（小时）

        Returns:
            HILTicket: 创建的 HIL ticket

        Example:
            ticket = await self.request_human_input(
                question="发现多个研究方向，需要人工确认优先级",
                question_type=QuestionType.DECISION,
                context={"directions": ["方向A", "方向B", "方向C"]},
                options=["方向A", "方向B", "方向C"],
                priority=TicketPriority.HIGH,
                blocking=True
            )
        """
        ticket_create = HILTicketCreate(
            project_id=self.project.project_id,
            step_id=self.step_id,
            question_type=question_type,
            question=question,
            context=context,
            options=options,
            default_answer=default_answer,
            priority=priority,
            blocking=blocking,
            timeout_hours=timeout_hours
        )

        ticket = await self.hil_service.create_ticket(ticket_create)
        logger.info(f"Created HIL ticket {ticket.ticket_id} for step {self.step_id}")

        return ticket

    async def wait_for_human_input(
        self,
        ticket_id: str,
        poll_interval: float = 5.0,
        max_wait_time: Optional[float] = None
    ) -> Optional[HILTicket]:
        """
        等待人工输入（轮询 HIL Ticket 状态）

        Args:
            ticket_id: Ticket ID
            poll_interval: 轮询间隔（秒）
            max_wait_time: 最大等待时间（秒），None 表示无限等待

        Returns:
            Optional[HILTicket]: 已回答的 ticket，如果超时则返回 None

        Example:
            ticket = await self.request_human_input(...)
            answered_ticket = await self.wait_for_human_input(ticket.ticket_id)
            if answered_ticket:
                answer = answered_ticket.answer
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            # 获取 ticket 状态
            ticket = await self.hil_service.get_ticket(ticket_id)

            if not ticket:
                logger.error(f"Ticket {ticket_id} not found")
                return None

            # 检查是否已回答
            if ticket.status.value == "answered":
                logger.info(f"Ticket {ticket_id} answered: {ticket.answer}")
                return ticket

            # 检查是否已取消或过期
            if ticket.status.value in ["cancelled", "expired"]:
                logger.warning(f"Ticket {ticket_id} status: {ticket.status}")
                return ticket

            # 检查是否超时
            if max_wait_time:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > max_wait_time:
                    logger.warning(f"Timeout waiting for ticket {ticket_id}")
                    return None

            # 等待后继续轮询
            await asyncio.sleep(poll_interval)

    async def check_blocking_tickets(self) -> List[HILTicket]:
        """
        检查当前项目是否有阻塞性 HIL Tickets

        Returns:
            List[HILTicket]: 阻塞性 ticket 列表

        Example:
            blocking_tickets = await self.check_blocking_tickets()
            if blocking_tickets:
                logger.warning(f"Found {len(blocking_tickets)} blocking tickets")
                # 等待所有阻塞性 tickets 被回答
                for ticket in blocking_tickets:
                    await self.wait_for_human_input(ticket.ticket_id)
        """
        blocking_tickets = await self.hil_service.get_blocking_tickets(self.project.project_id)

        if blocking_tickets:
            logger.warning(
                f"Found {len(blocking_tickets)} blocking tickets for project {self.project.project_id}"
            )

        return blocking_tickets

    async def request_and_wait(
        self,
        question: str,
        question_type: QuestionType = QuestionType.CLARIFICATION,
        context: Optional[Dict[str, Any]] = None,
        options: Optional[List[str]] = None,
        default_answer: Optional[str] = None,
        priority: TicketPriority = TicketPriority.MEDIUM,
        blocking: bool = True,
        timeout_hours: float = 24.0,
        poll_interval: float = 5.0
    ) -> Optional[str]:
        """
        请求人工输入并等待回答（便捷方法）

        Args:
            question: 问题描述
            question_type: 问题类型
            context: 上下文信息
            options: 预定义选项
            default_answer: 超时默认答案
            priority: 优先级
            blocking: 是否阻塞
            timeout_hours: 超时时间（小时）
            poll_interval: 轮询间隔（秒）

        Returns:
            Optional[str]: 人工回答，如果超时或取消则返回 None

        Example:
            answer = await self.request_and_wait(
                question="选择研究方向",
                options=["方向A", "方向B", "方向C"],
                priority=TicketPriority.HIGH
            )
            if answer:
                logger.info(f"User selected: {answer}")
        """
        # 创建 ticket
        ticket = await self.request_human_input(
            question=question,
            question_type=question_type,
            context=context,
            options=options,
            default_answer=default_answer,
            priority=priority,
            blocking=blocking,
            timeout_hours=timeout_hours
        )

        # 等待回答
        max_wait_time = timeout_hours * 3600 if timeout_hours else None
        answered_ticket = await self.wait_for_human_input(
            ticket.ticket_id,
            poll_interval=poll_interval,
            max_wait_time=max_wait_time
        )

        if answered_ticket and answered_ticket.answer:
            return answered_ticket.answer

        return None

