"""
AI 客户端封装
统一封装 OpenAI API 和 Gemini API，支持重试机制和向量数据库集成
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import asyncio
import time
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import logging

from openai import AsyncOpenAI, OpenAIError
import google.generativeai as genai

from app.config import settings
from app.utils.api_logger import api_logger

# 配置日志
logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


class AIClientError(Exception):
    """AI 客户端异常"""
    pass


class AIClient(ABC):
    """AI 客户端基类"""

    def __init__(self, vector_store=None):
        """
        初始化 AI 客户端

        Args:
            vector_store: 向量数据库实例（用于检索项目上下文）
        """
        self.vector_store = vector_store

    @abstractmethod
    async def chat(self, prompt: str, context: Optional[List[str]] = None,
                   system_prompt: Optional[str] = None) -> str:
        """
        发送聊天请求

        Args:
            prompt: 用户提示词
            context: 上下文文档列表
            system_prompt: 系统提示词

        Returns:
            str: AI 响应内容
        """
        pass

    @abstractmethod
    async def chat_with_thinking(self, prompt: str, context: Optional[List[str]] = None,
                                 system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """
        发送聊天请求（带思考过程）

        Args:
            prompt: 用户提示词
            context: 上下文文档列表
            system_prompt: 系统提示词

        Returns:
            Dict: 包含响应内容和思考过程的字典
        """
        pass

    async def get_context_from_vector_store(self, project_id: str, query: str,
                                           top_k: int = 3) -> List[str]:
        """
        从向量数据库检索相关上下文

        Args:
            project_id: 项目 ID
            query: 查询文本
            top_k: 返回前 k 个最相关的文档

        Returns:
            List[str]: 相关文档内容列表
        """
        if not self.vector_store:
            return []

        try:
            results = await self.vector_store.query(
                project_id=project_id,
                query_text=query,
                top_k=top_k
            )
            return [doc["content"] for doc in results]
        except Exception as e:
            logger.error(f"Failed to retrieve context from vector store: {e}")
            return []


class ChatGPTClient(AIClient):
    """ChatGPT 客户端（PI/架构师角色）"""

    def __init__(self, vector_store=None):
        super().__init__(vector_store)
        # 支持自定义 Base URL（用于 API 代理服务如 TokHub）
        if settings.openai_api_base:
            self.client = AsyncOpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_api_base,
                timeout=settings.api_timeout
            )
            logger.info(f"Using custom OpenAI base URL: {settings.openai_api_base}")
        else:
            self.client = AsyncOpenAI(
                api_key=settings.openai_api_key,
                timeout=settings.api_timeout
            )
            logger.info("Using default OpenAI base URL")

        self.model = settings.openai_model
        self.max_tokens = settings.openai_max_tokens
        self.temperature = settings.openai_temperature
        logger.info(f"API timeout set to {settings.api_timeout} seconds")

    @retry(
        stop=stop_after_attempt(settings.max_retries),
        wait=wait_exponential(multiplier=1, min=settings.retry_delay, max=10),
        retry=retry_if_exception_type(OpenAIError),
        reraise=True
    )
    async def chat(self, prompt: str, context: Optional[List[str]] = None,
                   system_prompt: Optional[str] = None) -> str:
        """
        发送聊天请求到 ChatGPT

        Args:
            prompt: 用户提示词
            context: 上下文文档列表
            system_prompt: 系统提示词

        Returns:
            str: ChatGPT 响应内容
        """
        try:
            messages = []

            # 添加系统提示词
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            else:
                messages.append({
                    "role": "system",
                    "content": "You are a PI (Principal Investigator) and research architect. "
                               "Your role is formalization, assumptions, math/stat definitions, "
                               "risk control, gates, and engineering decomposition."
                })

            # 添加上下文
            if context:
                context_text = "\n\n---\n\n".join(context)
                messages.append({
                    "role": "user",
                    "content": f"Context from previous documents:\n\n{context_text}"
                })

            # 添加用户提示词
            messages.append({"role": "user", "content": prompt})

            logger.info(f"Sending request to ChatGPT (model: {self.model})")

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )

            content = response.choices[0].message.content
            logger.info(f"Received response from ChatGPT ({len(content)} characters)")

            return content

        except OpenAIError as e:
            logger.error(f"OpenAI API error: {e}")
            raise AIClientError(f"ChatGPT API error: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error in ChatGPT client: {e}")
            raise AIClientError(f"Unexpected error: {str(e)}")

    @retry(
        stop=stop_after_attempt(settings.max_retries),
        wait=wait_exponential(multiplier=1, min=settings.retry_delay, max=10),
        retry=retry_if_exception_type(OpenAIError),
        reraise=True
    )
    async def chat_with_thinking(self, prompt: str, context: Optional[List[str]] = None,
                                 system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """
        发送聊天请求到 ChatGPT（使用 o1 模型的思考模式）

        Args:
            prompt: 用户提示词
            context: 上下文文档列表
            system_prompt: 系统提示词

        Returns:
            Dict: 包含响应内容和思考过程
        """
        try:
            # 对于 o1 模型，使用不同的参数
            if "o1" in self.model:
                messages = []

                # o1 模型不支持 system role，将系统提示词合并到用户消息中
                user_content = ""
                if system_prompt:
                    user_content += f"{system_prompt}\n\n"

                # 添加上下文
                if context:
                    context_text = "\n\n---\n\n".join(context)
                    user_content += f"Context from previous documents:\n\n{context_text}\n\n"

                user_content += prompt
                messages.append({"role": "user", "content": user_content})

                logger.info(f"Sending request to ChatGPT with thinking (model: {self.model})")

                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages
                )

                content = response.choices[0].message.content
                # o1 模型的思考过程在响应中
                thinking = response.choices[0].message.content if hasattr(response.choices[0].message, 'reasoning') else None

                logger.info(f"Received response from ChatGPT with thinking ({len(content)} characters)")

                return {
                    "content": content,
                    "thinking": thinking,
                    "model": self.model
                }
            else:
                # 对于非 o1 模型，使用普通模式
                content = await self.chat(prompt, context, system_prompt)
                return {
                    "content": content,
                    "thinking": None,
                    "model": self.model
                }

        except OpenAIError as e:
            logger.error(f"OpenAI API error: {e}")
            raise AIClientError(f"ChatGPT API error: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error in ChatGPT client: {e}")
            raise AIClientError(f"Unexpected error: {str(e)}")


class GeminiClient(AIClient):
    """Gemini 客户端（情报官/编辑角色）"""

    def __init__(self, vector_store=None):
        super().__init__(vector_store)

        # 如果配置了自定义 Base URL（如 TokHub），使用 OpenAI 兼容接口
        if settings.gemini_api_base:
            self.use_openai_compatible = True
            self.client = AsyncOpenAI(
                api_key=settings.gemini_api_key,
                base_url=settings.gemini_api_base,
                timeout=settings.api_timeout
            )
            logger.info(f"Using custom Gemini base URL: {settings.gemini_api_base}")
        else:
            # 使用 Google 官方 SDK
            self.use_openai_compatible = False
            genai.configure(api_key=settings.gemini_api_key)
            self.model = genai.GenerativeModel(settings.gemini_model)
            logger.info("Using official Google Gemini SDK")

        logger.info(f"API timeout set to {settings.api_timeout} seconds")

        self.model_name = settings.gemini_model

    @retry(
        stop=stop_after_attempt(settings.max_retries),
        wait=wait_exponential(multiplier=1, min=settings.retry_delay, max=10),
        reraise=True
    )
    async def chat(self, prompt: str, context: Optional[List[str]] = None,
                   system_prompt: Optional[str] = None) -> str:
        """
        发送聊天请求到 Gemini

        Args:
            prompt: 用户提示词
            context: 上下文文档列表
            system_prompt: 系统提示词

        Returns:
            str: Gemini 响应内容
        """
        try:
            # 如果使用 OpenAI 兼容接口（TokHub）
            if self.use_openai_compatible:
                messages = []

                # 添加系统提示词
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                else:
                    messages.append({
                        "role": "system",
                        "content": "You are a Chief Intelligence Officer and senior academic editor. "
                                   "Your role is deep research, venue taste analysis, narrative options, "
                                   "and 'Reviewer #2' red-team critique."
                    })

                # 添加上下文
                if context:
                    context_text = "\n\n---\n\n".join(context)
                    messages.append({
                        "role": "user",
                        "content": f"Context from previous documents:\n\n{context_text}"
                    })

                # 添加用户提示词
                messages.append({"role": "user", "content": prompt})

                logger.info(f"Sending request to Gemini via OpenAI-compatible API (model: {self.model_name})")

                response = await self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages
                )

                content = response.choices[0].message.content
                logger.info(f"Received response from Gemini ({len(content)} characters)")

                return content

            else:
                # 使用 Google 官方 SDK
                # 构建完整的提示词
                full_prompt = ""

                # 添加系统提示词
                if system_prompt:
                    full_prompt += f"{system_prompt}\n\n"
                else:
                    full_prompt += ("You are a Chief Intelligence Officer and senior academic editor. "
                                   "Your role is deep research, venue taste analysis, narrative options, "
                                   "and 'Reviewer #2' red-team critique.\n\n")

                # 添加上下文
                if context:
                    context_text = "\n\n---\n\n".join(context)
                    full_prompt += f"Context from previous documents:\n\n{context_text}\n\n"

                # 添加用户提示词
                full_prompt += prompt

                logger.info(f"Sending request to Gemini (model: {self.model_name})")

                # 使用异步生成
                response = await asyncio.to_thread(
                    self.model.generate_content,
                    full_prompt
                )

                content = response.text
                logger.info(f"Received response from Gemini ({len(content)} characters)")

                return content

        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise AIClientError(f"Gemini API error: {str(e)}")

    async def chat_with_thinking(self, prompt: str, context: Optional[List[str]] = None,
                                 system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """
        发送聊天请求到 Gemini（Gemini 不支持显式的思考模式）

        Args:
            prompt: 用户提示词
            context: 上下文文档列表
            system_prompt: 系统提示词

        Returns:
            Dict: 包含响应内容
        """
        content = await self.chat(prompt, context, system_prompt)
        return {
            "content": content,
            "thinking": None,
            "model": settings.gemini_model
        }


# 工厂函数
def create_chatgpt_client(vector_store=None) -> ChatGPTClient:
    """创建 ChatGPT 客户端"""
    return ChatGPTClient(vector_store=vector_store)


def create_gemini_client(vector_store=None) -> GeminiClient:
    """创建 Gemini 客户端"""
    return GeminiClient(vector_store=vector_store)
