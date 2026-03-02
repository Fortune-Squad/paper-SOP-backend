"""
Session Logger
v1.2 DevSpec §5.8 - 三时机写入 (Plan / Decisions / Wrap-up)

管理 execution/session_logs/session_{timestamp}.md 文件
"""
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SessionLog(BaseModel):
    """Session log 数据结构"""
    session_id: str
    created_at: datetime = Field(default_factory=datetime.now)
    # Phase 1: Plan
    goal: Optional[str] = None
    approach: Optional[str] = None
    rejected_alternatives: List[str] = Field(default_factory=list)
    token_estimate: Optional[int] = None
    # Phase 2: Decisions
    decisions: List[Dict[str, str]] = Field(default_factory=list)
    # Phase 3: Wrap-up
    completed: Optional[str] = None
    remaining: Optional[str] = None
    next_steps: Optional[str] = None
    memory_updates: List[str] = Field(default_factory=list)


class SessionLogger:
    """
    Session log 管理器
    
    三时机写入 (Sant'Anna 模式):
    1. Plan 批准后 → 创建 log，记录目标、方案、被否决的替代方案
    2. 实施过程中 → 每个决策点增量写入 (1-3 行)
    3. Session 结束时 → 总结完成了什么、遗留问题、下一步
    """
    
    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.logs_dir = self.project_path / "execution" / "session_logs"
    
    def _ensure_dir(self):
        """确保 session_logs 目录存在"""
        self.logs_dir.mkdir(parents=True, exist_ok=True)
    
    def create_session(
        self,
        goal: str,
        approach: str,
        rejected_alternatives: Optional[List[str]] = None,
        token_estimate: Optional[int] = None
    ) -> str:
        """
        Phase 1: Plan — 创建新 session log
        
        Returns:
            session_id: 新创建的 session ID
        """
        self._ensure_dir()
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_id = f"session_{timestamp}"
        
        content = f"""# Session Log: {timestamp}

## 1. Plan
- **目标**: {goal}
- **方案**: {approach}
"""
        if rejected_alternatives:
            content += "- **被否决的替代方案**:\n"
            for alt in rejected_alternatives:
                content += f"  - {alt}\n"
        
        if token_estimate:
            content += f"- **预估 token**: {token_estimate}\n"
        
        content += "\n## 2. Decisions\n"
        
        log_path = self.logs_dir / f"{session_id}.md"
        log_path.write_text(content, encoding="utf-8")
        
        logger.info(f"Created session log: {session_id}")
        return session_id
    
    def log_decision(self, session_id: str, decision: str) -> None:
        """
        Phase 2: Decisions — 增量写入决策记录
        
        Args:
            session_id: Session ID
            decision: 决策描述 (1-3 行)
        """
        log_path = self.logs_dir / f"{session_id}.md"
        if not log_path.exists():
            logger.warning(f"Session log not found: {session_id}")
            return
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"- {timestamp} {decision}\n"
        
        content = log_path.read_text(encoding="utf-8")
        
        # 在 Wrap-up section 之前插入，或者在文件末尾追加
        if "## 3. Wrap-up" in content:
            content = content.replace("## 3. Wrap-up", f"{entry}\n## 3. Wrap-up")
        else:
            content += entry
        
        log_path.write_text(content, encoding="utf-8")
        logger.debug(f"Logged decision in {session_id}: {decision[:50]}...")
    
    def wrap_up(
        self,
        session_id: str,
        completed: str,
        remaining: str,
        next_steps: str,
        memory_updates: Optional[List[str]] = None
    ) -> None:
        """
        Phase 3: Wrap-up — 写入 session 总结
        
        Args:
            session_id: Session ID
            completed: 完成了什么
            remaining: 遗留问题
            next_steps: 下一步
            memory_updates: MEMORY.md 更新列表
        """
        log_path = self.logs_dir / f"{session_id}.md"
        if not log_path.exists():
            logger.warning(f"Session log not found: {session_id}")
            return
        
        content = log_path.read_text(encoding="utf-8")
        
        wrapup = f"""
## 3. Wrap-up
- **完成**: {completed}
- **遗留**: {remaining}
- **下一步**: {next_steps}
"""
        if memory_updates:
            wrapup += "- **MEMORY 更新**:\n"
            for update in memory_updates:
                wrapup += f"  - {update}\n"
        
        # 替换已有的 Wrap-up 或追加
        if "## 3. Wrap-up" in content:
            # 替换从 ## 3. Wrap-up 到文件末尾
            idx = content.index("## 3. Wrap-up")
            content = content[:idx] + wrapup.lstrip("\n")
        else:
            content += wrapup
        
        log_path.write_text(content, encoding="utf-8")
        logger.info(f"Wrapped up session: {session_id}")
    
    def get_latest_wrapup(self) -> Optional[str]:
        """获取最近一次 session 的 wrap-up 内容（用于 Session Resume）"""
        if not self.logs_dir.exists():
            return None
        
        logs = sorted(self.logs_dir.glob("session_*.md"), reverse=True)
        if not logs:
            return None
        
        content = logs[0].read_text(encoding="utf-8")
        
        if "## 3. Wrap-up" in content:
            idx = content.index("## 3. Wrap-up")
            return content[idx:]
        
        return None
    
    def list_sessions(self) -> List[Dict]:
        """列出所有 session logs"""
        if not self.logs_dir.exists():
            return []
        
        sessions = []
        for log_path in sorted(self.logs_dir.glob("session_*.md")):
            content = log_path.read_text(encoding="utf-8")
            
            # 提取目标
            goal = ""
            for line in content.split("\n"):
                if line.startswith("- **目标**:"):
                    goal = line.replace("- **目标**:", "").strip()
                    break
            
            has_wrapup = "## 3. Wrap-up" in content
            
            sessions.append({
                "session_id": log_path.stem,
                "created_at": log_path.stat().st_mtime,
                "goal": goal,
                "has_wrapup": has_wrapup,
                "file_path": str(log_path)
            })
        
        return sessions
    
    def get_session_content(self, session_id: str) -> Optional[str]:
        """获取指定 session log 的完整内容"""
        log_path = self.logs_dir / f"{session_id}.md"
        if not log_path.exists():
            return None
        return log_path.read_text(encoding="utf-8")
