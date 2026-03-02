"""
Migration Script: v4 Flat Structure → v7 Hierarchical Structure

Migrates existing projects from:
  backend/artifacts/<project_id>/*.md
  projects/<project_id>/documents/*.md (empty)

To:
  projects/<project_id>/artifacts/{category}/*.md
  projects/<project_id>/evidence/
  projects/<project_id>/gates/
  projects/<project_id>/hil/

Usage:
  python scripts/migrate_to_v7_structure.py [--dry-run] [--project-id <id>]
"""
import asyncio
import argparse
import logging
import sys
import os
from pathlib import Path
from typing import List, Dict, Optional
import shutil
import json
from datetime import datetime

# Add parent directory to path for imports
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from app.config.v7_path_mapping import get_step_v7_path
from app.utils.file_manager import FileManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class V7MigrationTool:
    """Tool to migrate projects from v4 to v7 structure"""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        # Use hardcoded paths relative to backend directory
        backend_path = Path(__file__).parent.parent
        self.projects_path = backend_path / "projects"
        self.old_artifacts_path = backend_path / "artifacts"
        self.migration_log: List[Dict] = []

    def find_projects(self) -> List[str]:
        """Find all projects in old artifacts/ directory"""
        if not self.old_artifacts_path.exists():
            logger.warning(f"Old artifacts path not found: {self.old_artifacts_path}")
            return []

        projects = []
        for item in self.old_artifacts_path.iterdir():
            if item.is_dir() and not item.name.startswith(("00_", "01_", "02_", "03_", "04_", "S-1_")):
                # This is a project directory (not a category directory)
                projects.append(item.name)

        logger.info(f"Found {len(projects)} projects to migrate")
        return projects

    def map_step_file_to_v7(self, step_file: Path) -> Optional[str]:
        """
        Map old step file to v7 path

        Args:
            step_file: Path to step file (e.g., step_s0.md)

        Returns:
            Optional[str]: v7 relative path (e.g., "00_intake/00_Project_Intake_Card.md")
        """
        step_id = step_file.stem  # e.g., "step_s0"

        v7_path = get_step_v7_path(step_id)
        if v7_path == f"00_intake/{step_id}.md":
            # Fallback path, no mapping found
            logger.warning(f"No v7 mapping for step: {step_id}")
            return None

        return v7_path

    async def migrate_project(self, project_id: str) -> bool:
        """
        Migrate a single project to v7 structure

        Args:
            project_id: Project ID

        Returns:
            bool: Success status
        """
        logger.info(f"{'[DRY RUN] ' if self.dry_run else ''}Migrating project: {project_id}")

        old_project_path = self.old_artifacts_path / project_id
        new_project_path = self.projects_path / project_id

        if not old_project_path.exists():
            logger.error(f"Old project path not found: {old_project_path}")
            return False

        # Create v7 structure
        if not self.dry_run:
            file_manager = FileManager(structure_version="v7")
            file_manager.ensure_project_structure(project_id)

        # Find all step files
        step_files = list(old_project_path.glob("step_*.md"))
        logger.info(f"Found {len(step_files)} step files to migrate")

        migrated_count = 0
        for step_file in step_files:
            v7_path = self.map_step_file_to_v7(step_file)
            if not v7_path:
                continue

            # Construct new path
            new_file_path = new_project_path / "artifacts" / v7_path

            # Copy file
            if not self.dry_run:
                new_file_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(step_file, new_file_path)
                logger.info(f"  Copied: {step_file.name} → {v7_path}")
            else:
                logger.info(f"  [DRY RUN] Would copy: {step_file.name} → {v7_path}")

            # Log migration
            self.migration_log.append({
                "project_id": project_id,
                "old_path": str(step_file),
                "new_path": str(new_file_path),
                "timestamp": datetime.now().isoformat()
            })

            migrated_count += 1

        logger.info(f"Migrated {migrated_count}/{len(step_files)} files for project {project_id}")
        return True

    async def migrate_all_projects(self, project_ids: Optional[List[str]] = None):
        """
        Migrate all projects or specific projects

        Args:
            project_ids: Optional list of project IDs to migrate
        """
        if project_ids:
            projects = project_ids
        else:
            projects = self.find_projects()

        logger.info(f"Starting migration for {len(projects)} projects")

        success_count = 0
        for project_id in projects:
            try:
                success = await self.migrate_project(project_id)
                if success:
                    success_count += 1
            except Exception as e:
                logger.error(f"Failed to migrate project {project_id}: {e}", exc_info=True)

        logger.info(f"Migration complete: {success_count}/{len(projects)} projects migrated")

        # Save migration log
        if not self.dry_run and self.migration_log:
            log_file = self.projects_path / "migration_log.json"
            with open(log_file, 'w') as f:
                json.dump(self.migration_log, f, indent=2)
            logger.info(f"Migration log saved to: {log_file}")

    def verify_migration(self, project_id: str) -> bool:
        """
        Verify that a project was migrated correctly

        Args:
            project_id: Project ID

        Returns:
            bool: Verification status
        """
        new_project_path = self.projects_path / project_id / "artifacts"

        if not new_project_path.exists():
            logger.error(f"New project path not found: {new_project_path}")
            return False

        # Check that required directories exist
        required_dirs = ["00_intake", "01_research", "02_freeze", "03_spec", "04_frozen"]
        for dir_name in required_dirs:
            dir_path = new_project_path / dir_name
            if not dir_path.exists():
                logger.warning(f"Missing directory: {dir_path}")

        # Count migrated files
        migrated_files = list(new_project_path.rglob("*.md"))
        logger.info(f"Verification: Found {len(migrated_files)} files in new structure")

        # List files by category
        for category in required_dirs:
            category_files = list((new_project_path / category).glob("*.md"))
            if category_files:
                logger.info(f"  {category}: {len(category_files)} files")
                for f in category_files:
                    logger.info(f"    - {f.name}")

        return len(migrated_files) > 0


async def main():
    parser = argparse.ArgumentParser(description="Migrate projects to v7 structure")
    parser.add_argument("--dry-run", action="store_true", help="Dry run (no actual changes)")
    parser.add_argument("--project-id", type=str, help="Migrate specific project only")
    parser.add_argument("--verify", action="store_true", help="Verify migration only")

    args = parser.parse_args()

    tool = V7MigrationTool(dry_run=args.dry_run)

    if args.verify:
        if args.project_id:
            success = tool.verify_migration(args.project_id)
            sys.exit(0 if success else 1)
        else:
            logger.error("--verify requires --project-id")
            sys.exit(1)
    else:
        project_ids = [args.project_id] if args.project_id else None
        await tool.migrate_all_projects(project_ids)


if __name__ == "__main__":
    asyncio.run(main())
