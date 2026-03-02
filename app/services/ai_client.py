"""
AI 客户端封装（增强版）
统一封装 OpenAI API 和 Gemini API，支持重试机制、向量数据库集成和详细日志记录
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import asyncio
import time
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, RetryCallState
import logging

from openai import AsyncOpenAI, OpenAIError
import google.generativeai as genai

from app.config import settings
from app.utils.api_logger import api_logger
from app.services.agentic_wrapper import AgenticWrapper
from app.utils.trace_logger import TraceLogger

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


def log_retry_attempt(retry_state: RetryCallState):
    """重试回调函数"""
    exception = retry_state.outcome.exception()
    attempt_number = retry_state.attempt_number
    logger.warning(
        f"🔄 Retry attempt {attempt_number} | "
        f"Error: {type(exception).__name__}: {str(exception)}"
    )


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
        logger.info(f"Max retries set to {settings.max_retries}")

    @retry(
        stop=stop_after_attempt(settings.max_retries),
        wait=wait_exponential(multiplier=1, min=settings.retry_delay, max=60),
        retry=retry_if_exception_type(OpenAIError),
        before_sleep=log_retry_attempt,
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
        start_time = time.time()
        error = None
        response_data = None
        status = "success"

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

            logger.info(f"📤 Sending request to ChatGPT (model: {self.model})")

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )

            content = response.choices[0].message.content
            logger.info(f"📥 Received response from ChatGPT ({len(content)} characters)")

            # 提取 token 使用信息
            usage = None
            if hasattr(response, 'usage') and response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }
                logger.info(
                    f"💰 Token usage: {usage['total_tokens']} total "
                    f"({usage['prompt_tokens']} prompt + {usage['completion_tokens']} completion)"
                )

            response_data = {
                "content": content,
                "usage": usage
            }

            return content

        except OpenAIError as e:
            error = e
            status = "error"
            if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                status = "timeout"
                logger.error(f"⏱ ChatGPT API timeout: {e}")
            else:
                logger.error(f"❌ ChatGPT API error: {e}")
            raise AIClientError(f"ChatGPT API error: {str(e)}")
        except Exception as e:
            error = e
            status = "error"
            logger.error(f"❌ Unexpected error in ChatGPT client: {e}")
            raise AIClientError(f"Unexpected error: {str(e)}")
        finally:
            duration = time.time() - start_time

            # 记录详细日志
            api_logger.log_api_call(
                provider="openai",
                model=self.model,
                request_data={
                    "prompt": prompt,
                    "context": context or [],
                    "system_prompt": system_prompt
                },
                response_data=response_data,
                error=error,
                duration=duration,
                retry_count=0,  # tenacity 会自动处理重试
                status=status
            )

    @retry(
        stop=stop_after_attempt(settings.max_retries),
        wait=wait_exponential(multiplier=1, min=settings.retry_delay, max=60),
        retry=retry_if_exception_type(OpenAIError),
        before_sleep=log_retry_attempt,
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
        start_time = time.time()
        error = None
        response_data = None
        status = "success"

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

                logger.info(f"📤 Sending request to ChatGPT with thinking (model: {self.model})")

                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages
                )

                content = response.choices[0].message.content
                thinking = response.choices[0].message.content if hasattr(response.choices[0].message, 'reasoning') else None

                logger.info(f"📥 Received response from ChatGPT with thinking ({len(content)} characters)")

                # 提取 token 使用信息
                usage = None
                if hasattr(response, 'usage') and response.usage:
                    usage = {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens
                    }

                response_data = {
                    "content": content,
                    "thinking": thinking,
                    "model": self.model,
                    "usage": usage
                }

                return response_data
            else:
                # 对于非 o1 模型，使用普通模式
                content = await self.chat(prompt, context, system_prompt)
                return {
                    "content": content,
                    "thinking": None,
                    "model": self.model
                }

        except OpenAIError as e:
            error = e
            status = "error"
            if "timeout" in str(e).lower():
                status = "timeout"
            logger.error(f"❌ ChatGPT API error: {e}")
            raise AIClientError(f"ChatGPT API error: {str(e)}")
        except Exception as e:
            error = e
            status = "error"
            logger.error(f"❌ Unexpected error in ChatGPT client: {e}")
            raise AIClientError(f"Unexpected error: {str(e)}")
        finally:
            duration = time.time() - start_time

            # 记录详细日志
            api_logger.log_api_call(
                provider="openai",
                model=self.model,
                request_data={
                    "prompt": prompt,
                    "context": context or [],
                    "system_prompt": system_prompt
                },
                response_data=response_data,
                error=error,
                duration=duration,
                retry_count=0,
                status=status
            )


class GeminiClient(AIClient):
    """Gemini 客户端（情报官/编辑角色）- v4.0 with Agentic Wrapper"""

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
        logger.info(f"Max retries set to {settings.max_retries}")

        self.model_name = settings.gemini_model

        # v4.0: Initialize Agentic Wrapper
        self.agentic_wrapper = None
        if settings.agentic_wrapper_enabled and settings.gemini_gem_config_path:
            try:
                self.agentic_wrapper = AgenticWrapper(settings.gemini_gem_config_path)
                logger.info("✅ Agentic Wrapper enabled for Gemini")
            except Exception as e:
                logger.warning(f"Failed to initialize Agentic Wrapper: {e}, continuing without it")
                self.agentic_wrapper = None

        # v4.1: Initialize TraceLogger for raw response preservation
        self.trace_logger = None
        try:
            self.trace_logger = TraceLogger(settings.projects_path)
            logger.info("✅ TraceLogger initialized for raw response preservation")
        except Exception as e:
            logger.warning(f"Failed to initialize TraceLogger: {e}, continuing without it")
            self.trace_logger = None

    @retry(
        stop=stop_after_attempt(settings.max_retries),
        wait=wait_exponential(multiplier=1, min=settings.retry_delay, max=60),
        before_sleep=log_retry_attempt,
        reraise=True
    )
    async def chat(self, prompt: str, context: Optional[List[str]] = None,
                   system_prompt: Optional[str] = None, max_tokens: Optional[int] = None,
                   wrapper_mode: Optional[str] = None,
                   project_id: Optional[str] = None,
                   step_id: Optional[str] = None) -> str:
        """
        发送聊天请求到 Gemini (v4.0 with Agentic Wrapper, v4.1 with Raw Response Preservation)

        Args:
            prompt: 用户提示词
            context: 上下文文档列表
            system_prompt: 系统提示词
            max_tokens: 最大输出 token 数（可选，用于长篇输出）
            wrapper_mode: Agentic Wrapper 模式 ("full", "lite", "minimal", "disabled")，覆盖默认模式
            project_id: 项目 ID（用于保存 trace）
            step_id: 步骤 ID（用于保存 trace）

        Returns:
            str: Gemini 响应内容（仅 Deliverables 部分）
        """
        start_time = time.time()
        error = None
        response_data = None
        status = "success"

        try:
            # v4.0: Apply Agentic Wrapper to prompt
            wrapped_prompt = prompt
            final_system_prompt = system_prompt

            if self.agentic_wrapper:
                wrapped_prompt = self.agentic_wrapper.wrap_prompt(prompt, system_prompt, mode=wrapper_mode)
                # Use Agentic Wrapper's system prompt if no custom one provided
                if not system_prompt:
                    final_system_prompt = self.agentic_wrapper.get_system_prompt()
                effective_mode = wrapper_mode if wrapper_mode else self.agentic_wrapper.mode
                logger.info(f"🔄 Applied Agentic Wrapper to prompt (mode: {effective_mode})")

            # 如果使用 OpenAI 兼容接口（TokHub）
            if self.use_openai_compatible:
                messages = []

                # 添加系统提示词
                if final_system_prompt:
                    messages.append({"role": "system", "content": final_system_prompt})
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

                # 添加用户提示词（已包装）
                messages.append({"role": "user", "content": wrapped_prompt})

                logger.info(f"📤 Sending request to Gemini via OpenAI-compatible API (model: {self.model_name}, max_tokens: {max_tokens or 'default'})")

                # 构建请求参数
                request_params = {
                    "model": self.model_name,
                    "messages": messages
                }

                # 如果指定了 max_tokens，添加到请求中
                if max_tokens:
                    request_params["max_tokens"] = max_tokens

                response = await self.client.chat.completions.create(**request_params)

                raw_content = response.choices[0].message.content
                logger.info(f"📥 Received response from Gemini ({len(raw_content)} characters)")

                # v4.1: 🔥 CRITICAL - Save raw response FIRST (before any processing)
                if self.trace_logger and project_id and step_id:
                    try:
                        trace_path = self.trace_logger.save_raw_response(
                            project_id=project_id,
                            step_id=step_id,
                            response=raw_content,
                            metadata={
                                'model': self.model_name,
                                'wrapper_mode': effective_mode,
                                'timestamp': time.time(),
                                'prompt_length': len(prompt),
                                'context_count': len(context) if context else 0,
                                'max_tokens': max_tokens
                            }
                        )
                        if trace_path:
                            logger.info(f"✓ Raw response saved to trace: {trace_path}")
                    except Exception as e:
                        logger.error(f"❌ Failed to save raw response: {e}")
                        # Don't interrupt the main flow

                # v4.0: Validate and extract deliverables from Agentic response
                effective_mode = wrapper_mode if wrapper_mode else (self.agentic_wrapper.mode if self.agentic_wrapper else None)

                if self.agentic_wrapper and effective_mode != "disabled":
                    validation = self.agentic_wrapper.validate_response(raw_content)

                    if not validation["valid"]:
                        logger.warning(f"⚠️ Agentic response validation failed: {validation['errors']}")

                    if validation["warnings"]:
                        logger.warning(f"⚠️ Agentic response warnings: {validation['warnings']}")

                    if validation["confidence_score"] is not None:
                        logger.info(f"🎯 Confidence score: {validation['confidence_score']:.2f}")

                    # v4.1: Extract deliverables with fallback mechanism
                    try:
                        extraction_result = self.agentic_wrapper.extract_deliverables(raw_content)
                        content = extraction_result["content"]
                        logger.info(f"📦 Extracted deliverables ({len(content)} characters) using {extraction_result['extraction_method']}")

                        # Log extraction warnings if any
                        if extraction_result.get("warnings"):
                            for warning in extraction_result["warnings"]:
                                logger.warning(f"⚠️ Extraction warning: {warning}")

                        # Log meta information if available
                        if extraction_result.get("meta"):
                            logger.info(f"📋 Meta information extracted: {list(extraction_result['meta'].keys())}")

                            # v4.1: Save sidecar meta to file if using sidecar_meta mode
                            if extraction_result["extraction_method"] == "sidecar_meta" and project_id and step_id:
                                try:
                                    from pathlib import Path
                                    from app.services.agentic_wrapper import AgenticWrapper
                                    project_path = Path(settings.projects_path) / project_id
                                    meta_path = AgenticWrapper.save_sidecar_meta(
                                        meta=extraction_result["meta"],
                                        project_path=project_path,
                                        step_id=step_id
                                    )
                                    logger.info(f"✓ Sidecar meta saved to {meta_path}")
                                except Exception as e:
                                    logger.error(f"❌ Failed to save sidecar meta: {e}")
                                    # Don't fail the entire operation if meta save fails
                    except Exception as e:
                        logger.error(f"❌ Extraction failed: {e}, using raw response as fallback")
                        content = raw_content  # 🔥 FALLBACK: Use raw response to prevent data loss
                else:
                    # Disabled mode or no wrapper: use raw content
                    content = raw_content
                    if effective_mode == "disabled":
                        logger.info(f"✓ Using raw content (disabled mode): {len(content)} characters")

                # 提取 token 使用信息
                usage = None
                if hasattr(response, 'usage') and response.usage:
                    usage = {
                        "prompt_tokens": response.usage.prompt_tokens,
                        "completion_tokens": response.usage.completion_tokens,
                        "total_tokens": response.usage.total_tokens
                    }
                    logger.info(
                        f"💰 Token usage: {usage['total_tokens']} total "
                        f"({usage['prompt_tokens']} prompt + {usage['completion_tokens']} completion)"
                    )

                response_data = {
                    "content": content,
                    "raw_content": raw_content if self.agentic_wrapper else content,
                    "usage": usage
                }

                return content

            else:
                # 使用 Google 官方 SDK
                full_prompt = ""

                # 添加系统提示词
                if final_system_prompt:
                    full_prompt += f"{final_system_prompt}\n\n"
                else:
                    full_prompt += ("You are a Chief Intelligence Officer and senior academic editor. "
                                   "Your role is deep research, venue taste analysis, narrative options, "
                                   "and 'Reviewer #2' red-team critique.\n\n")

                # 添加上下文
                if context:
                    context_text = "\n\n---\n\n".join(context)
                    full_prompt += f"Context from previous documents:\n\n{context_text}\n\n"

                # 添加用户提示词（已包装）
                full_prompt += wrapped_prompt

                logger.info(f"📤 Sending request to Gemini (model: {self.model_name})")

                # 使用异步生成
                response = await asyncio.to_thread(
                    self.model.generate_content,
                    full_prompt
                )

                raw_content = response.text
                logger.info(f"📥 Received response from Gemini ({len(raw_content)} characters)")

                # v4.1: 🔥 CRITICAL - Save raw response FIRST (before any processing)
                if self.trace_logger and project_id and step_id:
                    try:
                        trace_path = self.trace_logger.save_raw_response(
                            project_id=project_id,
                            step_id=step_id,
                            response=raw_content,
                            metadata={
                                'model': self.model_name,
                                'wrapper_mode': effective_mode,
                                'timestamp': time.time(),
                                'prompt_length': len(prompt),
                                'context_count': len(context) if context else 0
                            }
                        )
                        if trace_path:
                            logger.info(f"✓ Raw response saved to trace: {trace_path}")
                    except Exception as e:
                        logger.error(f"❌ Failed to save raw response: {e}")
                        # Don't interrupt the main flow

                # v4.0: Validate and extract deliverables from Agentic response
                effective_mode = wrapper_mode if wrapper_mode else (self.agentic_wrapper.mode if self.agentic_wrapper else None)

                if self.agentic_wrapper and effective_mode != "disabled":
                    validation = self.agentic_wrapper.validate_response(raw_content)

                    if not validation["valid"]:
                        logger.warning(f"⚠️ Agentic response validation failed: {validation['errors']}")

                    if validation["warnings"]:
                        logger.warning(f"⚠️ Agentic response warnings: {validation['warnings']}")

                    if validation["confidence_score"] is not None:
                        logger.info(f"🎯 Confidence score: {validation['confidence_score']:.2f}")

                    # v4.1: Extract deliverables with fallback mechanism
                    try:
                        extraction_result = self.agentic_wrapper.extract_deliverables(raw_content)
                        content = extraction_result["content"]
                        logger.info(f"📦 Extracted deliverables ({len(content)} characters) using {extraction_result['extraction_method']}")

                        # Log extraction warnings if any
                        if extraction_result.get("warnings"):
                            for warning in extraction_result["warnings"]:
                                logger.warning(f"⚠️ Extraction warning: {warning}")

                        # Log meta information if available
                        if extraction_result.get("meta"):
                            logger.info(f"📋 Meta information extracted: {list(extraction_result['meta'].keys())}")

                            # v4.1: Save sidecar meta to file if using sidecar_meta mode
                            if extraction_result["extraction_method"] == "sidecar_meta" and project_id and step_id:
                                try:
                                    from pathlib import Path
                                    from app.services.agentic_wrapper import AgenticWrapper
                                    project_path = Path(settings.projects_path) / project_id
                                    meta_path = AgenticWrapper.save_sidecar_meta(
                                        meta=extraction_result["meta"],
                                        project_path=project_path,
                                        step_id=step_id
                                    )
                                    logger.info(f"✓ Sidecar meta saved to {meta_path}")
                                except Exception as e:
                                    logger.error(f"❌ Failed to save sidecar meta: {e}")
                                    # Don't fail the entire operation if meta save fails
                    except Exception as e:
                        logger.error(f"❌ Extraction failed: {e}, using raw response as fallback")
                        content = raw_content  # 🔥 FALLBACK: Use raw response to prevent data loss
                else:
                    # Disabled mode or no wrapper: use raw content
                    content = raw_content
                    if effective_mode == "disabled":
                        logger.info(f"✓ Using raw content (disabled mode): {len(content)} characters")

                response_data = {
                    "content": content,
                    "raw_content": raw_content if self.agentic_wrapper else content,
                    "usage": None  # Google SDK 不提供 token 使用信息
                }

                return content

        except Exception as e:
            error = e
            status = "error"
            if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                status = "timeout"
                logger.error(f"⏱ Gemini API timeout: {e}")
            else:
                logger.error(f"❌ Gemini API error: {e}")
            raise AIClientError(f"Gemini API error: {str(e)}")
        finally:
            duration = time.time() - start_time

            # 记录详细日志
            api_logger.log_api_call(
                provider="gemini",
                model=self.model_name,
                request_data={
                    "prompt": prompt,
                    "context": context or [],
                    "system_prompt": system_prompt
                },
                response_data=response_data,
                error=error,
                duration=duration,
                retry_count=0,
                status=status
            )

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
