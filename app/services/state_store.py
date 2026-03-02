"""
StateStore 服务
Step 3 执行状态的持久化存储（state.json）

使用文件锁 + 版本号实现原子更新（乐观锁）
Windows 兼容：使用 portalocker 实现跨平台文件锁
"""
import json
import logging
import tempfile
import os
import socket
from pathlib import Path
from typing import Callable, Optional
from datetime import datetime

import portalocker

from app.models.work_package import ExecutionState
from app.config import settings

logger = logging.getLogger(__name__)


class StateStoreError(Exception):
    """StateStore 错误"""
    pass


class VersionConflictError(StateStoreError):
    """版本冲突错误（乐观锁失败）"""
    pass


class StateStore:
    """
    Step 3 执行状态存储

    state.json 是 Step 3 的唯一真相源。
    Project 模型只跟踪高层标志（step3_started/completed），
    WP 级状态全在 state.json。
    """

    def __init__(self, projects_path: Optional[str] = None):
        self.projects_path = Path(projects_path or settings.projects_path)

    def _state_file(self, project_id: str) -> Path:
        """获取 state.json 路径"""
        return self.projects_path / project_id / "state.json"

    def exists(self, project_id: str) -> bool:
        """检查 state.json 是否存在"""
        return self._state_file(project_id).exists()

    def load(self, project_id: str) -> ExecutionState:
        """
        读取 state.json

        Args:
            project_id: 项目 ID

        Returns:
            ExecutionState: 执行状态

        Raises:
            StateStoreError: 读取失败
        """
        state_file = self._state_file(project_id)
        if not state_file.exists():
            raise StateStoreError(f"state.json not found for project {project_id}")

        try:
            with open(str(state_file), 'r', encoding='utf-8') as f:
                portalocker.lock(f, portalocker.LOCK_SH)
                content = f.read()
                portalocker.unlock(f)
                return ExecutionState.model_validate_json(content)
        except portalocker.exceptions.LockException:
            raise StateStoreError(f"Failed to acquire lock on state.json for project {project_id}")
        except Exception as e:
            raise StateStoreError(f"Failed to load state.json: {e}")

    def update(
        self,
        project_id: str,
        mutator_fn: Callable[[ExecutionState], ExecutionState],
        expected_version: Optional[int] = None
    ) -> ExecutionState:
        """
        原子更新 state.json

        Args:
            project_id: 项目 ID
            mutator_fn: 状态变更函数
            expected_version: 期望的版本号（乐观锁）

        Returns:
            ExecutionState: 更新后的状态

        Raises:
            VersionConflictError: 版本冲突
            StateStoreError: 更新失败
        """
        state_file = self._state_file(project_id)

        try:
            with open(str(state_file), 'r+', encoding='utf-8') as f:
                portalocker.lock(f, portalocker.LOCK_EX)
                content = f.read()
                state = ExecutionState.model_validate_json(content)

                # 乐观锁检查
                if expected_version is not None and state.state_version != expected_version:
                    raise VersionConflictError(
                        f"Version conflict: expected {expected_version}, got {state.state_version}"
                    )

                # 应用变更
                new_state = mutator_fn(state)
                new_state.state_version = state.state_version + 1
                new_state.updated_at = datetime.now()

                # §2.2.2: 自动填充 last_writer
                new_state.last_writer = {
                    "host": socket.gethostname(),
                    "pid": os.getpid(),
                    "worker_id": f"backend-{os.getpid()}",
                }

                # 原子写入
                f.seek(0)
                f.truncate()
                f.write(new_state.model_dump_json(indent=2))
                f.flush()
                os.fsync(f.fileno())

                # v7.1: Update AGENTS.md dynamic section on state change
                try:
                    from app.services.snapshot_generator import SnapshotGenerator
                    project_path = str(self.projects_path / project_id)
                    snapshot_gen = SnapshotGenerator(project_path)
                    wp_states_dict = {wid: {"status": ws.status.value} for wid, ws in new_state.wp_states.items()}
                    dynamic = snapshot_gen.generate_agents_md_dynamic_section(
                        state={"current_phase": "step_3", "wp_states": wp_states_dict},
                    )
                    snapshot_gen.update_agents_md(dynamic)
                except Exception as snap_err:
                    # Non-blocking: don't let AGENTS.md update failure break state updates
                    pass

                return new_state

        except VersionConflictError:
            raise
        except portalocker.exceptions.LockException:
            raise StateStoreError(f"Failed to acquire lock on state.json for project {project_id}")
        except Exception as e:
            raise StateStoreError(f"Failed to update state.json: {e}")

    def save_atomic(self, project_id: str, state: ExecutionState) -> None:
        """
        原子保存 state.json（用于初始创建）

        使用 tmp → fsync → rename 模式确保原子性

        Args:
            project_id: 项目 ID
            state: 执行状态
        """
        state_file = self._state_file(project_id)
        state_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            # 写入临时文件
            fd, tmp_path = tempfile.mkstemp(
                dir=str(state_file.parent),
                suffix='.tmp'
            )
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    f.write(state.model_dump_json(indent=2))
                    f.flush()
                    os.fsync(f.fileno())

                # 原子重命名（Windows 需要先删除目标文件）
                if os.name == 'nt' and state_file.exists():
                    os.replace(tmp_path, str(state_file))
                else:
                    os.rename(tmp_path, str(state_file))

                logger.info(f"Saved state.json for project {project_id} (version {state.state_version})")

            except Exception:
                # 清理临时文件
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise

        except Exception as e:
            raise StateStoreError(f"Failed to save state.json: {e}")
