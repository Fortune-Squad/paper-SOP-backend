"""
AI 对话日志记录器
记录每个项目的 AI 交互过程，包括提示词和完整响应
"""
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class ConversationLogger:
    """AI 对话日志记录器"""

    def __init__(self, projects_path: str = "./projects"):
        """
        初始化对话日志记录器

        Args:
            projects_path: 项目根目录路径
        """
        self.projects_path = Path(projects_path)

    def _get_log_dir(self, project_id: str) -> Path:
        """
        获取项目的日志目录

        Args:
            project_id: 项目 ID

        Returns:
            Path: 日志目录路径
        """
        log_dir = self.projects_path / project_id / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir

    def _get_log_file(self, project_id: str, step_id: str) -> Path:
        """
        获取步骤的日志文件路径

        Args:
            project_id: 项目 ID
            step_id: 步骤 ID

        Returns:
            Path: 日志文件路径
        """
        log_dir = self._get_log_dir(project_id)
        return log_dir / f"{step_id}_ai_conversation.md"

    def log_conversation(
        self,
        project_id: str,
        step_id: str,
        model: str,
        system_prompt: Optional[str],
        user_prompt: str,
        context: Optional[list] = None,
        response: str = "",
        thinking: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        记录一次 AI 对话

        Args:
            project_id: 项目 ID
            step_id: 步骤 ID
            model: AI 模型名称
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            context: 上下文文档列表
            response: AI 响应内容
            thinking: 思考过程（如果有）
            metadata: 额外的元数据（如 tokens, latency 等）
        """
        try:
            log_file = self._get_log_file(project_id, step_id)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 构建日志内容
            log_content = f"\n\n{'='*80}\n"
            log_content += f"## 对话记录 - {timestamp}\n\n"
            log_content += f"**模型**: {model}\n\n"

            # 元数据
            if metadata:
                log_content += "**元数据**:\n"
                for key, value in metadata.items():
                    log_content += f"- {key}: {value}\n"
                log_content += "\n"

            # 系统提示词
            if system_prompt:
                log_content += "### 系统提示词 (System Prompt)\n\n"
                log_content += "```\n"
                log_content += system_prompt
                log_content += "\n```\n\n"

            # 上下文
            if context and len(context) > 0:
                log_content += "### 上下文 (Context)\n\n"
                for i, ctx in enumerate(context, 1):
                    log_content += f"#### 上下文文档 {i}\n\n"
                    log_content += "```\n"
                    # 限制上下文长度，避免日志过大
                    if len(ctx) > 2000:
                        log_content += ctx[:2000] + "\n... (truncated)\n"
                    else:
                        log_content += ctx
                    log_content += "\n```\n\n"

            # 用户提示词
            log_content += "### 用户提示词 (User Prompt)\n\n"
            log_content += "```\n"
            log_content += user_prompt
            log_content += "\n```\n\n"

            # 思考过程（如果有）
            if thinking:
                log_content += "### 思考过程 (Thinking)\n\n"
                log_content += "```\n"
                log_content += thinking
                log_content += "\n```\n\n"

            # AI 响应
            log_content += "### AI 响应 (Response)\n\n"
            log_content += "```\n"
            log_content += response
            log_content += "\n```\n\n"

            log_content += f"{'='*80}\n"

            # 追加写入日志文件
            with open(log_file, "a", encoding="utf-8") as f:
                # 如果是新文件，添加标题
                if log_file.stat().st_size == 0:
                    f.write(f"# AI 对话日志 - {step_id}\n\n")
                    f.write(f"**项目 ID**: {project_id}\n")
                    f.write(f"**步骤 ID**: {step_id}\n")
                    f.write(f"**创建时间**: {timestamp}\n\n")
                    f.write("---\n")

                f.write(log_content)

            logger.info(f"Logged conversation for {project_id}/{step_id} to {log_file}")

        except Exception as e:
            logger.error(f"Failed to log conversation: {e}")

    def get_conversation_history(self, project_id: str, step_id: str) -> Optional[str]:
        """
        获取步骤的对话历史

        Args:
            project_id: 项目 ID
            step_id: 步骤 ID

        Returns:
            Optional[str]: 对话历史内容，如果不存在则返回 None
        """
        try:
            log_file = self._get_log_file(project_id, step_id)
            if log_file.exists():
                with open(log_file, "r", encoding="utf-8") as f:
                    return f.read()
            return None
        except Exception as e:
            logger.error(f"Failed to read conversation history: {e}")
            return None

    def list_conversation_logs(self, project_id: str) -> list:
        """
        列出项目的所有对话日志文件

        Args:
            project_id: 项目 ID

        Returns:
            list: 日志文件列表
        """
        try:
            log_dir = self._get_log_dir(project_id)
            if log_dir.exists():
                return sorted([f.name for f in log_dir.glob("*_ai_conversation.md")])
            return []
        except Exception as e:
            logger.error(f"Failed to list conversation logs: {e}")
            return []


# 全局实例
conversation_logger = ConversationLogger()
