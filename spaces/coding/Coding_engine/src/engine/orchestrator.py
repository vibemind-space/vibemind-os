"""
Orchestrator - Main coordination layer for the coding engine.

This module handles:
1. Job lifecycle management
2. Coordinating DAG parsing and task scheduling
3. Monitoring job progress
4. Assembling results
"""
import asyncio
import json
from typing import Optional
from datetime import datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from src.config import get_settings
from src.models.project import Project, ProjectStatus
from src.models.job import Job, JobStatus
from src.models.task import Task, TaskStatus, TaskType
from src.engine.dag_parser import DAGParser, RequirementsData, NodeType
from src.engine.task_scheduler import TaskScheduler, ScheduledTask

logger = structlog.get_logger()


class Orchestrator:
    """
    Main orchestrator for the coding engine.

    Coordinates:
    1. Parsing requirements
    2. Building execution DAG
    3. Scheduling tasks to agents
    4. Tracking progress
    5. Assembling results
    """

    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        self.parser = DAGParser()
        self.scheduler: Optional[TaskScheduler] = None
        self.logger = logger.bind(component="orchestrator")
        self._settings = get_settings()

    async def initialize(self):
        """Initialize orchestrator components."""
        self.scheduler = TaskScheduler(self._settings.redis_url)
        await self.scheduler.connect()

    async def shutdown(self):
        """Shutdown orchestrator components."""
        if self.scheduler:
            await self.scheduler.close()

    async def create_project(
        self,
        name: str,
        description: Optional[str] = None,
        config: Optional[dict] = None,
    ) -> Project:
        """Create a new project."""
        project = Project(
            name=name,
            description=description,
            status=ProjectStatus.CREATED,
            config_json=json.dumps(config) if config else None,
        )

        self.db.add(project)
        await self.db.flush()
        await self.db.refresh(project)

        self.logger.info("project_created", project_id=project.id, name=name)
        return project

    async def submit_job(
        self,
        project_id: int,
        requirements_json: str,
        source_file: Optional[str] = None,
    ) -> Job:
        """
        Submit a new job for processing.

        Args:
            project_id: The project to associate with
            requirements_json: The requirements JSON string
            source_file: Optional source file path

        Returns:
            The created Job
        """
        # Parse requirements
        try:
            data = json.loads(requirements_json)
            req_data = self.parser.parse(data)
        except (json.JSONDecodeError, ValueError) as e:
            self.logger.error("parse_error", error=str(e))
            raise ValueError(f"Failed to parse requirements: {e}")

        # Create job record
        job = Job(
            project_id=project_id,
            status=JobStatus.PARSING,
            requirements_json=requirements_json,
            source_file=source_file,
            total_requirements=len(req_data.requirements),
            dag_nodes=req_data.dag.number_of_nodes() if req_data.dag else 0,
            dag_edges=req_data.dag.number_of_edges() if req_data.dag else 0,
        )

        self.db.add(job)
        await self.db.flush()
        await self.db.refresh(job)

        self.logger.info(
            "job_created",
            job_id=job.id,
            project_id=project_id,
            requirements=job.total_requirements,
        )

        # Create task records in database
        tasks = await self._create_task_records(job, req_data)
        job.total_tasks = len(tasks)

        # Update job status
        job.status = JobStatus.SCHEDULING
        await self.db.flush()

        # Schedule tasks
        if self.scheduler:
            scheduled_tasks = await self.scheduler.schedule_job(
                job.id,
                req_data,
                project_context={"project_id": project_id},
            )

            job.status = JobStatus.RUNNING
            await self.db.flush()

            self.logger.info(
                "job_scheduled",
                job_id=job.id,
                scheduled_tasks=len(scheduled_tasks),
            )

        # Refresh job to get all updated attributes including timestamps
        await self.db.refresh(job)
        return job

    async def _create_task_records(
        self,
        job: Job,
        req_data: RequirementsData,
    ) -> list[Task]:
        """Create task records in the database."""
        tasks = []
        dag = req_data.dag
        req_nodes = {n.id: n for n in req_data.nodes if n.type == NodeType.REQUIREMENT}

        for node_id, node in req_nodes.items():
            # Get dependencies
            predecessors = list(dag.predecessors(node_id)) if dag and node_id in dag else []
            depth = dag.nodes[node_id].get('depth', 0) if dag and node_id in dag else 0

            # Determine task type
            task_type_str = self.parser.get_task_type_for_requirement(node)
            try:
                task_type = TaskType(task_type_str)
            except ValueError:
                task_type = TaskType.GENERAL

            # Generate prompt
            prompt = self._generate_prompt(node)

            task = Task(
                job_id=job.id,
                task_id=node_id,
                requirement_ids=[node_id],
                task_type=task_type,
                title=node.name[:512],  # Truncate to fit
                description=f"Implement requirement: {node.name}",
                prompt=prompt,
                depends_on=predecessors,
                depth_level=depth,
                status=TaskStatus.PENDING,
            )

            self.db.add(task)
            tasks.append(task)

        await self.db.flush()

        self.logger.info(
            "task_records_created",
            job_id=job.id,
            num_tasks=len(tasks),
        )

        return tasks

    def _generate_prompt(self, node) -> str:
        """Generate a prompt for the agent."""
        return f"""# Requirement Implementation

**Requirement ID:** {node.id}
**Title:** {node.name}
**Tag:** {node.tag or 'functional'}

## Task
Implement the following requirement:

{node.name}

## Instructions
1. Analyze the requirement carefully
2. Design an appropriate solution
3. Write clean, well-structured code
4. Include error handling
5. Add comments where necessary

## Output
Provide:
1. The implementation code
2. Any necessary configuration
3. A brief explanation of your approach
"""

    async def get_job_status(self, job_id: int) -> Optional[dict]:
        """Get current job status and progress."""
        # Get job from database
        result = await self.db.execute(
            select(Job).where(Job.id == job_id)
        )
        job = result.scalar_one_or_none()

        if not job:
            return None

        # Get progress from scheduler
        progress = {}
        if self.scheduler:
            progress = await self.scheduler.get_job_progress(job_id)

        return {
            "job_id": job.id,
            "project_id": job.project_id,
            "status": job.status.value,
            "status_message": job.status_message,
            "total_requirements": job.total_requirements,
            "total_tasks": job.total_tasks,
            "tasks_completed": progress.get("completed", job.tasks_completed),
            "tasks_failed": progress.get("failed", job.tasks_failed),
            "tasks_running": progress.get("running", 0),
            "tasks_queued": progress.get("queued", 0),
            "progress_percent": progress.get("progress_percent", job.progress_percent),
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        }

    async def update_task_status(
        self,
        job_id: int,
        task_id: str,
        status: TaskStatus,
        result: Optional[dict] = None,
        error: Optional[str] = None,
    ):
        """Update task status in the database."""
        stmt = (
            update(Task)
            .where(Task.job_id == job_id, Task.task_id == task_id)
            .values(
                status=status,
                status_message=error if error else None,
                agent_response=json.dumps(result) if result else None,
            )
        )
        await self.db.execute(stmt)

        # Update job counters
        if status == TaskStatus.COMPLETED:
            await self.db.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(tasks_completed=Job.tasks_completed + 1)
            )
        elif status == TaskStatus.FAILED:
            await self.db.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(tasks_failed=Job.tasks_failed + 1)
            )

        await self.db.flush()

    async def check_job_completion(self, job_id: int) -> bool:
        """Check if a job is complete and update status."""
        result = await self.db.execute(
            select(Job).where(Job.id == job_id)
        )
        job = result.scalar_one_or_none()

        if not job:
            return False

        total_done = job.tasks_completed + job.tasks_failed

        if total_done >= job.total_tasks:
            # Job is complete
            if job.tasks_failed > 0:
                job.status = JobStatus.FAILED
                job.status_message = f"{job.tasks_failed} tasks failed"
            else:
                job.status = JobStatus.COMPLETED

            await self.db.flush()

            self.logger.info(
                "job_completed",
                job_id=job_id,
                status=job.status.value,
                completed=job.tasks_completed,
                failed=job.tasks_failed,
            )
            return True

        return False

    async def get_job_results(self, job_id: int) -> dict:
        """Get all results for a completed job."""
        # Get tasks with results
        result = await self.db.execute(
            select(Task).where(Task.job_id == job_id)
        )
        tasks = result.scalars().all()

        results = {
            "job_id": job_id,
            "tasks": [],
            "artifacts": [],
        }

        for task in tasks:
            task_result = {
                "task_id": task.task_id,
                "title": task.title,
                "status": task.status.value,
                "task_type": task.task_type.value,
            }

            if task.agent_response:
                try:
                    task_result["response"] = json.loads(task.agent_response)
                except json.JSONDecodeError:
                    task_result["response"] = task.agent_response

            if task.generated_files:
                task_result["files"] = task.generated_files

            results["tasks"].append(task_result)

        return results
