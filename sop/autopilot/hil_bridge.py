from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from .ledger import append_event
from .recovery import atomic_write_json

logger = logging.getLogger(__name__)


# ── Enums ────────────────────────────────────────────────────────────


class HILRequestType(str, Enum):
    APPROVE = "approve"
    UPLOAD = "upload"
    OVERRIDE = "override"
    REVIEW = "review"
    DECIDE = "decide"
    ANOMALY_REVIEW = "anomaly_review"


class HILStatus(str, Enum):
    PENDING = "pending"
    ANSWERED = "answered"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class HILDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    OVERRIDE = "override"
    DEFER = "defer"


# ── Helpers ──────────────────────────────────────────────────────────


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


# ── HILResponse ──────────────────────────────────────────────────────


@dataclass
class HILResponse:
    decision: HILDecision
    comment: str = ""
    override_value: Any = None
    answered_at: str = ""

    def __post_init__(self) -> None:
        if not self.answered_at:
            self.answered_at = _utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "comment": self.comment,
            "override_value": self.override_value,
            "answered_at": self.answered_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HILResponse:
        return cls(
            decision=HILDecision(data["decision"]),
            comment=str(data.get("comment", "")),
            override_value=data.get("override_value"),
            answered_at=str(data.get("answered_at", "")),
        )


# ── HILTicket ────────────────────────────────────────────────────────


@dataclass
class HILTicket:
    ticket_id: str
    run_id: str
    request_type: HILRequestType
    message: str
    context: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    deadline: str = ""
    status: HILStatus = HILStatus.PENDING
    response: HILResponse | None = None

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = _utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "run_id": self.run_id,
            "request_type": self.request_type.value,
            "message": self.message,
            "context": dict(self.context),
            "created_at": self.created_at,
            "deadline": self.deadline,
            "status": self.status.value,
            "response": self.response.to_dict() if self.response else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HILTicket:
        raw_response = data.get("response")
        response: HILResponse | None = None
        if isinstance(raw_response, dict):
            response = HILResponse.from_dict(raw_response)

        return cls(
            ticket_id=str(data["ticket_id"]),
            run_id=str(data["run_id"]),
            request_type=HILRequestType(data["request_type"]),
            message=str(data["message"]),
            context=dict(data.get("context") or {}),
            created_at=str(data.get("created_at", "")),
            deadline=str(data.get("deadline", "")),
            status=HILStatus(data.get("status", "pending")),
            response=response,
        )


# ── HILBridge ────────────────────────────────────────────────────────


class HILBridge:
    """Lightweight file-based HIL bridge for the autopilot engine.

    Ticket format is compatible with paper-sop-automation but has zero
    dependency on FastAPI, pydantic, or any paper-sop-automation code.
    Humans respond by editing ``ticket.json`` directly (v1 workflow).
    """

    def __init__(self, inbox_dir: Path, ledger_dir: Path | None = None) -> None:
        self.inbox_dir = Path(inbox_dir)
        self.ledger_dir = Path(ledger_dir) if ledger_dir is not None else None

    # ── create ───────────────────────────────────────────────────────

    def create_ticket(
        self,
        run_id: str,
        request_type: HILRequestType,
        message: str,
        context: dict | None = None,
        deadline_hours: float = 24.0,
    ) -> HILTicket:
        now = _utc_now()
        deadline = now + timedelta(hours=deadline_hours)

        ticket = HILTicket(
            ticket_id=uuid.uuid4().hex,
            run_id=run_id,
            request_type=request_type,
            message=message,
            context=dict(context) if context else {},
            created_at=now.isoformat(),
            deadline=deadline.isoformat(),
        )

        ticket_path = self.inbox_dir / ticket.ticket_id / "ticket.json"
        atomic_write_json(ticket_path, ticket.to_dict())

        if self.ledger_dir is not None:
            append_event(self.ledger_dir, {
                "ts": ticket.created_at,
                "event": "hil_ticket_created",
                "event_type": "hil_ticket_created",
                "program_id": ticket.context.get("program_id", ""),
                "candidate_id": ticket.context.get("candidate_id", ""),
                "execution_type": ticket.context.get("execution_type", ""),
                "bundle_dir": "",
                "run_id": run_id,
                "gate_result": "PENDING",
                "status": "HIL_PENDING",
                "details": {
                    "ticket_id": ticket.ticket_id,
                    "request_type": request_type.value,
                    "message": message[:200],
                    "deadline": ticket.deadline,
                },
            })

        logger.info(
            "HIL ticket %s created for run %s: %s",
            ticket.ticket_id,
            run_id,
            message[:80],
        )
        return ticket

    # ── read / poll ──────────────────────────────────────────────────

    def _load_ticket(self, ticket_id: str) -> HILTicket | None:
        ticket_path = self.inbox_dir / ticket_id / "ticket.json"
        if not ticket_path.exists():
            return None
        try:
            raw = json.loads(ticket_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return HILTicket.from_dict(raw)
        except (json.JSONDecodeError, OSError, KeyError, ValueError) as exc:
            logger.warning("Failed to load ticket %s: %s", ticket_id, exc)
        return None

    def check_response(self, ticket_id: str) -> HILResponse | None:
        ticket = self._load_ticket(ticket_id)
        if ticket is None:
            return None

        # Already answered/cancelled/expired → return response
        if ticket.status != HILStatus.PENDING:
            return ticket.response

        # Check deadline
        if ticket.deadline:
            try:
                deadline_dt = datetime.fromisoformat(ticket.deadline)
                if _utc_now() > deadline_dt:
                    self._mark_expired(ticket)
                    return None
            except ValueError:
                pass

        return None

    def _mark_expired(self, ticket: HILTicket) -> None:
        ticket.status = HILStatus.EXPIRED
        ticket_path = self.inbox_dir / ticket.ticket_id / "ticket.json"
        atomic_write_json(ticket_path, ticket.to_dict())

        if self.ledger_dir is not None:
            append_event(self.ledger_dir, {
                "ts": _utc_now_iso(),
                "event": "hil_ticket_expired",
                "event_type": "hil_ticket_expired",
                "program_id": ticket.context.get("program_id", ""),
                "candidate_id": ticket.context.get("candidate_id", ""),
                "execution_type": "",
                "bundle_dir": "",
                "run_id": ticket.run_id,
                "gate_result": "PENDING",
                "status": "HIL_EXPIRED",
                "details": {"ticket_id": ticket.ticket_id},
            })
        logger.info("HIL ticket %s expired", ticket.ticket_id)

    # ── answer ───────────────────────────────────────────────────────

    def answer_ticket(
        self,
        ticket_id: str,
        decision: HILDecision,
        comment: str = "",
        override_value: Any = None,
    ) -> HILTicket:
        ticket = self._load_ticket(ticket_id)
        if ticket is None:
            raise FileNotFoundError(f"Ticket {ticket_id} not found")

        ticket.response = HILResponse(
            decision=decision,
            comment=comment,
            override_value=override_value,
        )
        ticket.status = HILStatus.ANSWERED

        ticket_path = self.inbox_dir / ticket_id / "ticket.json"
        atomic_write_json(ticket_path, ticket.to_dict())

        if self.ledger_dir is not None:
            append_event(self.ledger_dir, {
                "ts": ticket.response.answered_at,
                "event": "hil_ticket_answered",
                "event_type": "hil_ticket_answered",
                "program_id": ticket.context.get("program_id", ""),
                "candidate_id": ticket.context.get("candidate_id", ""),
                "execution_type": "",
                "bundle_dir": "",
                "run_id": ticket.run_id,
                "gate_result": "PENDING",
                "status": "HIL_ANSWERED",
                "details": {
                    "ticket_id": ticket_id,
                    "decision": decision.value,
                    "comment": comment[:200],
                },
            })

        logger.info("HIL ticket %s answered: %s", ticket_id, decision.value)
        return ticket

    # ── list / expire ────────────────────────────────────────────────

    def list_pending(self) -> list[HILTicket]:
        if not self.inbox_dir.exists():
            return []

        pending: list[HILTicket] = []
        for child in self.inbox_dir.iterdir():
            if not child.is_dir():
                continue
            ticket = self._load_ticket(child.name)
            if ticket is not None and ticket.status == HILStatus.PENDING:
                pending.append(ticket)

        pending.sort(key=lambda t: t.created_at)
        return pending

    def expire_overdue(self) -> list[str]:
        expired_ids: list[str] = []
        now = _utc_now()

        for ticket in self.list_pending():
            if not ticket.deadline:
                continue
            try:
                deadline_dt = datetime.fromisoformat(ticket.deadline)
                if now > deadline_dt:
                    self._mark_expired(ticket)
                    expired_ids.append(ticket.ticket_id)
            except ValueError:
                continue

        return expired_ids
