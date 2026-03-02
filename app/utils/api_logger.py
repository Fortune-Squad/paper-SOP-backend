"""
API 调用日志记录模块
提供详细的 API 调用监控、统计和错误追踪功能
"""
import logging
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from functools import wraps
import traceback

from app.config import settings


class APICallLogger:
    """API 调用日志记录器"""

    def __init__(self):
        """初始化日志记录器"""
        # 创建日志目录
        log_dir = Path(settings.log_file).parent
        log_dir.mkdir(parents=True, exist_ok=True)

        # 主日志文件
        self.main_logger = logging.getLogger("api_calls")
        self.main_logger.setLevel(logging.INFO)

        # 详细日志文件（包含所有请求详情）
        detailed_handler = logging.FileHandler(
            log_dir / "api_calls_detailed.log",
            encoding='utf-8'
        )
        detailed_handler.setLevel(logging.DEBUG)
        detailed_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        detailed_handler.setFormatter(detailed_formatter)
        self.main_logger.addHandler(detailed_handler)

        # 错误日志文件（只记录错误）
        error_handler = logging.FileHandler(
            log_dir / "api_errors.log",
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s\n%(message)s\n' + '-'*80,
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        error_handler.setFormatter(error_formatter)
        self.main_logger.addHandler(error_handler)

        # 统计日志文件（JSON 格式，用于分析）
        self.stats_file = log_dir / "api_stats.jsonl"

        # 控制台输出
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        self.main_logger.addHandler(console_handler)

    def log_api_call(
        self,
        provider: str,
        model: str,
        request_data: Dict[str, Any],
        response_data: Optional[Dict[str, Any]] = None,
        error: Optional[Exception] = None,
        duration: Optional[float] = None,
        retry_count: int = 0,
        status: str = "success"
    ):
        """
        记录 API 调用详情

        Args:
            provider: API 提供商（openai, gemini）
            model: 模型名称
            request_data: 请求数据
            response_data: 响应数据
            error: 错误信息
            duration: 调用耗时（秒）
            retry_count: 重试次数
            status: 状态（success, error, timeout）
        """
        timestamp = datetime.now().isoformat()

        # 构建日志记录
        log_entry = {
            "timestamp": timestamp,
            "provider": provider,
            "model": model,
            "status": status,
            "duration_seconds": duration,
            "retry_count": retry_count,
            "request": {
                "prompt_length": len(str(request_data.get("prompt", ""))),
                "context_count": len(request_data.get("context", [])),
                "has_system_prompt": bool(request_data.get("system_prompt"))
            }
        }

        # 添加响应信息
        if response_data:
            log_entry["response"] = {
                "content_length": len(str(response_data.get("content", ""))),
                "has_thinking": bool(response_data.get("thinking"))
            }

            # 尝试提取 token 使用信息
            if "usage" in response_data:
                log_entry["usage"] = response_data["usage"]

        # 添加错误信息
        if error:
            log_entry["error"] = {
                "type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc()
            }

        # 写入统计文件（JSON Lines 格式）
        try:
            with open(self.stats_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
        except Exception as e:
            self.main_logger.error(f"Failed to write stats file: {e}")

        # 写入主日志
        if status == "success":
            self.main_logger.info(
                f"✓ {provider.upper()} API call succeeded | "
                f"Model: {model} | "
                f"Duration: {duration:.2f}s | "
                f"Retries: {retry_count} | "
                f"Response: {log_entry['response']['content_length']} chars"
            )
        elif status == "error":
            self.main_logger.error(
                f"✗ {provider.upper()} API call failed | "
                f"Model: {model} | "
                f"Duration: {duration:.2f}s if duration else 'N/A' | "
                f"Retries: {retry_count} | "
                f"Error: {error}"
            )
        elif status == "timeout":
            self.main_logger.warning(
                f"⏱ {provider.upper()} API call timeout | "
                f"Model: {model} | "
                f"Duration: {duration:.2f}s | "
                f"Retries: {retry_count}"
            )

    def log_retry_attempt(self, provider: str, model: str, attempt: int, error: Exception):
        """记录重试尝试"""
        self.main_logger.warning(
            f"🔄 Retry attempt {attempt} for {provider.upper()} | "
            f"Model: {model} | "
            f"Error: {type(error).__name__}: {str(error)}"
        )


# 全局日志记录器实例
api_logger = APICallLogger()


def log_api_call(provider: str, model: str):
    """
    装饰器：自动记录 API 调用

    Args:
        provider: API 提供商
        model: 模型名称
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            retry_count = 0
            error = None
            response = None
            status = "success"

            try:
                # 执行函数
                response = await func(*args, **kwargs)
                return response

            except Exception as e:
                error = e
                status = "error"

                # 判断是否为超时错误
                if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                    status = "timeout"

                raise

            finally:
                duration = time.time() - start_time

                # 提取请求数据
                request_data = {
                    "prompt": kwargs.get("prompt", ""),
                    "context": kwargs.get("context", []),
                    "system_prompt": kwargs.get("system_prompt")
                }

                # 提取响应数据
                response_data = None
                if response:
                    if isinstance(response, dict):
                        response_data = response
                    elif isinstance(response, str):
                        response_data = {"content": response}

                # 记录日志
                api_logger.log_api_call(
                    provider=provider,
                    model=model,
                    request_data=request_data,
                    response_data=response_data,
                    error=error,
                    duration=duration,
                    retry_count=retry_count,
                    status=status
                )

        return wrapper
    return decorator
