"""
LLM Orchestration 测试
v1.2 DevSpec §13 - LLM Orchestration

测试内容:
- L1: AIClient 标准 generate() 接口
- L2: PromptPackCompiler v1.2 新增参数（memory_entries, north_star）
- L3: PromptType 枚举（包含 READINESS_ASSESSMENT）
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from app.services.ai_client import AIClient, ChatGPTClient, GeminiClient, ClaudeClient
from app.services.prompt_pack_compiler import (
    PromptPackCompiler,
    PromptTemplate,
    PromptType,
    PromptPack
)


class TestV12_L_LLMOrchestrationCompliance:
    """v1.2 §13 LLM Orchestration 合规性测试"""

    def test_ai_client_has_generate_method(self):
        """L1: AIClient 基类定义 generate() 方法"""
        # 验证 generate 方法存在
        assert hasattr(AIClient, 'generate')

        # 验证方法签名
        import inspect
        sig = inspect.signature(AIClient.generate)
        params = list(sig.parameters.keys())
        assert 'prompt' in params
        assert 'system' in params
        assert 'attachments' in params
        assert 'response_format' in params

    def test_chatgpt_client_generate_interface(self):
        """L1: ChatGPTClient 实现 generate() 接口"""
        # Mock OpenAI client
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="test response"))]
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        client = ChatGPTClient()
        client.client = mock_client

        # 调用 generate (同步测试，验证方法存在和签名)
        assert hasattr(client, 'generate')
        assert asyncio.iscoroutinefunction(client.generate)

    def test_gemini_client_generate_interface(self):
        """L1: GeminiClient 实现 generate() 接口"""
        client = GeminiClient()

        # 验证方法存在
        assert hasattr(client, 'generate')
        assert asyncio.iscoroutinefunction(client.generate)

    def test_claude_client_generate_interface(self):
        """L1: ClaudeClient 实现 generate() 接口"""
        client = ClaudeClient()

        # 验证方法存在
        assert hasattr(client, 'generate')
        assert asyncio.iscoroutinefunction(client.generate)

    def test_generate_signature_matches_spec(self):
        """L1: generate() 签名符合 §13.1 规格"""
        import inspect

        # 检查 ChatGPTClient.generate 签名
        sig = inspect.signature(ChatGPTClient.generate)
        params = list(sig.parameters.keys())

        assert 'prompt' in params
        assert 'system' in params
        assert 'attachments' in params
        assert 'response_format' in params

    def test_prompt_type_enum_exists(self):
        """L3: PromptType 枚举存在"""
        assert hasattr(PromptType, 'EXECUTE')
        assert hasattr(PromptType, 'REVIEW_ACCEPTANCE')
        assert hasattr(PromptType, 'REVIEW_FIX')
        assert hasattr(PromptType, 'DIAGNOSE')
        assert hasattr(PromptType, 'ASSEMBLY_KIT')
        assert hasattr(PromptType, 'FIGURE_GEN')
        assert hasattr(PromptType, 'READINESS_ASSESSMENT')  # v1.2 新增

    def test_prompt_type_readiness_assessment(self):
        """L3: PromptType 包含 READINESS_ASSESSMENT"""
        assert PromptType.READINESS_ASSESSMENT == "readiness_assessment"

    def test_prompt_template_has_prompt_type(self):
        """L3: PromptTemplate 支持 prompt_type 参数"""
        template = PromptTemplate(
            template_id="test_template",
            template_text="Test {artifact}",
            required_artifacts=["artifact"],
            prompt_type=PromptType.READINESS_ASSESSMENT
        )

        assert template.prompt_type == PromptType.READINESS_ASSESSMENT

    def test_compile_prompt_accepts_memory_entries(self):
        """L2: compile_prompt 接受 memory_entries 参数"""
        compiler = PromptPackCompiler()
        template = PromptTemplate(
            template_id="test",
            template_text="Prompt: {memory_entries}",
            required_artifacts=[],
            optional_artifacts=["memory_entries"]
        )
        compiler.register_template(template)

        # 编译 prompt with memory_entries
        pack = compiler.compile_prompt(
            template_id="test",
            project_id="test_proj",
            memory_entries="[LEARN:tag1] Lesson 1\n[LEARN:tag2] Lesson 2"
        )

        assert "Lesson 1" in pack.compiled_prompt
        assert "Lesson 2" in pack.compiled_prompt

    def test_compile_prompt_accepts_north_star(self):
        """L2: compile_prompt 接受 north_star 参数"""
        compiler = PromptPackCompiler()
        template = PromptTemplate(
            template_id="test_ra",
            template_text="North Star: {north_star}",
            required_artifacts=[],
            optional_artifacts=["north_star"],
            prompt_type=PromptType.READINESS_ASSESSMENT
        )
        compiler.register_template(template)

        # 编译 prompt with north_star
        pack = compiler.compile_prompt(
            template_id="test_ra",
            project_id="test_proj",
            north_star="Can we achieve X with method Y?"
        )

        assert "Can we achieve X with method Y?" in pack.compiled_prompt

    def test_compile_prompt_with_both_v12_params(self):
        """L2: compile_prompt 同时接受 memory_entries 和 north_star"""
        compiler = PromptPackCompiler()
        template = PromptTemplate(
            template_id="test_full",
            template_text="Memory: {memory_entries}\nNorth Star: {north_star}",
            required_artifacts=[],
            optional_artifacts=["memory_entries", "north_star"],
            prompt_type=PromptType.READINESS_ASSESSMENT
        )
        compiler.register_template(template)

        # 编译 prompt with both params
        pack = compiler.compile_prompt(
            template_id="test_full",
            project_id="test_proj",
            memory_entries="[LEARN:physics] Use conservation laws",
            north_star="Can we model turbulence accurately?"
        )

        assert "conservation laws" in pack.compiled_prompt
        assert "turbulence" in pack.compiled_prompt

    def test_compile_prompt_signature_backward_compatible(self):
        """L2: compile_prompt 向后兼容（新参数可选）"""
        compiler = PromptPackCompiler()
        template = PromptTemplate(
            template_id="test_compat",
            template_text="Simple prompt",
            required_artifacts=[]
        )
        compiler.register_template(template)

        # 不传 v1.2 新参数也能工作
        pack = compiler.compile_prompt(
            template_id="test_compat",
            project_id="test_proj"
        )

        assert pack.compiled_prompt == "Simple prompt"

    def test_prompt_pack_compiler_module_exists(self):
        """验证 prompt_pack_compiler 模块存在"""
        try:
            from app.services import prompt_pack_compiler
            assert hasattr(prompt_pack_compiler, 'PromptPackCompiler')
            assert hasattr(prompt_pack_compiler, 'PromptType')
        except ImportError:
            pytest.fail("prompt_pack_compiler module not found")
