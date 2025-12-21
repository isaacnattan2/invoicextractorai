import json
import queue
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class JobStatus(Enum):
    WAITING = "WAITING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


def format_elapsed_time(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}m {secs:02d}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes:02d}m"


def get_model_name_for_provider(provider: str) -> str:
    if provider == "offline":
        from app.services.ollama_client import OllamaClient
        client = OllamaClient()
        return client.model
    elif provider == "online":
        return "gpt-4o-mini"
    return provider


@dataclass
class Job:
    id: str
    filename: str
    provider: str
    model_name: Optional[str] = None
    status: JobStatus = JobStatus.WAITING
    progress: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None
    excel_path: Optional[str] = None
    pdf_content: Optional[bytes] = None
    cancelled: bool = False
    extracted_text: Optional[str] = None
    llm_prompt: Optional[str] = None

    def get_elapsed_seconds(self) -> int:
        if self.finished_at:
            delta = self.finished_at - self.created_at
        else:
            delta = datetime.now() - self.created_at
        return int(delta.total_seconds())

    def to_dict(self) -> dict:
        elapsed_seconds = self.get_elapsed_seconds()
        return {
            "id": self.id,
            "filename": self.filename,
            "provider": self.provider,
            "model_name": self.model_name or self.provider,
            "status": self.status.value,
            "progress": self.progress,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "finished_at": self.finished_at.strftime("%Y-%m-%d %H:%M:%S") if self.finished_at else None,
            "elapsed_time": format_elapsed_time(elapsed_seconds),
            "elapsed_seconds": elapsed_seconds,
            "error_message": self.error_message,
            "has_excel": self.excel_path is not None,
            "extracted_text": self.extracted_text,
            "llm_prompt": self.llm_prompt
        }

    def to_sse_dict(self) -> dict:
        data = self.to_dict()
        if self.excel_path:
            data["download_url"] = f"/jobs/{self.id}/download"
        return data


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
                    cls._instance._subscribers: List[queue.Queue] = []
                    cls._instance._subscribers_lock = threading.Lock()
        return cls._instance

    def subscribe(self) -> queue.Queue:
        q = queue.Queue()
        with self._subscribers_lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue):
        with self._subscribers_lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def _emit_event(self, job: Job):
        event_data = json.dumps(job.to_sse_dict())
        with self._subscribers_lock:
            for q in self._subscribers:
                try:
                    q.put_nowait(event_data)
                except queue.Full:
                    pass

    def create_job(self, filename: str, provider: str, pdf_content: bytes) -> Job:
        job_id = str(uuid.uuid4())[:8]
        model_name = get_model_name_for_provider(provider)
        job = Job(
            id=job_id,
            filename=filename,
            provider=provider,
            model_name=model_name,
            pdf_content=pdf_content
        )
        with self._jobs_lock:
            self._jobs[job_id] = job
        self._emit_event(job)
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
        job = None
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = status
                if progress is not None:
                    job.progress = progress
        if job:
            self._emit_event(job)

    def update_job_progress(self, job_id: str, progress: int):
        job = None
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if job:
                job.progress = progress
        if job:
            self._emit_event(job)

    def set_job_details(self, job_id: str, extracted_text: str, llm_prompt: str):
        job = None
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if job:
                job.extracted_text = extracted_text
                job.llm_prompt = llm_prompt
        if job:
            self._emit_event(job)

    def set_job_error(self, job_id: str, error_message: str):
        job = None
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = JobStatus.ERROR
                job.error_message = error_message
                job.finished_at = datetime.now()
        if job:
            self._emit_event(job)

    def set_job_completed(self, job_id: str, excel_path: str):
        job = None
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = JobStatus.COMPLETED
                job.progress = 100
                job.excel_path = excel_path
                job.pdf_content = None
                job.finished_at = datetime.now()
        if job:
            self._emit_event(job)

    def cancel_job(self, job_id: str) -> bool:
        job = None
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if job and job.status in (JobStatus.WAITING, JobStatus.PROCESSING):
                job.cancelled = True
                job.status = JobStatus.CANCELLED
                job.pdf_content = None
        if job and job.cancelled:
            self._emit_event(job)
            return True
        return False

    def is_job_cancelled(self, job_id: str) -> bool:
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            return job.cancelled if job else False


def get_registry() -> JobRegistry:
    return JobRegistry()
