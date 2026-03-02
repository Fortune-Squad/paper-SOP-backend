"""
Readiness Assessor
v1.2 DevSpec §5.9, §9.5 - ChatGPT Readiness Assessment

两层 Gate 设计:
- 执行层 Gate (Claude 自动跑): 验证器通过? 代码能跑? 维度对?
- 战略层 RA (ChatGPT 裁决): 物理上对吗? 覆盖了关键 case 吗? 北极星对齐?

判定: ADVANCE → freeze / POLISH → freeze + TODO / BLOCK → HIL ticket
"""
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from enum import Enum

logger = logging.getLogger(__name__)


class RAVerdict(str, Enum):
    """Readiness Assessment 判定结果"""
    ADVANCE = "ADVANCE"
    POLISH = "POLISH"
    BLOCK = "BLOCK"
    PENDING = "PENDING"


class RAResult(BaseModel):
    """Readiness Assessment 结果"""
    verdict: RAVerdict
    reasoning: str = ""
    north_star_alignment: str = ""
    missing_pieces: List[str] = Field(default_factory=list)
    polish_suggestions: List[str] = Field(default_factory=list)
    next_wp_readiness: str = ""
    assessed_at: datetime = Field(default_factory=datetime.now)
    assessed_by: str = "chatgpt"


RA_PROMPT_TEMPLATE = """# Readiness Assessment: {wp_id}
# Model: ChatGPT

## 你的角色
你是 ChatGPT，担任战略层审批官。Gate（机械验证）已通过。你现在判断：
1. 物理上对吗？覆盖了关键 case 吗？
2. 对北极星的推进够吗？有没有遗漏？
3. 下一个 WP 是否可以安全开始？

## 当前状态（来自 AGENTS.md）
{agents_md_content}

## 项目教训（来自 MEMORY.md）
{memory_md_content}

## Gate 结果摘要
- Gate verdict: PASS
- 通过的标准：{passed_criteria}
- Artifacts 摘要：{artifacts_summary}

## 你的输出格式（必须严格遵守）
```json
{{
  "verdict": "ADVANCE | POLISH | BLOCK",
  "reasoning": "简述判断依据（<= 200 words）",
  "north_star_alignment": "当前产出对北极星的贡献（1-2 句）",
  "missing_pieces": ["如果 BLOCK，列出缺什么"],
  "polish_suggestions": ["如果 POLISH，列出可改进点（不阻断推进）"],
  "next_wp_readiness": "下一个 WP 是否可以开始？依赖是否满足？"
}}
```

## 判断标准
- **ADVANCE**：物理正确、覆盖充分、可安全推进
- **POLISH**：物理正确但有改进空间，可推进但标记 TODO
- **BLOCK**：存在物理错误/关键遗漏/北极星偏离，需要返工

## 禁止事项
- 不要给打分（我们用 binary 判断）
- 不要重复 Gate 已经检查的机械标准
- 关注 Gate 无法检查的东西：物理直觉、覆盖完整性、战略对齐
"""


class ReadinessAssessor:
    """
    ChatGPT Readiness Assessment 管理器
    
    功能:
    - 生成 RA prompt（包含 AGENTS.md + MEMORY.md + Gate 结果）
    - 解析 ChatGPT 返回的 RA JSON
    - 执行状态转移 (ADVANCE/POLISH/BLOCK)
    - 支持人类 override BLOCK
    - 保存 RA 结果到 gate_results/ra_{timestamp}.json
    """
    
    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
    
    def generate_ra_prompt(
        self,
        wp_id: str,
        agents_md_content: str,
        memory_md_content: str,
        passed_criteria: str,
        artifacts_summary: str
    ) -> str:
        """
        生成 RA prompt
        
        Args:
            wp_id: Work Package ID
            agents_md_content: AGENTS.md 完整内容
            memory_md_content: MEMORY.md 相关条目
            passed_criteria: 通过的 gate 标准
            artifacts_summary: Artifacts 摘要
            
        Returns:
            渲染后的 RA prompt
        """
        return RA_PROMPT_TEMPLATE.format(
            wp_id=wp_id,
            agents_md_content=agents_md_content,
            memory_md_content=memory_md_content,
            passed_criteria=passed_criteria,
            artifacts_summary=artifacts_summary
        )
    
    def parse_result(self, raw_response: str) -> RAResult:
        """
        解析 ChatGPT 返回的 RA JSON
        
        Args:
            raw_response: ChatGPT 的原始响应文本
            
        Returns:
            RAResult 对象
        """
        try:
            # 尝试从响应中提取 JSON
            json_str = self._extract_json(raw_response)
            data = json.loads(json_str)
            
            verdict_str = data.get("verdict", "BLOCK").upper()
            try:
                verdict = RAVerdict(verdict_str)
            except ValueError:
                logger.warning(f"Invalid RA verdict: {verdict_str}, defaulting to BLOCK")
                verdict = RAVerdict.BLOCK
            
            return RAResult(
                verdict=verdict,
                reasoning=data.get("reasoning", ""),
                north_star_alignment=data.get("north_star_alignment", ""),
                missing_pieces=data.get("missing_pieces", []),
                polish_suggestions=data.get("polish_suggestions", []),
                next_wp_readiness=data.get("next_wp_readiness", ""),
                assessed_by="chatgpt"
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse RA result: {e}")
            return RAResult(
                verdict=RAVerdict.BLOCK,
                reasoning=f"Failed to parse RA response: {e}",
                assessed_by="system_error"
            )
    
    def save_result(self, wp_id: str, result: RAResult) -> str:
        """
        保存 RA 结果到文件
        
        Args:
            wp_id: Work Package ID
            result: RA 结果
            
        Returns:
            保存的文件路径
        """
        wp_dir = self.project_path / "execution" / wp_id / "gate_results"
        wp_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_path = wp_dir / f"ra_{timestamp}.json"
        
        result_data = result.model_dump()
        result_data["assessed_at"] = result.assessed_at.isoformat()
        
        result_path.write_text(
            json.dumps(result_data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        
        logger.info(f"Saved RA result for {wp_id}: {result.verdict.value} -> {result_path}")
        return str(result_path)
    
    def load_latest_result(self, wp_id: str) -> Optional[RAResult]:
        """加载最新的 RA 结果"""
        wp_dir = self.project_path / "execution" / wp_id / "gate_results"
        if not wp_dir.exists():
            return None
        
        ra_files = sorted(wp_dir.glob("ra_*.json"), reverse=True)
        if not ra_files:
            return None
        
        try:
            data = json.loads(ra_files[0].read_text(encoding="utf-8"))
            return RAResult(**data)
        except Exception as e:
            logger.error(f"Failed to load RA result: {e}")
            return None
    
    def create_override(self, wp_id: str, original_verdict: RAVerdict, override_reason: str) -> RAResult:
        """
        人类 override BLOCK 判定
        
        Args:
            wp_id: Work Package ID
            original_verdict: 原始判定
            override_reason: Override 原因
            
        Returns:
            新的 RAResult (ADVANCE)
        """
        result = RAResult(
            verdict=RAVerdict.ADVANCE,
            reasoning=f"Human override of {original_verdict.value}: {override_reason}",
            assessed_by="human_override"
        )
        
        self.save_result(wp_id, result)
        logger.info(f"Human override for {wp_id}: {original_verdict.value} -> ADVANCE")
        return result
    
    def get_ra_status(self) -> Dict[str, Any]:
        """获取所有 WP 的 RA 状态"""
        execution_dir = self.project_path / "execution"
        if not execution_dir.exists():
            return {}
        
        status = {}
        for wp_dir in execution_dir.iterdir():
            if not wp_dir.is_dir() or not wp_dir.name.startswith("wp"):
                continue
            
            result = self.load_latest_result(wp_dir.name)
            if result:
                status[wp_dir.name] = {
                    "verdict": result.verdict.value,
                    "reasoning": result.reasoning,
                    "assessed_at": result.assessed_at.isoformat(),
                    "assessed_by": result.assessed_by
                }
            else:
                status[wp_dir.name] = {"verdict": "NOT_ASSESSED"}
        
        return status
    
    def _extract_json(self, text: str) -> str:
        """从文本中提取 JSON 块"""
        # 尝试找 ```json ... ``` 块
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            return text[start:end].strip()
        
        # 尝试找 { ... } 块
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return text[start:end]
        
        return text
