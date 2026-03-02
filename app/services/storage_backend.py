"""
Storage Backend 抽象接口
v1.2 DevSpec §12.2 - Orchestra 存储后端

提供统一的存储接口，支持本地文件系统、Box、Git 等后端。
默认使用 LocalBackend（零配置）。
"""
import logging
import json
import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class StorageBackend(ABC):
    """
    存储后端抽象接口

    所有后端必须实现以下方法：
    - push_state: 推送 state.json
    - pull_state: 拉取 state.json
    - push_snapshot: 推送 AGENTS.md 快照
    - push_artifact: 推送 artifact 文件
    - pull_artifact: 拉取 artifact 文件
    """

    @abstractmethod
    def push_state(self, state: dict) -> None:
        """
        推送 state.json 到远程存储

        Args:
            state: state.json 的完整内容（dict）
        """
        pass

    @abstractmethod
    def pull_state(self) -> dict:
        """
        从远程存储拉取 state.json

        Returns:
            state.json 的完整内容（dict）
        """
        pass

    @abstractmethod
    def push_snapshot(self, snapshot_md: str) -> None:
        """
        推送 AGENTS.md 快照到远程存储

        Args:
            snapshot_md: AGENTS.md 的完整内容
        """
        pass

    @abstractmethod
    def push_artifact(self, local_path: str, remote_path: str) -> None:
        """
        推送 artifact 文件到远程存储

        Args:
            local_path: 本地文件路径
            remote_path: 远程存储路径
        """
        pass

    @abstractmethod
    def pull_artifact(self, remote_path: str, local_path: str) -> None:
        """
        从远程存储拉取 artifact 文件

        Args:
            remote_path: 远程存储路径
            local_path: 本地文件路径
        """
        pass


class LocalBackend(StorageBackend):
    """
    本地文件系统后端（默认）

    零配置，直接使用项目目录作为存储。
    适用于单机开发和测试。
    """

    def __init__(self, orchestra_root: str):
        """
        Args:
            orchestra_root: Orchestra 根目录（通常是项目目录）
        """
        self.orchestra_root = Path(orchestra_root)
        self.state_file = self.orchestra_root / "state.json"
        self.agents_md_file = self.orchestra_root / "AGENTS.md"
        self.artifacts_dir = self.orchestra_root / "artifacts"

        # 确保目录存在
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"LocalBackend initialized at {self.orchestra_root}")

    def push_state(self, state: dict) -> None:
        """
        推送 state.json（本地后端直接写入文件）

        Args:
            state: state.json 的完整内容
        """
        try:
            self.state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
            logger.debug(f"Pushed state.json to {self.state_file}")
        except Exception as e:
            logger.error(f"Failed to push state.json: {e}")
            raise

    def pull_state(self) -> dict:
        """
        拉取 state.json（本地后端直接读取文件）

        Returns:
            state.json 的完整内容
        """
        try:
            if not self.state_file.exists():
                logger.warning(f"state.json not found at {self.state_file}")
                return {}

            content = self.state_file.read_text(encoding="utf-8")
            return json.loads(content)
        except Exception as e:
            logger.error(f"Failed to pull state.json: {e}")
            raise

    def push_snapshot(self, snapshot_md: str) -> None:
        """
        推送 AGENTS.md 快照（本地后端直接写入文件）

        Args:
            snapshot_md: AGENTS.md 的完整内容
        """
        try:
            self.agents_md_file.write_text(snapshot_md, encoding="utf-8")
            logger.debug(f"Pushed AGENTS.md snapshot to {self.agents_md_file}")
        except Exception as e:
            logger.error(f"Failed to push AGENTS.md snapshot: {e}")
            raise

    def push_artifact(self, local_path: str, remote_path: str) -> None:
        """
        推送 artifact 文件（本地后端直接复制文件）

        Args:
            local_path: 本地文件路径
            remote_path: 远程存储路径（相对于 artifacts_dir）
        """
        try:
            src = Path(local_path)
            dst = self.artifacts_dir / remote_path

            if not src.exists():
                logger.warning(f"Source artifact not found: {src}")
                return

            # 确保目标目录存在
            dst.parent.mkdir(parents=True, exist_ok=True)

            # 复制文件
            shutil.copy2(src, dst)
            logger.debug(f"Pushed artifact {src} -> {dst}")
        except Exception as e:
            logger.error(f"Failed to push artifact: {e}")
            raise

    def pull_artifact(self, remote_path: str, local_path: str) -> None:
        """
        拉取 artifact 文件（本地后端直接复制文件）

        Args:
            remote_path: 远程存储路径（相对于 artifacts_dir）
            local_path: 本地文件路径
        """
        try:
            src = self.artifacts_dir / remote_path
            dst = Path(local_path)

            if not src.exists():
                logger.warning(f"Remote artifact not found: {src}")
                return

            # 确保目标目录存在
            dst.parent.mkdir(parents=True, exist_ok=True)

            # 复制文件
            shutil.copy2(src, dst)
            logger.debug(f"Pulled artifact {src} -> {dst}")
        except Exception as e:
            logger.error(f"Failed to pull artifact: {e}")
            raise


class BoxBackend(StorageBackend):
    """
    Box 云存储后端（可选）

    需要配置 Box API credentials。
    适用于团队协作和云端同步。
    """

    def __init__(self, orchestra_root: str, box_config: Optional[dict] = None):
        """
        Args:
            orchestra_root: Orchestra 根目录
            box_config: Box API 配置（client_id, client_secret, access_token 等）
        """
        self.orchestra_root = Path(orchestra_root)
        self.box_config = box_config or {}

        logger.warning("BoxBackend is not implemented yet. Using LocalBackend fallback.")
        self._fallback = LocalBackend(orchestra_root)

    def push_state(self, state: dict) -> None:
        """推送 state.json 到 Box（未实现，使用 LocalBackend fallback）"""
        self._fallback.push_state(state)

    def pull_state(self) -> dict:
        """从 Box 拉取 state.json（未实现，使用 LocalBackend fallback）"""
        return self._fallback.pull_state()

    def push_snapshot(self, snapshot_md: str) -> None:
        """推送 AGENTS.md 到 Box（未实现，使用 LocalBackend fallback）"""
        self._fallback.push_snapshot(snapshot_md)

    def push_artifact(self, local_path: str, remote_path: str) -> None:
        """推送 artifact 到 Box（未实现，使用 LocalBackend fallback）"""
        self._fallback.push_artifact(local_path, remote_path)

    def pull_artifact(self, remote_path: str, local_path: str) -> None:
        """从 Box 拉取 artifact（未实现，使用 LocalBackend fallback）"""
        self._fallback.pull_artifact(remote_path, local_path)


class GitBackend(StorageBackend):
    """
    Git 版本控制后端（可选）

    使用 Git 作为存储后端，支持版本历史和分支管理。
    适用于需要版本追溯的场景。
    """

    def __init__(self, orchestra_root: str, git_config: Optional[dict] = None):
        """
        Args:
            orchestra_root: Orchestra 根目录（必须是 Git 仓库）
            git_config: Git 配置（remote, branch 等）
        """
        self.orchestra_root = Path(orchestra_root)
        self.git_config = git_config or {}

        logger.warning("GitBackend is not implemented yet. Using LocalBackend fallback.")
        self._fallback = LocalBackend(orchestra_root)

    def push_state(self, state: dict) -> None:
        """推送 state.json 到 Git（未实现，使用 LocalBackend fallback）"""
        self._fallback.push_state(state)

    def pull_state(self) -> dict:
        """从 Git 拉取 state.json（未实现，使用 LocalBackend fallback）"""
        return self._fallback.pull_state()

    def push_snapshot(self, snapshot_md: str) -> None:
        """推送 AGENTS.md 到 Git（未实现，使用 LocalBackend fallback）"""
        self._fallback.push_snapshot(snapshot_md)

    def push_artifact(self, local_path: str, remote_path: str) -> None:
        """推送 artifact 到 Git（未实现，使用 LocalBackend fallback）"""
        self._fallback.push_artifact(local_path, remote_path)

    def pull_artifact(self, remote_path: str, local_path: str) -> None:
        """从 Git 拉取 artifact（未实现，使用 LocalBackend fallback）"""
        self._fallback.pull_artifact(remote_path, local_path)
