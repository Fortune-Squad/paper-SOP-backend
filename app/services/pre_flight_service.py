"""
Pre-flight Check Service
v7.1 S2-1: 参数声明 + 确认级别分类 + AI 审阅

在 subtask 执行前验证参数来源和合理性。
"""
import logging
from typing import List, Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ParameterSource(str, Enum):
    """参数来源"""
    FROM_SPEC = "from_spec"        # 来自冻结的 spec 文档
    FROM_REFERENCE = "from_reference"  # 来自参考文献
    DEFAULT = "default"            # 使用默认值
    COMPUTED = "computed"          # 计算得出


class ConfirmLevel(str, Enum):
    """确认级别"""
    AUTO_PASS = "auto_pass"        # FROM_SPEC / FROM_REFERENCE → 自动通过
    AI_REVIEW = "ai_review"        # DEFAULT → AI 审阅
    HUMAN_REVIEW = "human_review"  # 无来源或高风险 → 人工审阅


class ParameterDeclaration(BaseModel):
    """参数声明"""
    name: str = Field(..., description="参数名称")
    value: str = Field(..., description="参数值")
    source: ParameterSource = Field(..., description="参数来源")
    justification: str = Field(default="", description="使用理由")
    confirm_level: ConfirmLevel = Field(default=ConfirmLevel.AI_REVIEW)


class PreFlightResult(BaseModel):
    """Pre-flight 检查结果"""
    passed: bool = Field(default=False)
    declarations: List[ParameterDeclaration] = Field(default_factory=list)
    ai_review_results: Dict[str, str] = Field(default_factory=dict)
    blocked_params: List[str] = Field(default_factory=list)
    revised_params: Dict[str, str] = Field(default_factory=dict)

class PreFlightService:
    """
    Pre-flight 检查服务

    在 subtask 执行前:
    1. 让 Claude 输出参数声明
    2. 根据 source 分类确认级别
    3. AI_REVIEW → ChatGPT 审阅 DEFAULT 参数
    4. HUMAN_REVIEW → 创建 HIL ticket
    """

    def __init__(self, chatgpt_client=None):
        self.chatgpt_client = chatgpt_client

    def classify_confirm_level(self, source: ParameterSource) -> ConfirmLevel:
        """根据参数来源分类确认级别"""
        if source in (ParameterSource.FROM_SPEC, ParameterSource.FROM_REFERENCE):
            return ConfirmLevel.AUTO_PASS
        elif source == ParameterSource.DEFAULT:
            return ConfirmLevel.AI_REVIEW
        else:
            return ConfirmLevel.AI_REVIEW

    async def request_parameter_declaration(
        self, subtask_spec: str, context: str = ""
    ) -> List[ParameterDeclaration]:
        """
        让 AI 输出参数声明

        Args:
            subtask_spec: subtask 规格
            context: 上下文信息

        Returns:
            List[ParameterDeclaration]
        """
        if not self.chatgpt_client:
            return []

        from app.prompts.step3_prompts import PREFLIGHT_PARAMETER_DECLARATION_PROMPT
        prompt = PREFLIGHT_PARAMETER_DECLARATION_PROMPT.format(
            subtask_spec=subtask_spec, context=context,
        )

        try:
            response = await self.chatgpt_client.chat(
                system_prompt="You are a parameter auditor. Extract and classify all parameters.",
                user_prompt=prompt,
            )
            return self._parse_declarations(response)
        except Exception as e:
            logger.warning(f"Parameter declaration request failed: {e}")
            return []

    async def run_ai_review(
        self, declarations: List[ParameterDeclaration]
    ) -> Dict[str, str]:
        """
        ChatGPT 审阅 DEFAULT 参数

        Returns:
            Dict[param_name, "ACCEPT" | "REVISE:new_value"]
        """
        if not self.chatgpt_client:
            return {}

        default_params = [d for d in declarations if d.confirm_level == ConfirmLevel.AI_REVIEW]
        if not default_params:
            return {}

        params_text = "\n".join(
            f"- {d.name} = {d.value} (source: {d.source.value}, justification: {d.justification})"
            for d in default_params
        )

        prompt = f"""Review these DEFAULT parameters for a research subtask.
For each parameter, respond with ACCEPT or REVISE:new_value.

Parameters:
{params_text}

Output format (one per line):
param_name: ACCEPT
param_name: REVISE:new_value
"""
        try:
            response = await self.chatgpt_client.chat(
                system_prompt="You are a research parameter reviewer.",
                user_prompt=prompt,
            )
            results = {}
            for line in response.strip().split("\n"):
                if ":" in line:
                    parts = line.split(":", 1)
                    name = parts[0].strip()
                    verdict = parts[1].strip()
                    results[name] = verdict
            return results
        except Exception as e:
            logger.warning(f"AI review failed: {e}")
            return {}

    async def run_full_check(
        self, subtask_spec: str, context: str = ""
    ) -> PreFlightResult:
        """
        完整 Pre-flight 流程

        Returns:
            PreFlightResult
        """
        result = PreFlightResult()

        # v7.1: Inject MEMORY.md error patterns into context
        try:
            from app.services.prompt_pack_compiler import inject_memory_md
            # Extract project_id from context if available
            import re
            pid_match = re.search(r'project[_\s]?id[:\s]+(\S+)', context, re.IGNORECASE)
            if pid_match:
                memory_content = inject_memory_md(pid_match.group(1), tags=["numerical", "workflow", "boundary"])
                if memory_content and memory_content != "(MEMORY.md empty)":
                    context += f"\n\n## Known Error Patterns (from MEMORY.md)\n{memory_content}\n"
        except Exception as mem_err:
            logger.warning(f"Pre-flight memory injection failed (non-blocking): {mem_err}")

        # Step 1: Get parameter declarations
        declarations = await self.request_parameter_declaration(subtask_spec, context)
        if not declarations:
            result.passed = True  # No params to check
            return result

        # Step 2: Classify confirm levels
        for decl in declarations:
            decl.confirm_level = self.classify_confirm_level(decl.source)
        result.declarations = declarations

        # Step 3: AI review for DEFAULT params
        ai_results = await self.run_ai_review(declarations)
        result.ai_review_results = ai_results

        # Step 4: Process results
        blocked = []
        revised = {}
        for decl in declarations:
            if decl.confirm_level == ConfirmLevel.HUMAN_REVIEW:
                blocked.append(decl.name)
            elif decl.name in ai_results:
                verdict = ai_results[decl.name]
                if verdict.startswith("REVISE:"):
                    revised[decl.name] = verdict[7:]

        result.blocked_params = blocked
        result.revised_params = revised
        result.passed = len(blocked) == 0

        return result

    def _parse_declarations(self, response: str) -> List[ParameterDeclaration]:
        """解析 AI 返回的参数声明"""
        declarations = []
        import re
        # Parse lines like: - param_name = value (source: from_spec, justification: ...)
        pattern = r'-\s*(\w+)\s*=\s*(.+?)\s*\(source:\s*(\w+)'
        for match in re.finditer(pattern, response):
            name = match.group(1)
            value = match.group(2).strip()
            source_str = match.group(3).strip()
            try:
                source = ParameterSource(source_str)
            except ValueError:
                source = ParameterSource.DEFAULT
            declarations.append(ParameterDeclaration(
                name=name, value=value, source=source,
            ))
        return declarations
