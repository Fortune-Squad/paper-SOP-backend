"""
Git 管理器
处理项目的 Git 版本控制操作
"""
from git import Repo, GitCommandError
from pathlib import Path
from typing import Optional
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class GitManager:
    """Git 管理器类"""

    def __init__(self, base_path: Optional[str] = None):
        """
        初始化 Git 管理器

        Args:
            base_path: 基础路径（项目根目录）
        """
        self.base_path = Path(base_path or settings.projects_path)

    def get_project_path(self, project_id: str) -> Path:
        """获取项目目录路径"""
        return self.base_path / project_id

    def init_repo(self, project_id: str) -> Repo:
        """
        初始化 Git 仓库

        Args:
            project_id: 项目 ID

        Returns:
            Repo: Git 仓库对象
        """
        try:
            project_path = self.get_project_path(project_id)
            project_path.mkdir(parents=True, exist_ok=True)

            # 检查是否已经是 Git 仓库
            try:
                repo = Repo(project_path)
                logger.info(f"Git repo already exists at {project_path}")
                return repo
            except:
                # 初始化新仓库
                repo = Repo.init(project_path)
                logger.info(f"Initialized Git repo at {project_path}")

                # 创建初始 commit
                self._create_gitignore(project_path)
                repo.index.add([".gitignore"])
                repo.index.commit("Initial commit")

                return repo

        except Exception as e:
            logger.error(f"Failed to initialize Git repo: {e}")
            raise

    def _create_gitignore(self, project_path: Path):
        """创建 .gitignore 文件"""
        gitignore_content = """# Python
__pycache__/
*.py[cod]
*.so

# Logs
logs/
*.log

# Vector DB
vector_db/

# Temporary files
*.tmp
*.bak
.cache/
"""
        gitignore_path = project_path / ".gitignore"
        gitignore_path.write_text(gitignore_content)

    async def commit(self, project_id: str, message: str, files: Optional[list] = None):
        """
        提交更改

        Args:
            project_id: 项目 ID
            message: 提交信息
            files: 要提交的文件列表（相对路径），如果为 None 则提交所有更改
        """
        try:
            project_path = self.get_project_path(project_id)
            repo = Repo(project_path)

            # 添加文件到暂存区
            if files:
                repo.index.add(files)
            else:
                # 添加所有更改的文件
                repo.git.add(A=True)

            # 检查是否有更改
            if repo.is_dirty() or repo.untracked_files:
                # 提交
                repo.index.commit(message)
                logger.info(f"Committed changes: {message}")
            else:
                logger.info("No changes to commit")

        except GitCommandError as e:
            logger.error(f"Git command error: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to commit: {e}")
            raise

    async def get_commit_history(self, project_id: str, max_count: int = 10) -> list:
        """
        获取提交历史

        Args:
            project_id: 项目 ID
            max_count: 最大返回数量

        Returns:
            list: 提交历史列表
        """
        try:
            project_path = self.get_project_path(project_id)
            repo = Repo(project_path)

            commits = []
            for commit in repo.iter_commits(max_count=max_count):
                commits.append({
                    "sha": commit.hexsha[:7],
                    "message": commit.message.strip(),
                    "author": str(commit.author),
                    "date": commit.committed_datetime.isoformat(),
                    "files": list(commit.stats.files.keys())
                })

            return commits

        except Exception as e:
            logger.error(f"Failed to get commit history: {e}")
            return []

    async def get_file_history(self, project_id: str, file_path: str) -> list:
        """
        获取文件的提交历史

        Args:
            project_id: 项目 ID
            file_path: 文件路径（相对路径）

        Returns:
            list: 文件的提交历史
        """
        try:
            project_path = self.get_project_path(project_id)
            repo = Repo(project_path)

            commits = []
            for commit in repo.iter_commits(paths=file_path):
                commits.append({
                    "sha": commit.hexsha[:7],
                    "message": commit.message.strip(),
                    "author": str(commit.author),
                    "date": commit.committed_datetime.isoformat()
                })

            return commits

        except Exception as e:
            logger.error(f"Failed to get file history: {e}")
            return []

    async def get_file_at_commit(self, project_id: str, file_path: str, commit_sha: str) -> Optional[str]:
        """
        获取指定提交时的文件内容

        Args:
            project_id: 项目 ID
            file_path: 文件路径（相对路径）
            commit_sha: 提交 SHA

        Returns:
            Optional[str]: 文件内容，如果不存在则返回 None
        """
        try:
            project_path = self.get_project_path(project_id)
            repo = Repo(project_path)

            commit = repo.commit(commit_sha)
            blob = commit.tree / file_path

            return blob.data_stream.read().decode('utf-8')

        except Exception as e:
            logger.error(f"Failed to get file at commit: {e}")
            return None

    def get_status(self, project_id: str) -> dict:
        """
        获取 Git 状态

        Args:
            project_id: 项目 ID

        Returns:
            dict: Git 状态信息
        """
        try:
            project_path = self.get_project_path(project_id)
            repo = Repo(project_path)

            return {
                "is_dirty": repo.is_dirty(),
                "untracked_files": repo.untracked_files,
                "modified_files": [item.a_path for item in repo.index.diff(None)],
                "staged_files": [item.a_path for item in repo.index.diff("HEAD")],
                "current_branch": repo.active_branch.name if repo.head.is_valid() else None
            }

        except Exception as e:
            logger.error(f"Failed to get Git status: {e}")
            return {}


# 全局 Git 管理器实例
_git_manager_instance = None


def get_git_manager() -> GitManager:
    """获取全局 Git 管理器实例"""
    global _git_manager_instance
    if _git_manager_instance is None:
        _git_manager_instance = GitManager()
    return _git_manager_instance
