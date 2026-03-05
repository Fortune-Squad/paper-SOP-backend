"""
D-C Protocol — Divergence-Convergence data structures.

Phase F implements the standardised protocol for Gemini divergence (Phase D)
followed by ChatGPT convergence ruling (Phase C).

Data structures:
  - UnifiedDCCard:       single hypothesis card (Phase D output → Phase C input)
  - DCTrajectoryRecord:  aggregate statistics after a D-C round
  - DCProtocol:          validation + trajectory computation helpers

Design: stdlib-only, zero third-party deps.  All dataclasses support
``dataclasses.asdict()`` for JSON serialisation.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional
import json

logger = logging.getLogger(__name__)


# ── UnifiedDCCard ────────────────────────────────────────────────────

@dataclass
class UnifiedDCCard:
    """D-C Protocol unified hypothesis card.

    Created by Gemini during Phase D (divergence), then judged by ChatGPT
    during Phase C (convergence).
    """

    # === Required (unified interface) ===
    card_id: str                                # "DC-{module}-{nn}"
    hypothesis: str                             # one-sentence hypothesis
    falsifiable_test: str                       # how to falsify (must be executable)
    evidence_level: str                         # OBSERVED | DERIVED | SPECULATIVE
    term_provenance: List[Dict] = field(default_factory=list)
    # [{term, first_seen, status: CONFIRMED|TERM_UNCERTAIN}]

    # === Optional (module extensions) ===
    causal_status: Optional[str] = None         # ASSOCIATION_ONLY | CAUSAL_CANDIDATE
    evidence_hooks: Optional[List[str]] = None  # verification paths
    source_module: Optional[str] = None
    gemini_temperature: Optional[float] = None

    # === Phase C verdict (filled by ChatGPT) ===
    verdict: Optional[str] = None               # ADOPT | FLAG | REJECT
    verdict_reason: Optional[str] = None
    confidence: Optional[str] = None            # LOW | MED | HIGH
    next_action: Optional[str] = None           # "downstream" | "hil_ticket" | "trajectory_archive"
    blocking_reasons: Optional[List[str]] = None
    validity_label: Optional[str] = None        # OK | WEAK | INVALID

    def to_dict(self) -> dict:
        """Serialise to plain dict (JSON-safe)."""
        return asdict(self)

    def to_json(self) -> str:
        """Serialise to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> UnifiedDCCard:
        """Reconstruct from dict."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ── DCTrajectoryRecord ───────────────────────────────────────────────

@dataclass
class DCTrajectoryRecord:
    """Aggregate statistics for one D-C round."""
    dc_cards_total: int = 0
    dc_cards_adopted: int = 0
    dc_cards_flagged: int = 0
    dc_cards_rejected: int = 0
    cross_domain_ratio: float = 0.0
    gemini_temperature: float = 0.0
    waste_rate: float = 0.0               # REJECT / total
    novel_terms_generated: int = 0
    novel_terms_confirmed: int = 0
    source_module: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ── DCProtocol ───────────────────────────────────────────────────────

class DCProtocol:
    """D-C Protocol validation and trajectory computation."""

    VALID_EVIDENCE_LEVELS = {"OBSERVED", "DERIVED", "SPECULATIVE"}
    VALID_VERDICTS = {"ADOPT", "FLAG", "REJECT"}
    VALID_CONFIDENCE = {"LOW", "MED", "HIGH"}

    @staticmethod
    def validate_card(card: UnifiedDCCard) -> List[str]:
        """Validate a card, return list of errors (empty = valid)."""
        errors: List[str] = []
        if not card.card_id:
            errors.append("card_id is required")
        if not card.hypothesis:
            errors.append("hypothesis is required")
        if not card.falsifiable_test:
            errors.append("falsifiable_test is required")
        if card.evidence_level not in DCProtocol.VALID_EVIDENCE_LEVELS:
            errors.append(f"evidence_level must be one of {DCProtocol.VALID_EVIDENCE_LEVELS}")
        if card.verdict and card.verdict not in DCProtocol.VALID_VERDICTS:
            errors.append(f"verdict must be one of {DCProtocol.VALID_VERDICTS}")
        if card.confidence and card.confidence not in DCProtocol.VALID_CONFIDENCE:
            errors.append(f"confidence must be one of {DCProtocol.VALID_CONFIDENCE}")
        return errors

    @staticmethod
    def compute_trajectory(
        cards: List[UnifiedDCCard],
        gemini_temperature: float = 1.0,
        source_module: str = "",
    ) -> DCTrajectoryRecord:
        """Compute aggregate trajectory from a batch of judged cards."""
        total = len(cards)
        adopted = sum(1 for c in cards if c.verdict == "ADOPT")
        flagged = sum(1 for c in cards if c.verdict == "FLAG")
        rejected = sum(1 for c in cards if c.verdict == "REJECT")

        # Cross-domain: cards with TERM_UNCERTAIN provenance
        cross_domain = sum(
            1 for c in cards
            if any(t.get("status") == "TERM_UNCERTAIN" for t in (c.term_provenance or []))
        )

        novel_terms = sum(
            len([t for t in (c.term_provenance or []) if t.get("status") == "TERM_UNCERTAIN"])
            for c in cards
        )
        confirmed_terms = sum(
            len([t for t in (c.term_provenance or []) if t.get("status") == "CONFIRMED"])
            for c in cards
        )

        record = DCTrajectoryRecord(
            dc_cards_total=total,
            dc_cards_adopted=adopted,
            dc_cards_flagged=flagged,
            dc_cards_rejected=rejected,
            cross_domain_ratio=cross_domain / total if total > 0 else 0.0,
            gemini_temperature=gemini_temperature,
            waste_rate=rejected / total if total > 0 else 0.0,
            novel_terms_generated=novel_terms,
            novel_terms_confirmed=confirmed_terms,
            source_module=source_module,
        )

        logger.info(
            "compute_trajectory: total=%d adopt=%d flag=%d reject=%d waste=%.1f%% module=%s",
            total, adopted, flagged, rejected,
            record.waste_rate * 100, source_module,
        )

        return record

    @staticmethod
    def create_hil_ticket(card: UnifiedDCCard, project_path: str) -> str:
        """Create a HIL ticket for a FLAG verdict card.

        Writes a JSON ticket file to ``{project_path}/hil/tickets/`` that is
        compatible with the existing HILService format.

        Returns the generated ticket_id.
        """
        ticket_id = f"hil_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        ticket_data = {
            "ticket_id": ticket_id,
            "project_id": os.path.basename(project_path),
            "step_id": f"dc_protocol:{card.card_id}",
            "question_type": "validation",
            "question": (
                f"D-C card '{card.card_id}' received FLAG verdict. "
                f"Hypothesis: {card.hypothesis[:200]}. "
                f"Reason: {card.verdict_reason or 'N/A'}. "
                f"Please review and decide."
            ),
            "context": {
                "card_id": card.card_id,
                "hypothesis": card.hypothesis,
                "verdict": card.verdict,
                "verdict_reason": card.verdict_reason,
                "confidence": card.confidence,
                "blocking_reasons": card.blocking_reasons or [],
                "evidence_level": card.evidence_level,
                "source_module": card.source_module,
            },
            "options": ["Adopt anyway", "Reject", "Request more evidence"],
            "default_answer": None,
            "priority": "high",
            "blocking": True,
            "status": "pending",
            "answer": None,
            "explanation": None,
            "confidence": None,
            "created_at": now.isoformat(),
            "expires_at": None,
            "answered_at": None,
            "metadata": {"source": "dc_protocol"},
        }

        tickets_dir = os.path.join(project_path, "hil", "tickets")
        os.makedirs(tickets_dir, exist_ok=True)
        ticket_path = os.path.join(tickets_dir, f"{ticket_id}.json")

        with open(ticket_path, "w", encoding="utf-8") as f:
            json.dump(ticket_data, f, ensure_ascii=False, indent=2)

        logger.info(
            "HIL ticket created for FLAG card: %s (card=%s)",
            ticket_id, card.card_id,
        )
        return ticket_id
