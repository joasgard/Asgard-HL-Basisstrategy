"""
Async job manager for setup wizard long-running operations.
"""

import json
import uuid
import asyncio
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, asdict

from src.db.database import Database


class JobStatus(str, Enum):
    """Job status values."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class JobType(str, Enum):
    """Types of setup jobs."""
    CREATE_WALLETS = "create_wallets"
    TEST_EXCHANGE = "test_exchange"
    VERIFY_FUNDING = "verify_funding"


@dataclass
class JobResult:
    """Result of a completed job."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class Job:
    """Setup job."""
    id: str
    job_type: JobType
    status: JobStatus
    progress: int  # 0-100
    params: Dict[str, Any]
    result: Optional[JobResult] = None
    error: Optional[str] = None
    created_at: datetime = None
    updated_at: datetime = None
    completed_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.updated_at is None:
            self.updated_at = datetime.utcnow()


class SetupJobManager:
    """Manages async setup operations with progress tracking."""
    
    def __init__(self, db: Database):
        self.db = db
        self._jobs: Dict[str, Job] = {}
        self._handlers: Dict[JobType, Callable] = {}
    
    def register_handler(self, job_type: JobType, handler: Callable) -> None:
        """Register a handler for a job type."""
        self._handlers[job_type] = handler
    
    async def create_job(self, job_type: JobType, params: Dict[str, Any]) -> str:
        """
        Create a new job and start it in the background.
        
        Args:
            job_type: Type of job
            params: Job parameters
            
        Returns:
            Job ID for polling
        """
        job_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        job = Job(
            id=job_id,
            job_type=job_type,
            status=JobStatus.PENDING,
            progress=0,
            params=params,
            created_at=now,
            updated_at=now
        )
        
        self._jobs[job_id] = job
        
        # Store in database
        await self.db.execute(
            """INSERT INTO setup_jobs 
               (id, job_type, status, progress, params, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (job_id, job_type.value, job.status.value, job.progress,
             json.dumps(params), now.isoformat(), now.isoformat())
        )
        await self.db._connection.commit()
        
        # Start background task
        asyncio.create_task(self._run_job(job))
        
        return job_id
    
    async def get_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get current job status for polling.
        
        Returns:
            Job status dict or None if not found
        """
        # Check in-memory first
        job = self._jobs.get(job_id)
        
        if job:
            return {
                "id": job.id,
                "type": job.job_type.value,
                "status": job.status.value,
                "progress": job.progress,
                "result": job.result.data if job.result else None,
                "error": job.error,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None
            }
        
        # Fall back to database
        row = await self.db.fetchone(
            """SELECT id, job_type, status, progress, result, error,
                      created_at, completed_at
               FROM setup_jobs WHERE id = ?""",
            (job_id,)
        )
        
        if not row:
            return None
        
        return {
            "id": row["id"],
            "type": row["job_type"],
            "status": row["status"],
            "progress": row["progress"],
            "result": json.loads(row["result"]) if row["result"] else None,
            "error": row["error"],
            "created_at": row["created_at"],
            "completed_at": row["completed_at"]
        }
    
    async def _run_job(self, job: Job) -> None:
        """Execute job and update status."""
        handler = self._handlers.get(job.job_type)
        
        if not handler:
            await self._update_status(
                job.id, 
                JobStatus.FAILED, 
                error=f"No handler for job type: {job.job_type}"
            )
            return
        
        try:
            await self._update_status(job.id, JobStatus.RUNNING, progress=0)
            
            # Execute handler with progress callback
            result = await handler(job.params, lambda p: self._update_progress(job.id, p))
            
            await self._update_status(
                job.id,
                JobStatus.COMPLETED,
                progress=100,
                result=result
            )
            
        except Exception as e:
            await self._update_status(
                job.id,
                JobStatus.FAILED,
                error=str(e)
            )
    
    async def _update_status(
        self,
        job_id: str,
        status: JobStatus,
        progress: Optional[int] = None,
        result: Optional[JobResult] = None,
        error: Optional[str] = None
    ) -> None:
        """Update job status in memory and database."""
        job = self._jobs.get(job_id)
        if job:
            job.status = status
            job.updated_at = datetime.utcnow()
            
            if progress is not None:
                job.progress = progress
            if result is not None:
                job.result = result
            if error is not None:
                job.error = error
            
            if status in (JobStatus.COMPLETED, JobStatus.FAILED):
                job.completed_at = datetime.utcnow()
        
        # Update database
        now = datetime.utcnow()
        completed_at = now if status in (JobStatus.COMPLETED, JobStatus.FAILED) else None
        
        await self.db.execute(
            """UPDATE setup_jobs 
               SET status = ?, progress = ?, result = ?, error = ?,
                   updated_at = ?, completed_at = ?
               WHERE id = ?""",
            (status.value, progress,
             json.dumps(result.data) if result else None,
             error, now.isoformat(),
             completed_at.isoformat() if completed_at else None,
             job_id)
        )
        await self.db._connection.commit()
    
    async def _update_progress(self, job_id: str, progress: int) -> None:
        """Update job progress."""
        await self._update_status(job_id, JobStatus.RUNNING, progress=progress)
