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
v7.1: MEMORY.md write hook on ticket answer
"""

import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query, Depends
from pathlib import Path
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
from app.services.memory_store import MemoryStore
from app.services.project_manager import ProjectManager
from app.middleware.auth import get_current_active_user, require_admin
from app.db.models import User as DBUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["hil"])

project_manager = ProjectManager()


async def _check_project_access(project_id: str, current_user: DBUser):
    """检查项目访问权限"""
    project = await project_manager._load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id}")
    is_admin = current_user.role == "admin"
    if not project_manager.check_project_access(project, str(current_user.id), is_admin):
        raise HTTPException(status_code=403, detail="You don't have permission to access this project")


@router.post("/projects/{project_id}/hil/tickets", response_model=HILTicket)
async def create_hil_ticket(
    project_id: str,
    ticket_create: HILTicketCreate,
    current_user: DBUser = Depends(get_current_active_user)
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

        await _check_project_access(project_id, current_user)

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
    include_expired: bool = Query(False, description="Include expired tickets"),
    current_user: DBUser = Depends(get_current_active_user)
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
        await _check_project_access(project_id, current_user)

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
async def get_hil_ticket(
    ticket_id: str,
    current_user: DBUser = Depends(get_current_active_user)
) -> HILTicket:
    """
    Get HIL Ticket details

    Args:
        ticket_id: Ticket ID
        current_user: 当前认证用户

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

        # 通过 ticket 反查 project_id 校验归属
        await _check_project_access(ticket.project_id, current_user)

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
    answer: HILTicketAnswer,
    current_user: DBUser = Depends(get_current_active_user)
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

        # 先加载 ticket 获取 project_id，校验归属
        pre_ticket = await hil_service.get_ticket(ticket_id)
        if not pre_ticket:
            raise HTTPException(status_code=404, detail=f"HIL ticket {ticket_id} not found")
        await _check_project_access(pre_ticket.project_id, current_user)

        ticket = await hil_service.answer_ticket(ticket_id, answer)

        if not ticket:
            raise HTTPException(
                status_code=404,
                detail=f"HIL ticket {ticket_id} not found"
            )

        logger.info(f"Answered HIL ticket {ticket_id}")

        # v1.2 §7.2: Reset iteration_count after human intervention
        try:
            if ticket.step_id and ticket.step_id.startswith("step_3"):
                # Extract wp_id from metadata or step_id
                wp_id = ticket.metadata.get("wp_id") if ticket.metadata else None
                if wp_id:
                    from app.services.state_store import StateStore
                    state_store = StateStore()
                    if state_store.exists(ticket.project_id):
                        def reset_iteration(state):
                            if wp_id in state.wp_states:
                                state.wp_states[wp_id].iteration_count = 0
                                logger.info(f"v1.2 §7.2: Reset iteration_count for {wp_id} after HIL resolution")
                            return state
                        state_store.update(ticket.project_id, reset_iteration)
        except Exception as iter_err:
            logger.warning(f"Failed to reset iteration_count after HIL: {iter_err}")

        # v7.1: Write decision to MEMORY.md
        try:
            from app.config import settings
            from app.models.hil import QuestionType
            project_id = ticket.project_id
            project_path = str(Path(settings.projects_path) / project_id)
            memory_store = MemoryStore(project_path)
            memory_store.add_decision(
                symptom=f"HIL ticket {ticket_id}: {ticket.question[:100]}",
                correction=f"Human answer: {answer.answer[:100]}",
                source_actor="human",
                wp_id=ticket.wp_id if hasattr(ticket, 'wp_id') and ticket.wp_id else "",
            )
            # v7.1: Write error_pattern for correction-type tickets
            if ticket.question_type in (QuestionType.VALIDATION, QuestionType.FEEDBACK):
                memory_store.add_error_pattern(
                    symptom=f"Human correction on: {ticket.question[:100]}",
                    root_cause=f"Ticket {ticket_id} required human intervention",
                    correction=answer.answer[:200],
                    source_actor="human",
                    wp_id=ticket.wp_id if hasattr(ticket, 'wp_id') and ticket.wp_id else "",
                )
        except Exception as mem_err:
            logger.warning(f"Failed to write MEMORY.md hook: {mem_err}")

        return ticket

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to answer HIL ticket: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/hil/tickets/{ticket_id}/cancel", response_model=HILTicket)
async def cancel_hil_ticket(
    ticket_id: str,
    current_user: DBUser = Depends(get_current_active_user)
) -> HILTicket:
    """
    Cancel a HIL Ticket

    Args:
        ticket_id: Ticket ID
        current_user: 当前认证用户

    Returns:
        Cancelled HIL Ticket
    """
    try:
        hil_service = HILService()

        # 先加载 ticket 获取 project_id，校验归属
        pre_ticket = await hil_service.get_ticket(ticket_id)
        if not pre_ticket:
            raise HTTPException(status_code=404, detail=f"HIL ticket {ticket_id} not found")
        await _check_project_access(pre_ticket.project_id, current_user)

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
async def get_pending_tickets(
    project_id: str,
    current_user: DBUser = Depends(get_current_active_user)
) -> List[HILTicket]:
    """
    Get pending HIL Tickets for a project

    Args:
        project_id: Project ID
        current_user: 当前认证用户

    Returns:
        List of pending tickets
    """
    try:
        await _check_project_access(project_id, current_user)

        hil_service = HILService()
        tickets = await hil_service.get_pending_tickets(project_id)

        logger.info(f"Retrieved {len(tickets)} pending HIL tickets for project {project_id}")
        return tickets

    except Exception as e:
        logger.error(f"Failed to get pending HIL tickets: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/projects/{project_id}/hil/blocking", response_model=List[HILTicket])
async def get_blocking_tickets(
    project_id: str,
    current_user: DBUser = Depends(get_current_active_user)
) -> List[HILTicket]:
    """
    Get blocking HIL Tickets for a project

    Args:
        project_id: Project ID
        current_user: 当前认证用户

    Returns:
        List of blocking tickets (CRITICAL priority, PENDING status)
    """
    try:
        await _check_project_access(project_id, current_user)

        hil_service = HILService()
        tickets = await hil_service.get_blocking_tickets(project_id)

        logger.info(f"Retrieved {len(tickets)} blocking HIL tickets for project {project_id}")
        return tickets

    except Exception as e:
        logger.error(f"Failed to get blocking HIL tickets: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/hil/process-expired", response_model=dict)
async def process_expired_tickets(
    current_user: DBUser = Depends(require_admin)
) -> dict:
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
