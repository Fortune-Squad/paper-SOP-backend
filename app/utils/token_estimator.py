"""
Token Estimator for Wrapper Mode Selection
Uses tiktoken to estimate token counts for accurate mode selection
"""
import tiktoken
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TokenEstimator:
    """
    Token estimation utility for wrapper mode selection

    Uses tiktoken to estimate token counts, which is more accurate than
    character counts for determining truncation risk and mode selection.
    """

    def __init__(self, model: str = "gpt-4"):
        """
        Initialize TokenEstimator

        Args:
            model: Model name for token encoding (default: gpt-4)
        """
        try:
            self.encoding = tiktoken.encoding_for_model(model)
            self.model = model
            logger.info(f"TokenEstimator initialized for model: {model}")
        except KeyError:
            # Fallback to cl100k_base encoding (used by gpt-4, gpt-3.5-turbo)
            logger.warning(f"Model {model} not found, using cl100k_base encoding")
            self.encoding = tiktoken.get_encoding("cl100k_base")
            self.model = "cl100k_base"

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text

        Args:
            text: Text to estimate tokens for

        Returns:
            int: Estimated token count
        """
        try:
            tokens = self.encoding.encode(text)
            token_count = len(tokens)
            logger.debug(f"Estimated {token_count} tokens for {len(text)} characters")
            return token_count
        except Exception as e:
            logger.error(f"Failed to estimate tokens: {e}")
            # Fallback: rough estimate (1 token ≈ 4 characters for English)
            return len(text) // 4

    def select_wrapper_mode(
        self,
        expected_tokens: int,
        has_specific_format: bool = False,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Auto-select wrapper mode based on expected output tokens

        Decision tree:
        1. If has_specific_format → "meta_tail" (non-invasive)
        2. If expected_tokens > 5000 → "disabled" (avoid truncation)
        3. If expected_tokens > 2000 → "lite" (balance quality & completeness)
        4. Otherwise → "full" (complete quality control)

        Args:
            expected_tokens: Expected output token count
            has_specific_format: Whether step has specific format requirements
            max_tokens: Maximum tokens allowed (optional)

        Returns:
            str: Recommended wrapper mode
        """
        # Rule 1: Specific format requirements → meta_tail
        if has_specific_format:
            logger.info(f"Selected 'meta_tail' mode (specific format required)")
            return "meta_tail"

        # Rule 2: Very long output → disabled
        if expected_tokens > 5000:
            logger.info(f"Selected 'disabled' mode (expected {expected_tokens} tokens > 5000)")
            return "disabled"

        # Rule 3: Long output → lite
        if expected_tokens > 2000:
            logger.info(f"Selected 'lite' mode (expected {expected_tokens} tokens > 2000)")
            return "lite"

        # Rule 4: Short output → full
        logger.info(f"Selected 'full' mode (expected {expected_tokens} tokens <= 2000)")
        return "full"

    def calculate_max_tokens(
        self,
        expected_tokens: int,
        safety_margin: float = 2.0,
        absolute_max: int = 16384
    ) -> int:
        """
        Calculate recommended max_tokens parameter

        Args:
            expected_tokens: Expected output token count
            safety_margin: Multiplier for safety margin (default: 2.0)
            absolute_max: Absolute maximum tokens (default: 16384)

        Returns:
            int: Recommended max_tokens value
        """
        recommended = int(expected_tokens * safety_margin)
        max_tokens = min(recommended, absolute_max)

        logger.info(
            f"Calculated max_tokens: {max_tokens} "
            f"(expected: {expected_tokens}, margin: {safety_margin}x)"
        )

        return max_tokens

    def estimate_prompt_overhead(self, wrapper_mode: str) -> int:
        """
        Estimate prompt overhead for different wrapper modes

        Args:
            wrapper_mode: Wrapper mode ("full", "lite", "minimal", "meta_tail", "disabled")

        Returns:
            int: Estimated prompt overhead in tokens
        """
        overhead_map = {
            "full": 750,      # ~75% overhead (7 sections)
            "lite": 250,      # ~25% overhead (3 sections)
            "minimal": 100,   # ~10% overhead (1 section)
            "meta_tail": 150, # ~15% overhead (2-part format)
            "disabled": 0     # No overhead
        }

        overhead = overhead_map.get(wrapper_mode, 0)
        logger.debug(f"Estimated {overhead} tokens overhead for '{wrapper_mode}' mode")
        return overhead

    def validate_token_budget(
        self,
        prompt_tokens: int,
        expected_output_tokens: int,
        wrapper_mode: str,
        max_context_tokens: int = 32000
    ) -> bool:
        """
        Validate that token budget is within limits

        Args:
            prompt_tokens: Tokens in the prompt
            expected_output_tokens: Expected output tokens
            wrapper_mode: Wrapper mode
            max_context_tokens: Maximum context window (default: 32000)

        Returns:
            bool: True if within budget, False otherwise
        """
        overhead = self.estimate_prompt_overhead(wrapper_mode)
        total_tokens = prompt_tokens + overhead + expected_output_tokens

        within_budget = total_tokens <= max_context_tokens

        if not within_budget:
            logger.warning(
                f"Token budget exceeded: {total_tokens} > {max_context_tokens} "
                f"(prompt: {prompt_tokens}, overhead: {overhead}, output: {expected_output_tokens})"
            )
        else:
            logger.debug(
                f"Token budget OK: {total_tokens} <= {max_context_tokens} "
                f"({(total_tokens/max_context_tokens)*100:.1f}% used)"
            )

        return within_budget

    def get_token_stats(self, text: str) -> dict:
        """
        Get detailed token statistics for text

        Args:
            text: Text to analyze

        Returns:
            dict: Token statistics
        """
        token_count = self.estimate_tokens(text)
        char_count = len(text)
        line_count = text.count('\n') + 1

        stats = {
            "tokens": token_count,
            "characters": char_count,
            "lines": line_count,
            "chars_per_token": char_count / token_count if token_count > 0 else 0,
            "tokens_per_line": token_count / line_count if line_count > 0 else 0
        }

        logger.debug(f"Token stats: {stats}")
        return stats


# Global instance for convenience
_default_estimator = None


def get_token_estimator(model: str = "gpt-4") -> TokenEstimator:
    """
    Get or create default TokenEstimator instance

    Args:
        model: Model name for token encoding

    Returns:
        TokenEstimator: Token estimator instance
    """
    global _default_estimator
    if _default_estimator is None:
        _default_estimator = TokenEstimator(model)
    return _default_estimator


def estimate_tokens(text: str, model: str = "gpt-4") -> int:
    """
    Convenience function to estimate tokens

    Args:
        text: Text to estimate tokens for
        model: Model name for token encoding

    Returns:
        int: Estimated token count
    """
    estimator = get_token_estimator(model)
    return estimator.estimate_tokens(text)


def select_wrapper_mode(
    expected_tokens: int,
    has_specific_format: bool = False
) -> str:
    """
    Convenience function to select wrapper mode

    Args:
        expected_tokens: Expected output token count
        has_specific_format: Whether step has specific format requirements

    Returns:
        str: Recommended wrapper mode
    """
    estimator = get_token_estimator()
    return estimator.select_wrapper_mode(expected_tokens, has_specific_format)
