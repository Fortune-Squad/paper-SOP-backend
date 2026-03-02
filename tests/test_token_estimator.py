"""
Unit tests for TokenEstimator
Tests token estimation and wrapper mode selection
"""
import pytest
import sys
from unittest.mock import MagicMock


# --- Provide a realistic tiktoken mock before importing the module ---
def _fake_encode(text):
    """Simulate tiktoken encoding: ~1 token per 4 chars for ASCII, ~1 per 1.5 for CJK."""
    if not text:
        return []
    count = 0
    for ch in text:
        if ord(ch) > 0x2E80:  # CJK range
            count += 3  # each CJK char ≈ 1 token (represented as 3 sub-units)
        else:
            count += 1
    # Roughly 1 token per 4 bytes
    n_tokens = max(1, count // 4) if count > 0 else 0
    return [0] * n_tokens


_mock_encoding = MagicMock()
_mock_encoding.encode = _fake_encode

_mock_tiktoken = MagicMock()
_mock_tiktoken.encoding_for_model.return_value = _mock_encoding
_mock_tiktoken.get_encoding.return_value = _mock_encoding
sys.modules["tiktoken"] = _mock_tiktoken

from app.utils.token_estimator import TokenEstimator, estimate_tokens, select_wrapper_mode


class TestTokenEstimator:
    """Test TokenEstimator functionality"""

    @pytest.fixture
    def estimator(self):
        """Create a TokenEstimator instance"""
        return TokenEstimator(model="gpt-4")

    def test_estimate_tokens_english(self, estimator):
        """Test token estimation for English text"""
        text = "Hello, world! This is a test."
        tokens = estimator.estimate_tokens(text)

        # English text: roughly 1 token per 4 characters
        assert tokens > 0
        assert tokens < len(text)  # Tokens should be less than characters
        assert 5 < tokens < 15  # Reasonable range for this text

    def test_estimate_tokens_chinese(self, estimator):
        """Test token estimation for Chinese text"""
        text = "你好世界！这是一个测试。"
        tokens = estimator.estimate_tokens(text)

        # Chinese text: roughly 1 token per 1-2 characters
        assert tokens > 0
        assert tokens >= len(text) // 2  # At least half the character count

    def test_estimate_tokens_mixed(self, estimator):
        """Test token estimation for mixed language text"""
        text = "Hello 你好 World 世界"
        tokens = estimator.estimate_tokens(text)

        assert tokens > 0
        assert tokens < len(text)

    def test_estimate_tokens_empty(self, estimator):
        """Test token estimation for empty string"""
        tokens = estimator.estimate_tokens("")
        assert tokens == 0

    def test_estimate_tokens_long_text(self, estimator):
        """Test token estimation for long text"""
        text = "A" * 10000
        tokens = estimator.estimate_tokens(text)

        # Mock encoding: 10000 / 4 = 2500 tokens
        assert tokens > 1000

    def test_select_wrapper_mode_specific_format(self, estimator):
        """Test mode selection with specific format"""
        mode = estimator.select_wrapper_mode(
            expected_tokens=1000,
            has_specific_format=True
        )
        assert mode == "meta_tail"

    def test_select_wrapper_mode_very_long(self, estimator):
        """Test mode selection for very long output"""
        mode = estimator.select_wrapper_mode(
            expected_tokens=6000,
            has_specific_format=False
        )
        assert mode == "disabled"

    def test_select_wrapper_mode_long(self, estimator):
        """Test mode selection for long output"""
        mode = estimator.select_wrapper_mode(
            expected_tokens=3000,
            has_specific_format=False
        )
        assert mode == "lite"

    def test_select_wrapper_mode_short(self, estimator):
        """Test mode selection for short output"""
        mode = estimator.select_wrapper_mode(
            expected_tokens=1500,
            has_specific_format=False
        )
        assert mode == "full"

    def test_calculate_max_tokens(self, estimator):
        """Test max_tokens calculation"""
        max_tokens = estimator.calculate_max_tokens(
            expected_tokens=4000,
            safety_margin=2.0
        )

        # Should be 4000 * 2.0 = 8000
        assert max_tokens == 8000

    def test_calculate_max_tokens_with_limit(self, estimator):
        """Test max_tokens calculation with absolute limit"""
        max_tokens = estimator.calculate_max_tokens(
            expected_tokens=10000,
            safety_margin=2.0,
            absolute_max=16384
        )

        # Should be capped at 16384
        assert max_tokens == 16384

    def test_estimate_prompt_overhead(self, estimator):
        """Test prompt overhead estimation"""
        overhead_full = estimator.estimate_prompt_overhead("full")
        overhead_lite = estimator.estimate_prompt_overhead("lite")
        overhead_minimal = estimator.estimate_prompt_overhead("minimal")
        overhead_meta_tail = estimator.estimate_prompt_overhead("meta_tail")
        overhead_disabled = estimator.estimate_prompt_overhead("disabled")

        # Verify ordering
        assert overhead_full > overhead_lite
        assert overhead_lite > overhead_minimal
        assert overhead_lite > overhead_meta_tail
        assert overhead_disabled == 0

    def test_validate_token_budget_within(self, estimator):
        """Test token budget validation (within budget)"""
        within = estimator.validate_token_budget(
            prompt_tokens=1000,
            expected_output_tokens=2000,
            wrapper_mode="lite",
            max_context_tokens=32000
        )

        assert within is True

    def test_validate_token_budget_exceeded(self, estimator):
        """Test token budget validation (exceeded)"""
        within = estimator.validate_token_budget(
            prompt_tokens=20000,
            expected_output_tokens=15000,
            wrapper_mode="full",
            max_context_tokens=32000
        )

        assert within is False

    def test_get_token_stats(self, estimator):
        """Test token statistics"""
        text = "Hello, world!\nThis is a test.\nMultiple lines."
        stats = estimator.get_token_stats(text)

        assert "tokens" in stats
        assert "characters" in stats
        assert "lines" in stats
        assert "chars_per_token" in stats
        assert "tokens_per_line" in stats

        assert stats["tokens"] > 0
        assert stats["characters"] == len(text)
        assert stats["lines"] == 3
        assert stats["chars_per_token"] > 0
        assert stats["tokens_per_line"] > 0

    def test_convenience_function_estimate_tokens(self):
        """Test convenience function for token estimation"""
        tokens = estimate_tokens("Hello, world!")
        assert tokens > 0
        assert tokens < 20

    def test_convenience_function_select_mode(self):
        """Test convenience function for mode selection"""
        mode = select_wrapper_mode(
            expected_tokens=1000,
            has_specific_format=True
        )
        assert mode == "meta_tail"

    def test_mode_selection_boundary_5000(self, estimator):
        """Test mode selection at 5000 token boundary"""
        mode_4999 = estimator.select_wrapper_mode(4999, False)
        mode_5000 = estimator.select_wrapper_mode(5000, False)
        mode_5001 = estimator.select_wrapper_mode(5001, False)

        assert mode_4999 == "lite"
        assert mode_5000 == "lite"
        assert mode_5001 == "disabled"

    def test_mode_selection_boundary_2000(self, estimator):
        """Test mode selection at 2000 token boundary"""
        mode_1999 = estimator.select_wrapper_mode(1999, False)
        mode_2000 = estimator.select_wrapper_mode(2000, False)
        mode_2001 = estimator.select_wrapper_mode(2001, False)

        assert mode_1999 == "full"
        assert mode_2000 == "full"
        assert mode_2001 == "lite"

    def test_token_estimation_accuracy(self, estimator):
        """Test token estimation accuracy for various texts"""
        test_cases = [
            ("Short text", 2, 5),
            ("A" * 100, 20, 30),  # 100/4 = 25
            ("The quick brown fox jumps over the lazy dog", 8, 15),
            ("你好世界" * 10, 15, 50),
        ]

        for text, min_tokens, max_tokens in test_cases:
            tokens = estimator.estimate_tokens(text)
            assert min_tokens <= tokens <= max_tokens, \
                f"Token count {tokens} not in range [{min_tokens}, {max_tokens}] for: {text[:50]}"
