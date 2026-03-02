"""
Bootloader Confirmation Service

This service manages the Bootloader confirmation workflow (Loop1):
- Update user-edited Bootloader outputs
- Regenerate Bootloader with new focus areas
- Confirm Bootloader outputs and proceed to Step 0

v6.0 Phase 3: User Experience Optimization
"""

import logging
from typing import List, Optional
from datetime import datetime

from app.models.bootloader import DomainDictionary, OOTCandidates, ResourceCard, BootloaderResult
from app.models.project import Project, StepStatus
from app.services.bootloader_service import get_bootloader_service
from app.services.project_manager import ProjectManager

logger = logging.getLogger(__name__)


class BootloaderConfirmationService:
    """Manages Bootloader confirmation workflow (Loop1: Definition Alignment)"""

    def __init__(self):
        self.bootloader_service = get_bootloader_service()
        self.project_manager = ProjectManager()

    async def update_outputs(
        self,
        project_id: str,
        domain_dictionary: Optional[DomainDictionary] = None,
        oot_candidates: Optional[OOTCandidates] = None,
        resource_card: Optional[ResourceCard] = None
    ) -> bool:
        """
        Save user-edited Bootloader outputs.

        Args:
            project_id: Project ID
            domain_dictionary: Edited domain dictionary (optional)
            oot_candidates: Edited OOT candidates (optional)
            resource_card: Edited resource card (optional)

        Returns:
            bool: Success status
        """
        try:
            logger.info(f"Updating Bootloader outputs for project {project_id}")

            # Load project
            project = await self.project_manager.load_project(project_id)
            if not project:
                logger.error(f"Project not found: {project_id}")
                return False

            # Verify step_s_1 exists and is in correct state
            if "step_s_1" not in project.steps:
                logger.error(f"step_s_1 not found in project {project_id}")
                return False

            step_status = project.steps["step_s_1"].status
            if step_status not in [StepStatus.COMPLETED, StepStatus.IN_PROGRESS]:
                logger.error(f"Cannot update outputs - step_s_1 status is {step_status}")
                return False

            # Update documents using Step_S1_Bootloader methods
            from app.steps.step_s1 import Step_S1_Bootloader
            step = Step_S1_Bootloader(project)

            updated_count = 0

            if domain_dictionary:
                await step._save_domain_dictionary(domain_dictionary)
                logger.info(f"Updated Domain Dictionary for project {project_id}")
                updated_count += 1

            if oot_candidates:
                await step._save_oot_candidates(oot_candidates)
                logger.info(f"Updated OOT Candidates for project {project_id}")
                updated_count += 1

            if resource_card:
                await step._save_resource_card(resource_card)
                logger.info(f"Updated Resource Card for project {project_id}")
                updated_count += 1

            # Update metadata
            if "bootloader_edits" not in project.metadata:
                project.metadata["bootloader_edits"] = []

            project.metadata["bootloader_edits"].append({
                "timestamp": datetime.now().isoformat(),
                "updated_documents": updated_count
            })

            await self.project_manager._save_project(project)

            logger.info(f"Successfully updated {updated_count} Bootloader outputs for project {project_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to update Bootloader outputs: {e}")
            return False

    async def regenerate_bootloader(
        self,
        project_id: str,
        focus_areas: Optional[List[str]] = None
    ) -> BootloaderResult:
        """
        Regenerate Bootloader outputs with new focus areas.

        Args:
            project_id: Project ID
            focus_areas: Optional list of focus areas (e.g., ["datasets", "tools"])

        Returns:
            BootloaderResult: New Bootloader outputs
        """
        try:
            logger.info(f"Regenerating Bootloader for project {project_id} with focus: {focus_areas}")

            # Load project
            project = await self.project_manager.load_project(project_id)
            if not project:
                raise ValueError(f"Project not found: {project_id}")

            # Run Bootloader with focus areas
            result = await self.bootloader_service.run_bootloader(
                domain=project.config.topic,
                context=project.config.project_context,
                constraints="\n".join(project.config.hard_constraints) if project.config.hard_constraints else None,
                focus_areas=focus_areas
            )

            # Update metadata
            if "bootloader_regenerations" not in project.metadata:
                project.metadata["bootloader_regenerations"] = []

            project.metadata["bootloader_regenerations"].append({
                "timestamp": datetime.now().isoformat(),
                "focus_areas": focus_areas or []
            })

            await self.project_manager._save_project(project)

            logger.info(f"Successfully regenerated Bootloader for project {project_id}")
            return result

        except Exception as e:
            logger.error(f"Failed to regenerate Bootloader: {e}")
            raise

    async def confirm_and_proceed(self, project_id: str) -> Project:
        """
        Mark Bootloader as confirmed and proceed to Step 0.

        This completes the Loop1 (Definition Alignment) confirmation.

        Args:
            project_id: Project ID

        Returns:
            Project: Updated project object
        """
        try:
            logger.info(f"Confirming Bootloader for project {project_id}")

            # Load project
            project = await self.project_manager.load_project(project_id)
            if not project:
                raise ValueError(f"Project not found: {project_id}")

            # Verify step_s_1 is completed
            if "step_s_1" not in project.steps:
                raise ValueError(f"step_s_1 not found in project {project_id}")

            step_status = project.steps["step_s_1"].status
            if step_status != StepStatus.COMPLETED:
                raise ValueError(f"Cannot confirm - step_s_1 status is {step_status}, must be COMPLETED")

            # Update project state
            project.current_step = "step_0_1"

            # Mark as confirmed in metadata
            project.metadata["bootloader_confirmed"] = True
            project.metadata["bootloader_confirmed_at"] = datetime.now().isoformat()

            await self.project_manager._save_project(project)

            logger.info(f"Successfully confirmed Bootloader for project {project_id}, proceeding to step_0_1")
            return project

        except Exception as e:
            logger.error(f"Failed to confirm Bootloader: {e}")
            raise


# Singleton instance
_bootloader_confirmation_service_instance = None


def get_bootloader_confirmation_service() -> BootloaderConfirmationService:
    """Get singleton BootloaderConfirmationService instance"""
    global _bootloader_confirmation_service_instance
    if _bootloader_confirmation_service_instance is None:
        _bootloader_confirmation_service_instance = BootloaderConfirmationService()
    return _bootloader_confirmation_service_instance
