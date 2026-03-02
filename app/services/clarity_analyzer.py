"""
Input Clarity Analyzer Service

This service analyzes the clarity of user input (topic, context, constraints)
and provides recommendations on whether to run the Bootloader.

Uses a hybrid approach:
- 60% rule-based heuristics (length, specificity, technical terms)
- 40% ChatGPT judgment (subjective clarity assessment)

v6.0 Phase 3: User Experience Optimization
"""

import logging
from typing import List, Optional

from app.models.clarity import InputClarityScore
from app.services.ai_client import create_chatgpt_client

logger = logging.getLogger(__name__)


class InputClarityAnalyzer:
    """Analyzes input clarity and recommends Bootloader usage"""

    def __init__(self):
        self.ai_client = create_chatgpt_client()

    async def analyze_input_clarity(
        self,
        topic: str,
        context: Optional[str],
        constraints: List[str],
        keywords: List[str]
    ) -> InputClarityScore:
        """
        Analyze input clarity using hybrid approach.

        Args:
            topic: Research topic string
            context: Optional project context/background
            constraints: List of hard constraints
            keywords: List of keywords

        Returns:
            InputClarityScore with scores and recommendation
        """
        logger.info(f"Analyzing input clarity for topic: {topic[:50]}...")

        # 1. Calculate component scores using rules
        topic_score = self._calculate_topic_clarity(topic, keywords)
        context_score = self._calculate_context_clarity(context)
        constraint_score = self._calculate_constraint_clarity(constraints)

        logger.info(f"Rule-based scores - Topic: {topic_score:.1f}, Context: {context_score:.1f}, Constraint: {constraint_score:.1f}")

        # 2. Get AI judgment
        ai_score = await self._get_ai_judgment(topic, context, constraints)
        logger.info(f"AI judgment score: {ai_score:.1f}")

        # 3. Combine scores (60% rules + 40% AI)
        rule_based_avg = (topic_score + context_score + constraint_score) / 3
        overall = rule_based_avg * 0.6 + ai_score * 0.4

        logger.info(f"Overall clarity score: {overall:.1f} (rule-based: {rule_based_avg:.1f}, AI: {ai_score:.1f})")

        # 4. Make recommendation
        recommendation = self._make_recommendation(overall)
        reasons = self._generate_reasons(topic_score, context_score, constraint_score)

        return InputClarityScore(
            topic_clarity=round(topic_score, 2),
            context_clarity=round(context_score, 2),
            constraint_clarity=round(constraint_score, 2),
            overall_score=round(overall, 2),
            recommendation=recommendation,
            reasons=reasons
        )

    def _calculate_topic_clarity(self, topic: str, keywords: List[str]) -> float:
        """
        Rule-based topic clarity scoring.

        Factors:
        - Length (10-200 chars optimal)
        - Specificity indicators ("for", "on", "using", "with", "in")
        - Keyword density (>=3 keywords)
        """
        score = 50.0  # Base score

        # Length check
        topic_len = len(topic)
        if topic_len < 10:
            score -= 30  # Too short, very vague
        elif topic_len > 200:
            score -= 10  # Too long, may be unfocused
        else:
            score += 10  # Good length

        # Specificity check
        specific_terms = ["for", "on", "using", "with", "in", "based", "via"]
        if any(term in topic.lower() for term in specific_terms):
            score += 20  # Contains specific relationship indicators

        # Keyword density
        if len(keywords) >= 3:
            score += 10  # Good keyword coverage
        elif len(keywords) == 0:
            score -= 10  # No keywords provided

        # Technical term check (simple heuristic: capitalized words, acronyms)
        words = topic.split()
        technical_words = sum(1 for w in words if w.isupper() or (w[0].isupper() and len(w) > 1))
        if technical_words >= 2:
            score += 10  # Contains technical terms

        return min(100.0, max(0.0, score))

    def _calculate_context_clarity(self, context: Optional[str]) -> float:
        """
        Rule-based context clarity scoring.

        Factors:
        - Presence (missing context = low score)
        - Length (longer = more detailed)
        """
        if not context or len(context.strip()) < 20:
            return 30.0  # Low score for missing/short context

        score = 70.0  # Good baseline if context exists

        # Detail level
        context_len = len(context)
        if context_len > 200:
            score += 15  # Very detailed
        elif context_len > 100:
            score += 10  # Moderately detailed

        return min(100.0, score)

    def _calculate_constraint_clarity(self, constraints: List[str]) -> float:
        """
        Rule-based constraint clarity scoring.

        Factors:
        - Number of constraints (more = clearer requirements)
        - Measurability (contains comparison operators or modal verbs)
        """
        if not constraints:
            return 40.0  # Low score for no constraints

        score = 60.0 + len(constraints) * 8  # More constraints = clearer

        # Check for measurable constraints
        measurable_indicators = [">", "<", ">=", "<=", "must", "should", "require", "need"]
        measurable = any(
            any(indicator in c.lower() for indicator in measurable_indicators)
            for c in constraints
        )
        if measurable:
            score += 20  # Contains measurable/specific constraints

        return min(100.0, score)

    async def _get_ai_judgment(
        self,
        topic: str,
        context: Optional[str],
        constraints: List[str]
    ) -> float:
        """
        Use ChatGPT to judge input clarity.

        Returns a score from 0-100 based on AI's subjective assessment.
        """
        prompt = f"""Analyze the clarity of this research project input:

Topic: {topic}
Context: {context or "Not provided"}
Constraints: {", ".join(constraints) if constraints else "None"}

Rate the clarity from 0-100:
- 0-30: Very vague (e.g., "machine learning", "组合数学")
- 30-50: Somewhat vague (e.g., "deep learning for images")
- 50-70: Moderately clear (e.g., "CNN for medical image classification")
- 70-90: Clear (e.g., "ResNet-based CT scan tumor detection")
- 90-100: Very clear (specific dataset, method, venue, and constraints)

Consider:
- Topic specificity (generic vs specific)
- Context completeness (background information)
- Constraint measurability (vague vs concrete)

Return ONLY the numeric score (0-100) as a single number, nothing else."""

        try:
            response = await self.ai_client.chat(
                prompt=prompt,
                system_prompt="You are an expert at evaluating research project clarity. You provide objective numeric scores."
            )

            # Parse score
            score_str = response.strip()
            score = float(score_str)

            # Validate range
            if not (0 <= score <= 100):
                logger.warning(f"AI score out of range: {score}, defaulting to 50")
                return 50.0

            return score

        except (ValueError, AttributeError) as e:
            logger.error(f"Failed to parse AI judgment: {e}, defaulting to 50")
            return 50.0  # Default if parsing fails

    def _make_recommendation(self, overall_score: float) -> str:
        """
        Convert overall score to recommendation.

        Thresholds:
        - >= 80: skip_bootloader (clear input)
        - 50-80: review_required (user decides)
        - < 50: run_bootloader (fuzzy input)
        """
        if overall_score >= 80:
            return "skip_bootloader"
        elif overall_score >= 50:
            return "review_required"
        else:
            return "run_bootloader"

    def _generate_reasons(
        self,
        topic_score: float,
        context_score: float,
        constraint_score: float
    ) -> List[str]:
        """Generate specific reasons for the score"""
        reasons = []

        if topic_score < 50:
            reasons.append("Topic is too vague or generic")
        elif topic_score >= 80:
            reasons.append("Topic is clear and specific")

        if context_score < 50:
            reasons.append("Project context is missing or insufficient")
        elif context_score >= 80:
            reasons.append("Project context is detailed and complete")

        if constraint_score < 50:
            reasons.append("Constraints are not clearly defined")
        elif constraint_score >= 80:
            reasons.append("Constraints are well-defined and measurable")

        if not reasons:
            reasons.append("Input is moderately clear")

        return reasons


# Singleton instance
_clarity_analyzer_instance = None


def get_clarity_analyzer() -> InputClarityAnalyzer:
    """Get singleton InputClarityAnalyzer instance"""
    global _clarity_analyzer_instance
    if _clarity_analyzer_instance is None:
        _clarity_analyzer_instance = InputClarityAnalyzer()
    return _clarity_analyzer_instance
