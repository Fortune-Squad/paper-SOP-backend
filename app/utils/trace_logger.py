"""
Trace Logger for Raw AI Response Preservation
Saves raw AI responses before any processing to prevent data loss

v1.2 §15: 新增 event_type 支持（ra_request, ra_result, memory_update, session_log_write）
"""
from pathlib import Path
import json
from datetime import datetime
import logging
from typing import Optional, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


class TraceEventType(str, Enum):
    """v1.2 §15: Trace 事件类型"""
    AI_RESPONSE = "ai_response"  # 原有：AI 响应
    RA_REQUEST = "ra_request"  # v1.2 新增：RA 请求
    RA_RESULT = "ra_result"  # v1.2 新增：RA 结果
    MEMORY_UPDATE = "memory_update"  # v1.2 新增：MEMORY.md 更新
    SESSION_LOG_WRITE = "session_log_write"  # v1.2 新增：session_log 写入


class TraceLogger:
    """
    保存 AI 原始响应的工具类

    功能：
    - 在任何处理之前保存原始响应
    - 提供恢复机制
    - 支持审计追踪
    """

    def __init__(self, projects_path: str):
        """
        初始化 TraceLogger

        Args:
            projects_path: 项目根目录路径
        """
        self.projects_path = Path(projects_path)
        logger.info(f"TraceLogger initialized with projects_path: {projects_path}")

    def save_raw_response(self, project_id: str, step_id: str,
                         response: str, metadata: Optional[Dict[str, Any]] = None,
                         event_type: TraceEventType = TraceEventType.AI_RESPONSE) -> str:
        """
        保存原始 AI 响应（在任何处理之前）

        这是防止数据丢失的关键步骤：
        1. 接收原始响应后立即调用此方法
        2. 在任何 extract_deliverables() 或其他处理之前
        3. 如果提取失败，可以从 trace 文件恢复

        Args:
            project_id: 项目 ID
            step_id: 步骤 ID
            response: 原始响应内容
            metadata: 元数据（可选），包含 model, wrapper_mode, timestamp 等
            event_type: 事件类型（v1.2 §15 新增）

        Returns:
            str: 保存的文件路径

        Raises:
            Exception: 如果保存失败（不应中断主流程）
        """
        try:
            # 创建 trace 目录
            trace_dir = self.projects_path / project_id / "logs" / "traces"
            trace_dir.mkdir(parents=True, exist_ok=True)

            # 生成文件名（带时间戳和事件类型）
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            trace_file = trace_dir / f"{step_id}_{event_type.value}_{timestamp}.md"

            # 写入文件
            with open(trace_file, 'w', encoding='utf-8') as f:
                f.write(f"# Trace Event: {event_type.value}\n\n")
                f.write(f"- **Event Type**: {event_type.value}\n")
                f.write(f"- **Step ID**: {step_id}\n")
                f.write(f"- **Project ID**: {project_id}\n")
                f.write(f"- **Timestamp**: {timestamp}\n")
                f.write(f"- **Length**: {len(response)} characters\n")
                f.write(f"- **Lines**: {response.count(chr(10)) + 1}\n\n")

                if metadata:
                    f.write(f"## Metadata\n\n")
                    f.write(f"```json\n{json.dumps(metadata, indent=2, ensure_ascii=False)}\n```\n\n")

                f.write(f"## Content\n\n")
                f.write(response)

            logger.info(f"✓ Saved trace event [{event_type.value}] to {trace_file} ({len(response)} chars)")
            return str(trace_file)

        except Exception as e:
            logger.error(f"❌ Failed to save trace event: {e}")
            # 不要抛出异常，避免中断主流程
            return ""

    def load_raw_response(self, project_id: str, step_id: str,
                         timestamp: Optional[str] = None) -> str:
        """
        加载原始响应（用于恢复）

        Args:
            project_id: 项目 ID
            step_id: 步骤 ID
            timestamp: 时间戳（可选），如果不提供则加载最新的

        Returns:
            str: 原始响应内容

        Raises:
            FileNotFoundError: 如果找不到 trace 文件
        """
        trace_dir = self.projects_path / project_id / "logs" / "traces"

        if timestamp:
            # 加载指定时间戳的文件（尝试新旧格式）
            trace_file = trace_dir / f"{step_id}_ai_response_{timestamp}.md"
            if not trace_file.exists():
                # 尝试旧格式
                trace_file = trace_dir / f"{step_id}_raw_{timestamp}.md"
            if not trace_file.exists():
                raise FileNotFoundError(f"Trace file not found: {trace_file}")
        else:
            # 找最新的文件（支持新旧格式）
            files = list(trace_dir.glob(f"{step_id}_ai_response_*.md"))
            files.extend(list(trace_dir.glob(f"{step_id}_raw_*.md")))
            if not files:
                raise FileNotFoundError(f"No trace files found for {step_id} in {trace_dir}")
            trace_file = max(files, key=lambda p: p.stat().st_mtime)

        logger.info(f"Loading raw response from {trace_file}")

        with open(trace_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 提取原始响应部分
        if "## Content" in content:
            raw_response = content.split("## Content")[1].strip()
            # 移除开头的空行
            raw_response = raw_response.lstrip('\n')
            logger.info(f"✓ Loaded raw response ({len(raw_response)} chars)")
            return raw_response
        elif "## Raw Response" in content:
            # 向后兼容旧格式
            raw_response = content.split("## Raw Response")[1].strip()
            raw_response = raw_response.lstrip('\n')
            logger.info(f"✓ Loaded raw response ({len(raw_response)} chars)")
            return raw_response

        # 如果没有找到标记，返回整个内容
        logger.warning("⚠️ Could not find '## Content' or '## Raw Response' marker, returning full content")
        return content

    def list_raw_responses(self, project_id: str, step_id: Optional[str] = None) -> list:
        """
        列出所有原始响应文件

        Args:
            project_id: 项目 ID
            step_id: 步骤 ID（可选），如果不提供则列出所有步骤

        Returns:
            list: 文件路径列表，按修改时间排序（最新的在前）
        """
        trace_dir = self.projects_path / project_id / "logs" / "traces"

        if not trace_dir.exists():
            logger.warning(f"Trace directory does not exist: {trace_dir}")
            return []

        if step_id:
            # 支持新旧格式
            pattern1 = f"{step_id}_ai_response_*.md"
            pattern2 = f"{step_id}_raw_*.md"
            files = list(trace_dir.glob(pattern1))
            files.extend(list(trace_dir.glob(pattern2)))
        else:
            # 支持新旧格式
            pattern1 = "*_ai_response_*.md"
            pattern2 = "*_raw_*.md"
            files = list(trace_dir.glob(pattern1))
            files.extend(list(trace_dir.glob(pattern2)))

        # 按修改时间排序（最新的在前）
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        logger.info(f"Found {len(files)} trace files for project {project_id}")
        return [str(f) for f in files]

    def get_trace_metadata(self, trace_file: str) -> Dict[str, Any]:
        """
        从 trace 文件中提取元数据

        Args:
            trace_file: trace 文件路径

        Returns:
            dict: 元数据字典
        """
        try:
            with open(trace_file, 'r', encoding='utf-8') as f:
                content = f.read()

            metadata = {}

            # 提取基本信息
            for line in content.split('\n'):
                if line.startswith('- **Event Type**:'):
                    metadata['event_type'] = line.split(':')[1].strip()
                elif line.startswith('- **Step ID**:'):
                    metadata['step_id'] = line.split(':')[1].strip()
                elif line.startswith('- **Project ID**:'):
                    metadata['project_id'] = line.split(':')[1].strip()
                elif line.startswith('- **Timestamp**:'):
                    metadata['timestamp'] = line.split(':')[1].strip()
                elif line.startswith('- **Length**:'):
                    metadata['length'] = line.split(':')[1].strip()
                elif line.startswith('- **Lines**:'):
                    metadata['lines'] = line.split(':')[1].strip()

            # 提取 JSON 元数据
            if "## Metadata" in content and "```json" in content:
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                if json_end > json_start:
                    json_str = content[json_start:json_end].strip()
                    try:
                        metadata['api_metadata'] = json.loads(json_str)
                    except json.JSONDecodeError:
                        logger.warning("Failed to parse JSON metadata")

            return metadata

        except Exception as e:
            logger.error(f"Failed to extract metadata from {trace_file}: {e}")
            return {}
