"""
HIL (Human-in-the-Loop) Service

Manages HIL tickets for requesting human input during AI execution.
"""

import uuid
import json
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from pathlib import Path

from app.models.hil import (
    HILTicket,
    HILTicketCreate,
    HILTicketAnswer,
    HILTicketSummary,
    TicketStatus,
    TicketPriority,
    QuestionType
)
from app.config import PROJECTS_PATH


class HILService:
    """Service for managing HIL tickets"""

    def __init__(self):
        self.tickets_dir = Path(PROJECTS_PATH) / "hil_tickets"
        self.tickets_dir.mkdir(parents=True, exist_ok=True)

    def _get_ticket_path(self, ticket_id: str) -> Path:
        """Get path to ticket file"""
        return self.tickets_dir / f"{ticket_id}.json"

    def _get_project_tickets_dir(self, project_id: str) -> Path:
        """Get directory for project tickets"""
        project_dir = self.tickets_dir / project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        return project_dir

    async def create_ticket(self, ticket_create: HILTicketCreate) -> HILTicket:
        """Create a new HIL ticket"""
        ticket_id = f"hil_{uuid.uuid4().hex[:12]}"

        # Calculate expiration time
        expires_at = None
        if ticket_create.timeout_hours:
            expires_at = datetime.now() + timedelta(hours=ticket_create.timeout_hours)

        # Create ticket
        ticket = HILTicket(
            ticket_id=ticket_id,
            project_id=ticket_create.project_id,
            step_id=ticket_create.step_id,
            question_type=ticket_create.question_type,
            question=ticket_create.question,
            context=ticket_create.context,
            options=ticket_create.options,
            default_answer=ticket_create.default_answer,
            priority=ticket_create.priority,
            blocking=ticket_create.blocking,
            status=TicketStatus.PENDING,
            created_at=datetime.now(),
            expires_at=expires_at,
            metadata=ticket_create.metadata
        )

        # Save ticket
        await self._save_ticket(ticket)

        return ticket

    async def _save_ticket(self, ticket: HILTicket):
        """Save ticket to file"""
        ticket_path = self._get_ticket_path(ticket.ticket_id)

        # Also save in project directory for easy lookup
        project_ticket_path = self._get_project_tickets_dir(ticket.project_id) / f"{ticket.ticket_id}.json"

        ticket_data = ticket.model_dump(mode='json')

        # Convert datetime to ISO format
        for key in ['created_at', 'expires_at', 'answered_at']:
            if ticket_data.get(key):
                if isinstance(ticket_data[key], datetime):
                    ticket_data[key] = ticket_data[key].isoformat()

        # Save to both locations
        with open(ticket_path, 'w', encoding='utf-8') as f:
            json.dump(ticket_data, f, indent=2, ensure_ascii=False)

        with open(project_ticket_path, 'w', encoding='utf-8') as f:
            json.dump(ticket_data, f, indent=2, ensure_ascii=False)

    async def _load_ticket(self, ticket_id: str) -> Optional[HILTicket]:
        """Load ticket from file"""
        ticket_path = self._get_ticket_path(ticket_id)

        if not ticket_path.exists():
            return None

        with open(ticket_path, 'r', encoding='utf-8') as f:
            ticket_data = json.load(f)

        # Convert ISO format to datetime
        for key in ['created_at', 'expires_at', 'answered_at']:
            if ticket_data.get(key):
                ticket_data[key] = datetime.fromisoformat(ticket_data[key])

        return HILTicket(**ticket_data)

    async def get_ticket(self, ticket_id: str) -> Optional[HILTicket]:
        """Get ticket by ID"""
        return await self._load_ticket(ticket_id)

    async def list_tickets(
        self,
        project_id: str,
        status: Optional[TicketStatus] = None,
        priority: Optional[TicketPriority] = None,
        step_id: Optional[str] = None,
        include_expired: bool = False
    ) -> List[HILTicketSummary]:
        """List tickets for a project with optional filters"""
        project_dir = self._get_project_tickets_dir(project_id)

        tickets = []
        for ticket_file in project_dir.glob("*.json"):
            with open(ticket_file, 'r', encoding='utf-8') as f:
                ticket_data = json.load(f)

            # Convert datetime strings
            for key in ['created_at', 'answered_at']:
                if ticket_data.get(key):
                    ticket_data[key] = datetime.fromisoformat(ticket_data[key])

            # Apply filters
            if status and ticket_data['status'] != status:
                continue
            if priority and ticket_data['priority'] != priority:
                continue
            if step_id and ticket_data['step_id'] != step_id:
                continue

            # Filter expired tickets if not included
            if not include_expired and ticket_data.get('timeout_hours'):
                created_at = ticket_data['created_at']
                timeout_hours = ticket_data['timeout_hours']
                if datetime.now() > created_at + timedelta(hours=timeout_hours):
                    continue

            tickets.append(HILTicketSummary(**ticket_data))

        # Sort by created_at descending
        tickets.sort(key=lambda t: t.created_at, reverse=True)

        return tickets

    async def answer_ticket(
        self,
        ticket_id: str,
        answer: HILTicketAnswer
    ) -> HILTicket:
        """Answer a ticket"""
        ticket = await self._load_ticket(ticket_id)

        if not ticket:
            raise ValueError(f"Ticket {ticket_id} not found")

        if ticket.status != TicketStatus.PENDING:
            raise ValueError(f"Ticket {ticket_id} is not pending (status: {ticket.status})")

        # Update ticket
        ticket.status = TicketStatus.ANSWERED
        ticket.answer = answer.answer
        ticket.explanation = answer.explanation
        ticket.confidence = answer.confidence
        ticket.answered_at = datetime.now()

        if answer.metadata:
            if not ticket.metadata:
                ticket.metadata = {}
            ticket.metadata.update(answer.metadata)

        # Save updated ticket
        await self._save_ticket(ticket)

        return ticket

    async def cancel_ticket(self, ticket_id: str) -> HILTicket:
        """Cancel a ticket"""
        ticket = await self._load_ticket(ticket_id)

        if not ticket:
            raise ValueError(f"Ticket {ticket_id} not found")

        if ticket.status != TicketStatus.PENDING:
            raise ValueError(f"Ticket {ticket_id} is not pending (status: {ticket.status})")

        # Update ticket
        ticket.status = TicketStatus.CANCELLED
        ticket.answered_at = datetime.now()

        # Save updated ticket
        await self._save_ticket(ticket)

        return ticket

    async def get_pending_tickets(self, project_id: str) -> List[HILTicket]:
        """Get all pending tickets for a project"""
        summaries = await self.list_tickets(project_id, status=TicketStatus.PENDING)

        tickets = []
        for summary in summaries:
            ticket = await self._load_ticket(summary.ticket_id)
            if ticket:
                tickets.append(ticket)

        return tickets

    async def get_blocking_tickets(self, project_id: str) -> List[HILTicket]:
        """Get all blocking pending tickets for a project"""
        pending = await self.get_pending_tickets(project_id)
        return [t for t in pending if t.blocking]

    async def process_expired_tickets(self) -> Dict[str, int]:
        """Process expired tickets (auto-answer with default or mark as expired)"""
        now = datetime.now()
        processed = 0
        expired = 0
        auto_answered = 0

        # Scan all ticket files
        for ticket_file in self.tickets_dir.glob("**/*.json"):
            if ticket_file.parent == self.tickets_dir:
                # This is a main ticket file
                with open(ticket_file, 'r', encoding='utf-8') as f:
                    ticket_data = json.load(f)

                # Check if expired
                if ticket_data['status'] == 'pending' and ticket_data.get('expires_at'):
                    expires_at = datetime.fromisoformat(ticket_data['expires_at'])

                    if now > expires_at:
                        ticket = await self._load_ticket(ticket_data['ticket_id'])

                        if ticket:
                            expired += 1

                            # Auto-answer with default if available
                            if ticket.default_answer:
                                await self.answer_ticket(
                                    ticket.ticket_id,
                                    HILTicketAnswer(
                                        answer=ticket.default_answer,
                                        explanation="Auto-answered due to timeout",
                                        confidence=0.5
                                    )
                                )
                                auto_answered += 1
                            else:
                                # Mark as expired
                                ticket.status = TicketStatus.EXPIRED
                                ticket.answered_at = now
                                await self._save_ticket(ticket)

                            processed += 1

        return {
            "processed": processed,
            "expired": expired,
            "auto_answered": auto_answered
        }
