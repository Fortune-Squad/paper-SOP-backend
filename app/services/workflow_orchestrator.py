"""
Workflow Orchestrator

按 YAML 定义执行工作流，支持状态转换和事件触发

v6.0 NEW: YAML-driven workflow execution
"""
import logging
import yaml
from typing import Dict, Any, List, Optional, Callable
from pathlib import Path
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class WorkflowStatus(str, Enum):
    """工作流状态"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StateTransition:
    """状态转换"""

    def __init__(
        self,
        from_state: str,
        to_state: str,
        condition: Optional[str] = None,
        action: Optional[str] = None
    ):
        """
        初始化状态转换

        Args:
            from_state: 源状态
            to_state: 目标状态
            condition: 转换条件（可选）
            action: 转换动作（可选）
        """
        self.from_state = from_state
        self.to_state = to_state
        self.condition = condition
        self.action = action


class WorkflowState:
    """工作流状态"""

    def __init__(
        self,
        state_id: str,
        state_type: str,
        description: str,
        actions: List[str] = None,
        transitions: List[StateTransition] = None
    ):
        """
        初始化工作流状态

        Args:
            state_id: 状态 ID
            state_type: 状态类型（start/task/decision/end）
            description: 状态描述
            actions: 状态动作列表
            transitions: 状态转换列表
        """
        self.state_id = state_id
        self.state_type = state_type
        self.description = description
        self.actions = actions or []
        self.transitions = transitions or []


class WorkflowDefinition:
    """工作流定义"""

    def __init__(
        self,
        workflow_id: str,
        workflow_name: str,
        version: str,
        states: Dict[str, WorkflowState],
        initial_state: str,
        metadata: Dict[str, Any] = None
    ):
        """
        初始化工作流定义

        Args:
            workflow_id: 工作流 ID
            workflow_name: 工作流名称
            version: 版本号
            states: 状态字典
            initial_state: 初始状态
            metadata: 元数据
        """
        self.workflow_id = workflow_id
        self.workflow_name = workflow_name
        self.version = version
        self.states = states
        self.initial_state = initial_state
        self.metadata = metadata or {}

    @classmethod
    def from_yaml(cls, yaml_path: Path) -> "WorkflowDefinition":
        """
        从 YAML 文件加载工作流定义

        Args:
            yaml_path: YAML 文件路径

        Returns:
            WorkflowDefinition: 工作流定义
        """
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        # 解析状态
        states = {}
        for state_id, state_data in data.get('states', {}).items():
            # 解析转换
            transitions = []
            for trans_data in state_data.get('transitions', []):
                transitions.append(StateTransition(
                    from_state=state_id,
                    to_state=trans_data['to'],
                    condition=trans_data.get('condition'),
                    action=trans_data.get('action')
                ))

            states[state_id] = WorkflowState(
                state_id=state_id,
                state_type=state_data.get('type', 'task'),
                description=state_data.get('description', ''),
                actions=state_data.get('actions', []),
                transitions=transitions
            )

        return cls(
            workflow_id=data['workflow_id'],
            workflow_name=data['workflow_name'],
            version=data['version'],
            states=states,
            initial_state=data['initial_state'],
            metadata=data.get('metadata', {})
        )


class WorkflowInstance:
    """工作流实例"""

    def __init__(
        self,
        instance_id: str,
        workflow_def: WorkflowDefinition,
        project_id: str
    ):
        """
        初始化工作流实例

        Args:
            instance_id: 实例 ID
            workflow_def: 工作流定义
            project_id: 项目 ID
        """
        self.instance_id = instance_id
        self.workflow_def = workflow_def
        self.project_id = project_id
        self.current_state = workflow_def.initial_state
        self.status = WorkflowStatus.PENDING
        self.context = {}
        self.history = []
        self.created_at = datetime.now()
        self.updated_at = datetime.now()

    def transition_to(self, new_state: str, metadata: Dict[str, Any] = None):
        """
        转换到新状态

        Args:
            new_state: 新状态 ID
            metadata: 转换元数据
        """
        old_state = self.current_state

        # 记录历史
        self.history.append({
            'from_state': old_state,
            'to_state': new_state,
            'timestamp': datetime.now().isoformat(),
            'metadata': metadata or {}
        })

        # 更新状态
        self.current_state = new_state
        self.updated_at = datetime.now()

        logger.info(f"Workflow {self.instance_id} transitioned: {old_state} -> {new_state}")

    def update_context(self, key: str, value: Any):
        """
        更新上下文

        Args:
            key: 键
            value: 值
        """
        self.context[key] = value
        self.updated_at = datetime.now()

    def get_current_state_def(self) -> Optional[WorkflowState]:
        """获取当前状态定义"""
        return self.workflow_def.states.get(self.current_state)

    def is_terminal_state(self) -> bool:
        """检查是否为终止状态"""
        state_def = self.get_current_state_def()
        return state_def and state_def.state_type == 'end'


class WorkflowOrchestrator:
    """
    工作流编排器

    按 YAML 定义执行工作流
    """

    def __init__(self):
        """初始化编排器"""
        self.workflows: Dict[str, WorkflowDefinition] = {}
        self.instances: Dict[str, WorkflowInstance] = {}
        self.action_handlers: Dict[str, Callable] = {}

    def register_workflow(self, workflow_def: WorkflowDefinition):
        """
        注册工作流定义

        Args:
            workflow_def: 工作流定义
        """
        self.workflows[workflow_def.workflow_id] = workflow_def
        logger.info(f"Registered workflow: {workflow_def.workflow_id}")

    def load_workflow_from_yaml(self, yaml_path: Path):
        """
        从 YAML 文件加载并注册工作流

        Args:
            yaml_path: YAML 文件路径
        """
        workflow_def = WorkflowDefinition.from_yaml(yaml_path)
        self.register_workflow(workflow_def)

    def register_action_handler(self, action_name: str, handler: Callable):
        """
        注册动作处理器

        Args:
            action_name: 动作名称
            handler: 处理器函数
        """
        self.action_handlers[action_name] = handler
        logger.info(f"Registered action handler: {action_name}")

    def create_instance(
        self,
        workflow_id: str,
        project_id: str,
        instance_id: Optional[str] = None
    ) -> WorkflowInstance:
        """
        创建工作流实例

        Args:
            workflow_id: 工作流 ID
            project_id: 项目 ID
            instance_id: 实例 ID（可选）

        Returns:
            WorkflowInstance: 工作流实例
        """
        if workflow_id not in self.workflows:
            raise ValueError(f"Workflow not found: {workflow_id}")

        workflow_def = self.workflows[workflow_id]

        if instance_id is None:
            instance_id = f"{workflow_id}_{project_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        instance = WorkflowInstance(
            instance_id=instance_id,
            workflow_def=workflow_def,
            project_id=project_id
        )

        self.instances[instance_id] = instance
        logger.info(f"Created workflow instance: {instance_id}")

        return instance

    async def execute_action(
        self,
        instance: WorkflowInstance,
        action_name: str
    ) -> Dict[str, Any]:
        """
        执行动作

        Args:
            instance: 工作流实例
            action_name: 动作名称

        Returns:
            Dict[str, Any]: 动作执行结果
        """
        if action_name not in self.action_handlers:
            logger.warning(f"No handler for action: {action_name}")
            return {"status": "skipped", "reason": "no_handler"}

        handler = self.action_handlers[action_name]

        try:
            result = await handler(instance)
            logger.info(f"Action executed: {action_name} -> {result.get('status')}")
            return result
        except Exception as e:
            logger.error(f"Action failed: {action_name} -> {e}")
            return {"status": "failed", "error": str(e)}

    async def execute_state(self, instance: WorkflowInstance) -> bool:
        """
        执行当前状态

        Args:
            instance: 工作流实例

        Returns:
            bool: 是否成功
        """
        state_def = instance.get_current_state_def()
        if not state_def:
            logger.error(f"State not found: {instance.current_state}")
            return False

        logger.info(f"Executing state: {state_def.state_id} ({state_def.state_type})")

        # 执行状态动作
        for action_name in state_def.actions:
            result = await self.execute_action(instance, action_name)
            instance.update_context(f"action_{action_name}_result", result)

            if result.get('status') == 'failed':
                instance.status = WorkflowStatus.FAILED
                return False

        return True

    async def transition(
        self,
        instance: WorkflowInstance,
        target_state: Optional[str] = None
    ) -> bool:
        """
        执行状态转换

        Args:
            instance: 工作流实例
            target_state: 目标状态（可选，如果不指定则自动选择）

        Returns:
            bool: 是否成功
        """
        state_def = instance.get_current_state_def()
        if not state_def:
            return False

        # 如果指定了目标状态，直接转换
        if target_state:
            instance.transition_to(target_state)
            return True

        # 否则，根据转换规则自动选择
        for transition in state_def.transitions:
            # 简化版：暂时不检查条件，直接转换到第一个目标
            instance.transition_to(transition.to_state)
            return True

        # 没有转换规则
        logger.warning(f"No transitions defined for state: {state_def.state_id}")
        return False

    async def run(self, instance_id: str, max_steps: int = 100) -> WorkflowInstance:
        """
        运行工作流实例

        Args:
            instance_id: 实例 ID
            max_steps: 最大步数（防止无限循环）

        Returns:
            WorkflowInstance: 工作流实例
        """
        if instance_id not in self.instances:
            raise ValueError(f"Instance not found: {instance_id}")

        instance = self.instances[instance_id]
        instance.status = WorkflowStatus.RUNNING

        logger.info(f"Running workflow instance: {instance_id}")

        steps = 0
        while not instance.is_terminal_state() and steps < max_steps:
            # 执行当前状态
            success = await self.execute_state(instance)
            if not success:
                instance.status = WorkflowStatus.FAILED
                break

            # 转换到下一个状态
            success = await self.transition(instance)
            if not success:
                # 没有更多转换，停止
                break

            steps += 1

        # 检查是否完成
        if instance.is_terminal_state():
            instance.status = WorkflowStatus.COMPLETED
            logger.info(f"Workflow completed: {instance_id}")
        elif steps >= max_steps:
            instance.status = WorkflowStatus.FAILED
            logger.error(f"Workflow exceeded max steps: {instance_id}")
        else:
            logger.warning(f"Workflow stopped: {instance_id}")

        return instance

    def get_instance(self, instance_id: str) -> Optional[WorkflowInstance]:
        """获取工作流实例"""
        return self.instances.get(instance_id)

    def list_workflows(self) -> List[str]:
        """列出所有已注册的工作流"""
        return list(self.workflows.keys())

    def list_instances(self) -> List[str]:
        """列出所有工作流实例"""
        return list(self.instances.keys())


# 全局 Orchestrator 实例
_orchestrator_instance = None


def get_workflow_orchestrator() -> WorkflowOrchestrator:
    """
    获取全局 Workflow Orchestrator 实例

    Returns:
        WorkflowOrchestrator: Orchestrator 实例
    """
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = WorkflowOrchestrator()
    return _orchestrator_instance
