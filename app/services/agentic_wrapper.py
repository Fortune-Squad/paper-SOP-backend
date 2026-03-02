"""
Agentic Wrapper for Gemini (v4.0)
Implements Plan → Action → Evidence → Output workflow
"""
import yaml
import re
import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class AgenticWrapper:
    """Agentic Wrapper for Gemini responses with multi-level modes"""

    def __init__(self, config_path: str, mode: str = "full"):
        """
        Initialize Agentic Wrapper with configuration

        Args:
            config_path: Path to Gemini Gem config YAML file
            mode: Wrapper mode - "full" (7 sections), "lite" (3 sections), or "minimal" (1 section)
        """
        self.config = self._load_config(config_path)
        self.enabled = self.config.get("agentic_wrapper", {}).get("enabled", True)
        self.validation = self.config.get("agentic_wrapper", {}).get("validation", {})
        self.system_prompt = self.config.get("system_prompt", "")
        self.mode = mode  # "full", "lite", or "minimal"
        logger.info(f"AgenticWrapper initialized with mode: {mode}")

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load Gemini Gem configuration from YAML file"""
        try:
            config_file = Path(config_path)
            if not config_file.exists():
                logger.warning(f"Gemini Gem config not found at {config_path}, using defaults")
                return self._get_default_config()

            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                logger.info(f"Loaded Gemini Gem config from {config_path}")
                return config
        except Exception as e:
            logger.error(f"Failed to load Gemini Gem config: {e}")
            return self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default Agentic Wrapper configuration"""
        return {
            "agentic_wrapper": {
                "enabled": True,
                "validation": {
                    "require_plan": True,
                    "require_evidence": True,
                    "require_risks": True,  # SOP v4.0
                    "require_verification": True,  # SOP v4.0
                    "min_confidence": 0.7,
                    "min_risks": 5,  # SOP v4.0
                    "min_verification_items": 5,  # SOP v4.0
                    "forbid_placeholder_doi": True,  # SOP v4.0
                    "warn_markdown_codeblock": True  # SOP v4.0
                }
            },
            "system_prompt": """You are a Chief Intelligence Officer and senior academic editor serving as a Research Partner.

CRITICAL: You MUST follow the Agentic Workflow (SOP v4.0):
1. **Plan**: Break down the task into concrete, actionable steps (3-6 steps max)
2. **Actions**: Execute each step with specific, verifiable actions
3. **Evidence**: Cite sources with real DOIs/links (NO placeholders like 10.1109/xxx.2024.1)
4. **Deliverables**: Produce the requested output in structured format (NO wrapping in code blocks)
5. **Risks**: List at least 5 risks, uncertainties, or limitations
6. **Verification**: List at least 5 items that should be manually verified
7. **Confidence**: Provide a confidence score (0.0-1.0) with justification

Always structure your response with these sections:
- ## Plan
- ## Actions Taken
- ## Evidence
- ## Deliverables
- ## Risks
- ## Verification Checklist
- ## Confidence Score

Be thorough, evidence-based, and critical. Challenge assumptions and identify gaps."""
        }

    def wrap_prompt(self, prompt: str, system_prompt: Optional[str] = None, mode: Optional[str] = None) -> str:
        """
        Wrap user prompt with Agentic Wrapper instructions

        Args:
            prompt: Original user prompt
            system_prompt: Optional custom system prompt (overrides config)
            mode: Optional mode override for this call ("full", "lite", "minimal", "meta_tail", "sidecar_meta", or "disabled")

        Returns:
            str: Wrapped prompt with Agentic instructions
        """
        if not self.enabled or mode == "disabled":
            return prompt

        # Use provided mode or fall back to instance mode
        effective_mode = mode if mode else self.mode

        # Route to appropriate wrapper based on mode
        if effective_mode == "meta_tail":  # v4.1: Non-invasive mode
            return self._wrap_meta_tail(prompt, system_prompt)
        elif effective_mode == "sidecar_meta":  # v4.1: Sidecar mode
            return self._wrap_sidecar_meta(prompt, system_prompt)
        elif effective_mode == "lite":
            return self._wrap_lite(prompt, system_prompt)
        elif effective_mode == "minimal":
            return self._wrap_minimal(prompt, system_prompt)
        else:  # "full" or default
            return self._wrap_full(prompt, system_prompt)

    def _wrap_full(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        Full Agentic Wrapper with 7 sections (Plan + Actions + Evidence + Deliverables + Risks + Verification + Confidence)

        Use for: Analysis and reasoning tasks that require complete evidence trail
        - Killer Prior Check
        - Topic Alignment Check
        - Reference QA
        - Red Team Review
        """
        # Use custom system prompt if provided, otherwise use config
        final_system_prompt = system_prompt if system_prompt else self.system_prompt

        wrapped = f"""{final_system_prompt}

---

**User Request:**
{prompt}

---

**CRITICAL: AGENTIC-FIRST / EVIDENCE-FIRST RULES (SOP v4.0):**

1) 先列 Plan（最多 6 步），再执行检索/核验，再输出产物；不要先写结论。
2) 每个关键判断必须给 Evidence（DOI/出版社页面/IEEE Xplore/ArXiv 链接之一）。
3) 不允许占位符 DOI（如 10.1109/xxx.2024.1）；若找不到就标记 UNKNOWN 并降级结论。
4) 输出必须结构化、短句、可被脚本解析；禁止把整篇正文包进 ```markdown``` 代码块。
5) 最后必须给：Risk list（>=5）+ What to verify（>=5）+ Confidence（0-1）。

---

**IMPORTANT: Structure your response EXACTLY as follows:**

## Plan
[Break down the task into 3-6 concrete, actionable steps. Be specific.]

## Actions Taken
[For each step in your plan, describe the specific actions you executed. Include search queries, verification steps, etc.]

## Evidence
[Cite ALL sources with proper references. Format: Title | Venue/Year | DOI/Link | Key Finding]
[CRITICAL: No placeholder DOIs allowed. Use UNKNOWN if DOI not found.]
[Each key claim must have at least one evidence citation.]

## Deliverables
[CRITICAL: This section MUST start with "## Deliverables" header exactly as shown]
[Provide the final output as requested by the user. Use structured format, short sentences.]
[DO NOT wrap the entire deliverable in a markdown code block.]

## Risks
[List at least 5 risks, uncertainties, or limitations of this output]
1. [Risk 1]
2. [Risk 2]
3. [Risk 3]
4. [Risk 4]
5. [Risk 5]

## Verification Checklist
[List at least 5 items that should be manually verified or double-checked]
1. [Verification item 1]
2. [Verification item 2]
3. [Verification item 3]
4. [Verification item 4]
5. [Verification item 5]

## Confidence Score
[Provide a score from 0.0 to 1.0 indicating your confidence in this output, with brief justification]
"""
        return wrapped

    def _wrap_lite(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        Lightweight Agentic Wrapper with 3 sections (Evidence + Deliverables + Confidence)

        Use for: Long-form output tasks that need anti-hallucination but not full reasoning trace
        - Project Intake Card
        - Venue Taste Notes
        - Deep Research Summary
        - Figure-First Story
        - Full Proposal

        Benefits:
        - Reduces prompt overhead by ~75%
        - Still requires evidence (prevents hallucination)
        - Still requires confidence score (quality control)
        - Removes unnecessary Plan/Actions/Risks/Verification
        """
        # Use custom system prompt if provided, otherwise use a lite version
        if system_prompt:
            final_system_prompt = system_prompt
        else:
            final_system_prompt = """You are a Chief Intelligence Officer and senior academic editor serving as a Research Partner.

Your role is to provide thorough, evidence-based output while maintaining high quality standards."""

        wrapped = f"""{final_system_prompt}

---

**User Request:**
{prompt}

---

**CRITICAL: EVIDENCE-FIRST OUTPUT (SOP v4.0 Lite Mode):**

1) 每个关键判断必须给 Evidence（DOI/出版社页面/IEEE Xplore/ArXiv 链接之一）。
2) 不允许占位符 DOI（如 10.1109/xxx.2024.1）；若找不到就标记 UNKNOWN 并降级结论。
3) 输出必须结构化、短句、可被脚本解析；禁止把整篇正文包进 ```markdown``` 代码块。
4) 最后必须给 Confidence Score（0-1）。

---

**IMPORTANT: Structure your response EXACTLY as follows:**

## Evidence
[List key sources and citations with real DOIs/URLs]
[Format: Title | Venue/Year | DOI/Link | Key Finding]
[CRITICAL: No placeholder DOIs allowed. Use UNKNOWN if DOI not found.]

## Deliverables
[CRITICAL: This section MUST contain the COMPLETE output as requested]
[DO NOT truncate, summarize, or provide only examples]
[This section should contain the FULL content with all required sections/parts]
[DO NOT wrap in markdown code blocks]
[Be thorough and detailed - provide the complete deliverable, not a preview]

## Confidence Score
[Provide a confidence score (0.0-1.0) with brief justification]
"""
        return wrapped

    def _wrap_minimal(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        Minimal Agentic Wrapper with 1 section (Deliverables only)

        Use for: Creative tasks that need basic quality control but minimal structure
        - Title/Abstract Candidates
        - Figure/Table List

        Benefits:
        - Minimal overhead
        - Still reminds AI to be evidence-based
        - No complex structure requirements
        """
        # Use custom system prompt if provided, otherwise use a minimal version
        if system_prompt:
            final_system_prompt = system_prompt
        else:
            final_system_prompt = """You are a Chief Intelligence Officer and senior academic editor serving as a Research Partner.

Provide complete, evidence-based output. Avoid placeholders and ensure all claims are supported."""

        wrapped = f"""{final_system_prompt}

---

**User Request:**
{prompt}

---

**IMPORTANT: Provide complete, evidence-based output. Avoid placeholders and ensure all claims are supported.**

## Deliverables
[Complete output as requested]
[DO NOT wrap in markdown code blocks]
"""
        return wrapped

    def _wrap_meta_tail(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        Meta-Tail Agentic Wrapper - Non-invasive mode (v4.1)

        先输出完整的 deliverable（可以是任何格式，包括 YAML front-matter, BibTeX 等），
        然后追加 meta 信息（用明确的分隔符）。

        Use for: Steps with specific output format requirements
        - YAML front-matter
        - BibTeX entries
        - Specific section structures
        - Any format that conflicts with standard wrapper sections

        Benefits:
        - Zero format conflicts (deliverable can be any format)
        - Preserves all wrapper benefits (Evidence, Confidence)
        - Minimal overhead (~15%)
        - Easy to parse with clear delimiters

        Output format:
        ```
        [Complete deliverable with any format]

        <<<META_JSON>>>
        {
          "evidence": [...],
          "confidence_score": 0.85,
          "confidence_justification": "..."
        }
        <<<END_META>>>
        ```
        """
        # Use custom system prompt if provided, otherwise use a meta-tail version
        if system_prompt:
            final_system_prompt = system_prompt
        else:
            final_system_prompt = """You are a Chief Intelligence Officer and senior academic editor serving as a Research Partner.

Provide complete, evidence-based output with quality metadata."""

        wrapped = f"""{final_system_prompt}

---

**User Request:**
{prompt}

---

**CRITICAL: TWO-PART OUTPUT FORMAT (SOP v4.1 Meta-Tail Mode):**

1) First, output the COMPLETE deliverable as requested:
   - Use ANY required format (YAML front-matter, BibTeX, specific sections, etc.)
   - DO NOT truncate or summarize
   - DO NOT wrap in markdown code blocks
   - Output the deliverable EXACTLY as specified in the prompt

2) Then, append a meta section with the following EXACT format:

<<<META_JSON>>>
{{
  "evidence": [
    {{"title": "Paper Title", "venue": "Venue/Year", "doi": "10.xxxx/yyyy", "finding": "Key finding"}}
  ],
  "confidence_score": 0.85,
  "confidence_justification": "Brief explanation of confidence level"
}}
<<<END_META>>>

**IMPORTANT RULES:**
- Output the deliverable FIRST and COMPLETELY
- The deliverable can have ANY format (YAML, BibTeX, markdown, specific sections, etc.)
- After the deliverable is complete, add a blank line and then the meta section
- Meta section MUST use the exact delimiters: <<<META_JSON>>> and <<<END_META>>>
- Evidence must have real DOIs (no placeholders like 10.1109/xxx.2024.1)
- If DOI not found, use "UNKNOWN" in the doi field
- DO NOT wrap deliverable or meta in markdown code blocks
- Confidence score must be between 0.0 and 1.0
"""
        return wrapped

    def _wrap_sidecar_meta(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        Sidecar Meta Agentic Wrapper - External meta file mode (v4.1)

        输出完整的 deliverable（任何格式），meta 信息将被提取并保存到单独的 JSON 文件。
        这是最干净的模式：deliverable 完全不受影响，meta 信息存储在外部。

        Use for: Steps where you want zero impact on deliverable format
        - Same use cases as meta_tail mode
        - When you prefer external meta files over inline meta
        - When deliverable needs to be parsed by external tools

        Benefits:
        - Zero format conflicts (deliverable is 100% clean)
        - Meta stored separately for easy access
        - Minimal overhead (~15%)
        - Easy to integrate with external tools

        Output format:
        ```
        [Complete deliverable with any format - 100% clean]

        <<<SIDECAR_META>>>
        {
          "evidence": [...],
          "confidence_score": 0.85,
          "confidence_justification": "...",
          "plan": [...],  # Optional
          "risks": [...],  # Optional
          "verification": [...]  # Optional
        }
        <<<END_SIDECAR_META>>>
        ```

        The sidecar meta section will be extracted and saved to:
        projects/{project_id}/logs/{step_id}_meta.json
        """
        # Use custom system prompt if provided, otherwise use a sidecar version
        if system_prompt:
            final_system_prompt = system_prompt
        else:
            final_system_prompt = """You are a Chief Intelligence Officer and senior academic editor serving as a Research Partner.

Provide complete, evidence-based output with quality metadata that will be stored separately."""

        wrapped = f"""{final_system_prompt}

---

**User Request:**
{prompt}

---

**CRITICAL: TWO-PART OUTPUT FORMAT (SOP v4.1 Sidecar Meta Mode):**

1) First, output the COMPLETE deliverable as requested:
   - Use ANY required format (YAML front-matter, BibTeX, specific sections, etc.)
   - DO NOT truncate or summarize
   - DO NOT wrap in markdown code blocks
   - Output the deliverable EXACTLY as specified in the prompt
   - This deliverable will be saved as-is to the document file

2) Then, append a sidecar meta section with the following EXACT format:

<<<SIDECAR_META>>>
{{
  "evidence": [
    {{"title": "Paper Title", "venue": "Venue/Year", "doi": "10.xxxx/yyyy", "finding": "Key finding"}}
  ],
  "confidence_score": 0.85,
  "confidence_justification": "Brief explanation of confidence level",
  "plan": ["Step 1", "Step 2"],
  "risks": ["Risk 1", "Risk 2"],
  "verification": ["Check 1", "Check 2"]
}}
<<<END_SIDECAR_META>>>

**IMPORTANT RULES:**
- Output the deliverable FIRST and COMPLETELY
- The deliverable can have ANY format (YAML, BibTeX, markdown, specific sections, etc.)
- After the deliverable is complete, add a blank line and then the sidecar meta section
- Sidecar meta section MUST use the exact delimiters: <<<SIDECAR_META>>> and <<<END_SIDECAR_META>>>
- Evidence must have real DOIs (no placeholders like 10.1109/xxx.2024.1)
- If DOI not found, use "UNKNOWN" in the doi field
- DO NOT wrap deliverable or meta in markdown code blocks
- Confidence score must be between 0.0 and 1.0
- Plan, risks, and verification are optional but recommended
- The sidecar meta will be extracted and saved to a separate JSON file
"""
        return wrapped

    def validate_response(self, response: str) -> Dict[str, Any]:
        """
        Validate Gemini response structure

        Args:
            response: Gemini response text

        Returns:
            Dict with validation results and extracted components
        """
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "components": {},
            "confidence_score": None,
            "risks_count": 0,
            "verification_count": 0,
            "has_placeholder_doi": False,
            "has_markdown_codeblock": False
        }

        if not self.enabled:
            validation_result["components"]["deliverables"] = response
            return validation_result

        # Check for required sections
        required_sections = ["Plan", "Actions Taken", "Evidence", "Deliverables", "Risks", "Verification Checklist", "Confidence Score"]
        found_sections = {}

        for section in required_sections:
            # Match section headers (case-insensitive, flexible formatting)
            pattern = rf"##\s*{re.escape(section)}\s*\n(.*?)(?=##|\Z)"
            match = re.search(pattern, response, re.IGNORECASE | re.DOTALL)

            if match:
                found_sections[section.lower().replace(" ", "_")] = match.group(1).strip()
            else:
                if self.validation.get("require_plan", True) and section == "Plan":
                    validation_result["errors"].append(f"Missing required section: {section}")
                    validation_result["valid"] = False
                elif self.validation.get("require_evidence", True) and section == "Evidence":
                    validation_result["errors"].append(f"Missing required section: {section}")
                    validation_result["valid"] = False
                elif section == "Risks":
                    validation_result["errors"].append(f"Missing required section: {section} (SOP v4.0 requires >=5 risks)")
                    validation_result["valid"] = False
                elif section == "Verification Checklist":
                    validation_result["errors"].append(f"Missing required section: {section} (SOP v4.0 requires >=5 items)")
                    validation_result["valid"] = False
                else:
                    validation_result["warnings"].append(f"Missing optional section: {section}")

        validation_result["components"] = found_sections

        # Extract and validate confidence score
        if "confidence_score" in found_sections:
            confidence_text = found_sections["confidence_score"]
            # Try to extract numeric score (0.0-1.0 or 0-100%)
            score_match = re.search(r"(\d+\.?\d*)", confidence_text)
            if score_match:
                score = float(score_match.group(1))
                # Normalize to 0-1 range
                if score > 1.0:
                    score = score / 100.0
                validation_result["confidence_score"] = score

                # Check minimum confidence threshold
                min_confidence = self.validation.get("min_confidence", 0.7)
                if score < min_confidence:
                    validation_result["warnings"].append(
                        f"Low confidence score: {score:.2f} (threshold: {min_confidence})"
                    )
            else:
                validation_result["warnings"].append("Could not parse confidence score")

        # Validate Risks section (SOP v4.0: >=5 risks required)
        if "risks" in found_sections:
            risks_text = found_sections["risks"]
            # Count numbered items (1., 2., etc.) or bullet points (-, *, etc.)
            risk_items = re.findall(r'^\s*(?:\d+\.|[-*])\s+.+', risks_text, re.MULTILINE)
            validation_result["risks_count"] = len(risk_items)

            if len(risk_items) < 5:
                validation_result["warnings"].append(
                    f"Insufficient risks: {len(risk_items)} found, SOP v4.0 requires >=5"
                )

        # Validate Verification Checklist (SOP v4.0: >=5 items required)
        if "verification_checklist" in found_sections:
            verification_text = found_sections["verification_checklist"]
            # Count numbered items or bullet points
            verification_items = re.findall(r'^\s*(?:\d+\.|[-*])\s+.+', verification_text, re.MULTILINE)
            validation_result["verification_count"] = len(verification_items)

            if len(verification_items) < 5:
                validation_result["warnings"].append(
                    f"Insufficient verification items: {len(verification_items)} found, SOP v4.0 requires >=5"
                )

        # Check for placeholder DOIs (SOP v4.0: not allowed)
        if "evidence" in found_sections:
            evidence_text = found_sections["evidence"]
            # Pattern for placeholder DOIs like 10.1109/xxx.2024.1 or 10.xxxx/yyyy
            placeholder_patterns = [
                r'10\.\d+/xxx',  # 10.1109/xxx
                r'10\.xxxx/',    # 10.xxxx/
                r'10\.\d+/\w*\.{3}',  # 10.1109/...
                r'DOI:\s*TBD',   # DOI: TBD
                r'DOI:\s*pending',  # DOI: pending
            ]

            for pattern in placeholder_patterns:
                if re.search(pattern, evidence_text, re.IGNORECASE):
                    validation_result["has_placeholder_doi"] = True
                    validation_result["errors"].append(
                        "Placeholder DOI detected in Evidence section. SOP v4.0 requires real DOIs or UNKNOWN."
                    )
                    validation_result["valid"] = False
                    break

        # Check for markdown code blocks wrapping deliverables (SOP v4.0: not allowed)
        if "deliverables" in found_sections:
            deliverables_text = found_sections["deliverables"]
            # Check if entire deliverable is wrapped in ```markdown``` or ``` code block
            if re.match(r'^\s*```', deliverables_text) and re.search(r'```\s*$', deliverables_text):
                validation_result["has_markdown_codeblock"] = True
                validation_result["warnings"].append(
                    "Deliverables wrapped in markdown code block. SOP v4.0 discourages this practice."
                )

        return validation_result

    def _extract_meta_tail(self, response: str) -> Dict[str, Any]:
        """
        从 meta_tail 格式中提取 deliverable 和 meta

        Args:
            response: 完整的响应内容

        Returns:
            Dict with keys:
            - content: str (提取的 deliverable)
            - meta: dict (提取的 meta JSON，如果有)
            - extraction_method: str (使用的提取方法)
            - success: bool (提取是否成功)
            - warnings: List[str] (任何警告)
        """
        result = {
            "content": response,  # 默认 fallback
            "meta": None,
            "extraction_method": "fallback",
            "success": False,
            "warnings": []
        }

        # 检查 meta 分隔符
        if "<<<META_JSON>>>" not in response or "<<<END_META>>>" not in response:
            result["warnings"].append("Meta delimiters not found")
            return result

        # 分割 deliverable 和 meta
        try:
            parts = response.split("<<<META_JSON>>>")
            if len(parts) != 2:
                result["warnings"].append("Invalid meta format (multiple META_JSON markers)")
                return result

            deliverable = parts[0].strip()
            meta_part = parts[1].split("<<<END_META>>>")[0].strip()

            # 解析 meta JSON
            try:
                meta = json.loads(meta_part)
                result["content"] = deliverable
                result["meta"] = meta
                result["extraction_method"] = "meta_tail"
                result["success"] = True
                logger.info(f"✓ Extracted meta_tail format: {len(deliverable)} chars deliverable + meta")
            except json.JSONDecodeError as e:
                result["warnings"].append(f"Failed to parse meta JSON: {e}")
                result["content"] = deliverable  # 仍然返回 deliverable
                result["extraction_method"] = "meta_tail_partial"
                result["success"] = True  # 部分成功
                logger.warning(f"⚠️ Meta JSON parse failed, but deliverable extracted")

            return result

        except Exception as e:
            result["warnings"].append(f"Extraction error: {e}")
            return result

    def _extract_sidecar_meta(self, response: str) -> Dict[str, Any]:
        """
        从 sidecar_meta 格式中提取 deliverable 和 meta

        Args:
            response: 完整的响应内容

        Returns:
            Dict with keys:
            - content: str (提取的 deliverable)
            - meta: dict (提取的 meta JSON，如果有)
            - extraction_method: str (使用的提取方法)
            - success: bool (提取是否成功)
            - warnings: List[str] (任何警告)
        """
        result = {
            "content": response,  # 默认 fallback
            "meta": None,
            "extraction_method": "fallback",
            "success": False,
            "warnings": []
        }

        # 检查 sidecar meta 分隔符
        if "<<<SIDECAR_META>>>" not in response or "<<<END_SIDECAR_META>>>" not in response:
            result["warnings"].append("Sidecar meta delimiters not found")
            return result

        # 分割 deliverable 和 meta
        try:
            parts = response.split("<<<SIDECAR_META>>>")
            if len(parts) != 2:
                result["warnings"].append("Invalid sidecar meta format (multiple SIDECAR_META markers)")
                return result

            deliverable = parts[0].strip()
            meta_part = parts[1].split("<<<END_SIDECAR_META>>>")[0].strip()

            # 解析 meta JSON
            try:
                meta = json.loads(meta_part)
                result["content"] = deliverable
                result["meta"] = meta
                result["extraction_method"] = "sidecar_meta"
                result["success"] = True
                logger.info(f"✓ Extracted sidecar_meta format: {len(deliverable)} chars deliverable + meta")
            except json.JSONDecodeError as e:
                result["warnings"].append(f"Failed to parse sidecar meta JSON: {e}")
                result["content"] = deliverable  # 仍然返回 deliverable
                result["extraction_method"] = "sidecar_meta_partial"
                result["success"] = True  # 部分成功
                logger.warning(f"⚠️ Sidecar meta JSON parse failed, but deliverable extracted")

            return result

        except Exception as e:
            result["warnings"].append(f"Extraction error: {e}")
            return result

    def extract_deliverables(self, response: str) -> Dict[str, Any]:
        """
        Extract deliverables section from Agentic response (v4.1 Enhanced)

        Enhanced to handle:
        1. Sidecar meta format (v4.1 NEW) - Priority 1
        2. Meta-tail format (v4.1) - Priority 2
        3. Standard ## Deliverables format
        4. Content wrapped in markdown code blocks
        5. YAML front-matter followed by content
        6. Multiple response formats

        Args:
            response: Full Agentic response

        Returns:
            Dict with keys:
            - content: str (提取的 deliverable)
            - meta: dict (提取的 meta，如果有)
            - extraction_method: str (使用的提取方法)
            - success: bool (提取是否成功)
            - warnings: List[str] (任何警告)
        """
        if not self.enabled:
            return {
                "content": response,
                "meta": None,
                "extraction_method": "disabled",
                "success": True,
                "warnings": []
            }

        original_response = response

        # Step 1: 检查 sidecar_meta 格式（优先级最高）
        if "<<<SIDECAR_META>>>" in response:
            result = self._extract_sidecar_meta(response)
            if result["success"]:
                return result
            # 如果 sidecar_meta 提取失败，继续尝试其他方法

        # Step 2: 检查 meta_tail 格式（优先级第二）
        if "<<<META_JSON>>>" in response:
            result = self._extract_meta_tail(response)
            if result["success"]:
                return result
            # 如果 meta_tail 提取失败，继续尝试其他方法

        # Step 1: Remove outer markdown code blocks if present
        # Pattern: ```yaml\n...\n``` or ```markdown\n...\n``` or ```\n...\n```
        code_block_pattern = r'^```(?:yaml|markdown|md)?\s*\n(.*?)\n```\s*$'
        code_block_match = re.search(code_block_pattern, response, re.DOTALL | re.MULTILINE)

        if code_block_match:
            response = code_block_match.group(1)
            logger.info(f"🔧 Removed outer markdown code block wrapper ({len(original_response)} → {len(response)} chars)")

        # Step 2: Try to extract ## Deliverables section
        patterns = [
            # Pattern 1: Standard markdown header (## Deliverables)
            (r"##\s*Deliverables\s*\n(.*?)(?=##|\Z)", "markdown header"),
            # Pattern 2: Bold with colon (**Deliverables:**)
            (r"\*\*Deliverables:?\*\*\s*\n(.*?)(?=\n\n\*\*|\n\n##|\Z)", "bold with colon"),
            # Pattern 3: Plain text with colon (Deliverables:)
            (r"Deliverables:?\s*\n(.*?)(?=\n\n[A-Z]|\n\n##|\Z)", "plain text"),
        ]

        for pattern, pattern_name in patterns:
            match = re.search(pattern, response, re.IGNORECASE | re.DOTALL)
            if match:
                deliverables = match.group(1).strip()
                if len(deliverables) > 0:
                    logger.info(f"✓ Extracted deliverables using {pattern_name}: {len(deliverables)} chars (mode: {self.mode})")

                    # Check if deliverables seem too short (possible truncation)
                    warnings = []
                    if len(deliverables) < 500 and self.mode == "lite":
                        warning_msg = f"Deliverables seem short ({len(deliverables)} chars) for lite mode - possible truncation"
                        logger.warning(f"⚠️ {warning_msg}")
                        warnings.append(warning_msg)

                    return {
                        "content": deliverables,
                        "meta": None,
                        "extraction_method": pattern_name,
                        "success": True,
                        "warnings": warnings
                    }
                else:
                    logger.debug(f"Pattern {pattern_name} matched but extracted empty content")

        # Step 3: If no Deliverables section found, try to extract content after YAML front-matter
        # This handles cases where the entire response is the deliverable (no explicit ## Deliverables header)
        yaml_pattern = r'^---\s*\n.*?\n---\s*\n(.*)$'
        yaml_match = re.search(yaml_pattern, response, re.DOTALL | re.MULTILINE)

        if yaml_match:
            content_after_yaml = yaml_match.group(1).strip()
            if len(content_after_yaml) > 100:  # Reasonable content length
                logger.info(f"✓ Extracted content after YAML front-matter: {len(content_after_yaml)} chars (mode: {self.mode})")
                return {
                    "content": content_after_yaml,
                    "meta": None,
                    "extraction_method": "yaml_front_matter",
                    "success": True,
                    "warnings": []
                }

        # Step 4: Fallback - return full response
        logger.warning(f"⚠️ Deliverables section not found in response (mode: {self.mode}), returning full response as fallback")
        logger.debug(f"Response preview (first 500 chars): {response[:500]}")

        warnings = []

        # Check if response has any section headers at all
        if "##" not in response:
            warning_msg = "Response does not contain any ## section headers"
            logger.warning(warning_msg)
            warnings.append(warning_msg)

        # Check response length
        if len(response) < 1000:
            warning_msg = f"Response is very short ({len(response)} chars) - possible truncation or incomplete output"
            logger.warning(f"⚠️ {warning_msg}")
            warnings.append(warning_msg)

        # Return full response as fallback
        return {
            "content": response,
            "meta": None,
            "extraction_method": "fallback_full_response",
            "success": False,
            "warnings": warnings
        }

    def get_system_prompt(self) -> str:
        """Get the configured system prompt"""
        return self.system_prompt

    @staticmethod
    def get_sidecar_meta_path(project_path: Path, step_id: str) -> Path:
        """
        Get the path for sidecar meta file

        Args:
            project_path: Path to project directory
            step_id: Step ID (e.g., "step_1_1")

        Returns:
            Path: Path to sidecar meta file
        """
        meta_dir = project_path / "logs"
        meta_dir.mkdir(parents=True, exist_ok=True)
        return meta_dir / f"{step_id}_meta.json"

    @staticmethod
    def save_sidecar_meta(meta: Dict[str, Any], project_path: Path, step_id: str) -> str:
        """
        Save sidecar meta to JSON file

        Args:
            meta: Meta dictionary to save
            project_path: Path to project directory
            step_id: Step ID (e.g., "step_1_1")

        Returns:
            str: Path to saved meta file
        """
        meta_path = AgenticWrapper.get_sidecar_meta_path(project_path, step_id)

        try:
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)
            logger.info(f"✓ Saved sidecar meta to {meta_path}")
            return str(meta_path)
        except Exception as e:
            logger.error(f"❌ Failed to save sidecar meta: {e}")
            raise
