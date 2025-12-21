import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Optional


class JobStatus(Enum):
    WAITING = "WAITING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


@dataclass
class Job:
    id: str
    filename: str
    provider: str
    status: JobStatus = JobStatus.WAITING
    progress: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    error_message: Optional[str] = None
    excel_path: Optional[str] = None
    pdf_content: Optional[bytes] = None
    cancelled: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "provider": self.provider,
            "status": self.status.value,
            "progress": self.progress,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "error_message": self.error_message,
            "has_excel": self.excel_path is not None
        }


class JobRegistry:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._jobs: Dict[str, Job] = {}
                    cls._instance._jobs_lock = threading.Lock()
        return cls._instance

    def create_job(self, filename: str, provider: str, pdf_content: bytes) -> Job:
        job_id = str(uuid.uuid4())[:8]
        job = Job(
            id=job_id,
            filename=filename,
            provider=provider,
            pdf_content=pdf_content
        )
        with self._jobs_lock:
            self._jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        with self._jobs_lock:
            return self._jobs.get(job_id)

    def get_all_jobs(self) -> list:
        with self._jobs_lock:
            sorted_jobs = sorted(
                self._jobs.values(),
                key=lambda j: j.created_at,
                reverse=True
            )
            return [job.to_dict() for job in sorted_jobs]

    def update_job_status(self, job_id: str, status: JobStatus, progress: int = None):
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = status
                if progress is not None:
                    job.progress = progress

    def update_job_progress(self, job_id: str, progress: int):
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if job:
                job.progress = progress

    def set_job_error(self, job_id: str, error_message: str):
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = JobStatus.ERROR
                job.error_message = error_message

    def set_job_completed(self, job_id: str, excel_path: str):
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = JobStatus.COMPLETED
                job.progress = 100
                job.excel_path = excel_path
                job.pdf_content = None

    def cancel_job(self, job_id: str) -> bool:
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if job and job.status in (JobStatus.WAITING, JobStatus.PROCESSING):
                job.cancelled = True
                job.status = JobStatus.CANCELLED
                job.pdf_content = None
                return True
            return False

    def is_job_cancelled(self, job_id: str) -> bool:
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            return job.cancelled if job else False


def get_registry() -> JobRegistry:
    return JobRegistry()
