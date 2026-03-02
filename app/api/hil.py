"""
HIL (Human-in-the-Loop) Ticket API Endpoints

Provides REST API for managing HIL tickets:
- Create tickets
- List tickets (with filtering)
- Get ticket details
- Answer tickets
- Cancel tickets
- Get pending/blocking tickets

v6.0 Phase 1: API Integration
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from datetime import datetime

from app.models.hil import (
    HILTicket,
    HILTicketCreate,
    HILTicketAnswer,
    HILTicketSummary,
    TicketStatus,
    TicketPriority
)
from app.services.hil_service import HILService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["hil"])


@router.post("/projects/{project_id}/hil/tickets", response_model=HILTicket)
async def create_hil_ticket(
    project_id: str,
    ticket_create: HILTicketCreate
) -> HILTicket:
    """
    Create a new HIL Ticket

    Args:
        project_id: Project ID
        ticket_create: Ticket creation data

    Returns:
        Created HIL Ticket
    """
    try:
        # Validate project_id matches
        if ticket_create.project_id != project_id:
            raise HTTPException(
                status_code=400,
                detail=f"Project ID mismatch: {ticket_create.project_id} != {project_id}"
            )

        hil_service = HILService()
        ticket = await hil_service.create_ticket(ticket_create)

        logger.info(f"Created HIL ticket {ticket.ticket_id} for project {project_id}")
        return ticket

    except Exception as e:
        logger.error(f"Failed to create HIL ticket: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_id}/hil/tickets", response_model=List[HILTicketSummary])
async def list_hil_tickets(
    project_id: str,
    status: Optional[TicketStatus] = Query(None, description="Filter by status"),
    priority: Optional[TicketPriority] = Query(None, description="Filter by priority"),
    include_expired: bool = Query(False, description="Include expired tickets")
) -> List[HILTicketSummary]:
    """
    List HIL Tickets for a project

    Args:
        project_id: Project ID
        status: Optional status filter
        priority: Optional priority filter
        include_expired: Whether to include expired tickets

    Returns:
        List of ticket summaries
    """
    try:
        hil_service = HILService()
        tickets = await hil_service.list_tickets(
            project_id=project_id,
            status=status,
            priority=priority,
            include_expired=include_expired
        )

        logger.info(f"Listed {len(tickets)} HIL tickets for project {project_id}")
        return tickets

    except Exception as e:
        logger.error(f"Failed to list HIL tickets: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hil/tickets/{ticket_id}", response_model=HILTicket)
async def get_hil_ticket(ticket_id: str) -> HILTicket:
    """
    Get HIL Ticket details

    Args:
        ticket_id: Ticket ID

    Returns:
        HIL Ticket details
    """
    try:
        hil_service = HILService()
        ticket = await hil_service.get_ticket(ticket_id)

        if not ticket:
            raise HTTPException(
                status_code=404,
                detail=f"HIL ticket {ticket_id} not found"
            )

        logger.info(f"Retrieved HIL ticket {ticket_id}")
        return ticket

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get HIL ticket: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/hil/tickets/{ticket_id}/answer", response_model=HILTicket)
async def answer_hil_ticket(
    ticket_id: str,
    answer: HILTicketAnswer
) -> HILTicket:
    """
    Answer a HIL Ticket

    Args:
        ticket_id: Ticket ID
        answer: Ticket answer

    Returns:
        Updated HIL Ticket
    """
    try:
        hil_service = HILService()
        ticket = await hil_service.answer_ticket(ticket_id, answer)

        if not ticket:
            raise HTTPException(
                status_code=404,
                detail=f"HIL ticket {ticket_id} not found"
            )

        logger.info(f"Answered HIL ticket {ticket_id}")
        return ticket

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to answer HIL ticket: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/hil/tickets/{ticket_id}/cancel", response_model=HILTicket)
async def cancel_hil_ticket(ticket_id: str) -> HILTicket:
    """
    Cancel a HIL Ticket

    Args:
        ticket_id: Ticket ID

    Returns:
        Cancelled HIL Ticket
    """
    try:
        hil_service = HILService()
        ticket = await hil_service.cancel_ticket(ticket_id)

        if not ticket:
            raise HTTPException(
                status_code=404,
                detail=f"HIL ticket {ticket_id} not found"
            )

        logger.info(f"Cancelled HIL ticket {ticket_id}")
        return ticket

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to cancel HIL ticket: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_id}/hil/pending", response_model=List[HILTicket])
async def get_pending_tickets(project_id: str) -> List[HILTicket]:
    """
    Get pending HIL Tickets for a project

    Args:
        project_id: Project ID

    Returns:
        List of pending tickets
    """
    try:
        hil_service = HILService()
        tickets = await hil_service.get_pending_tickets(project_id)

        logger.info(f"Retrieved {len(tickets)} pending HIL tickets for project {project_id}")
        return tickets

    except Exception as e:
        logger.error(f"Failed to get pending HIL tickets: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_id}/hil/blocking", response_model=List[HILTicket])
async def get_blocking_tickets(project_id: str) -> List[HILTicket]:
    """
    Get blocking HIL Tickets for a project

    Args:
        project_id: Project ID

    Returns:
        List of blocking tickets (CRITICAL priority, PENDING status)
    """
    try:
        hil_service = HILService()
        tickets = await hil_service.get_blocking_tickets(project_id)

        logger.info(f"Retrieved {len(tickets)} blocking HIL tickets for project {project_id}")
        return tickets

    except Exception as e:
        logger.error(f"Failed to get blocking HIL tickets: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/hil/process-expired", response_model=dict)
async def process_expired_tickets() -> dict:
    """
    Process expired HIL Tickets (admin endpoint)

    Returns:
        Number of tickets processed
    """
    try:
        hil_service = HILService()
        count = await hil_service.process_expired_tickets()

        logger.info(f"Processed {count} expired HIL tickets")
        return {
            "success": True,
            "processed_count": count,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to process expired HIL tickets: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
