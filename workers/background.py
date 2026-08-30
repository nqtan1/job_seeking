from __future__ import annotations

import json
import os
import sqlite3
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

from pydantic import BaseModel


class BackgroundJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


def _serialize_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return json.loads(value.model_dump_json())
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _serialize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]
    return value


@dataclass
class BackgroundJobRecord:
    job_id: str
    tenant_id: str
    job_type: str
    status: BackgroundJobStatus = BackgroundJobStatus.QUEUED
    submitted_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Any] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "tenant_id": self.tenant_id,
            "job_type": self.job_type,
            "status": self.status.value,
            "submitted_at": self.submitted_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": _serialize_value(self.result),
            "error": self.error,
        }


class BackgroundJobManager:
    def __init__(self, max_workers: int = 4, db_path: Optional[str] = None):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = Lock()
        self._futures: Dict[str, Future] = {}
        
        # Set default DB path to db/background_jobs.db under the project root
        if db_path is None:
            project_root = Path(__file__).resolve().parent.parent
            self.db_path = str(project_root / "db" / "background_jobs.db")
        else:
            self.db_path = db_path
            
        self._init_db()

    def _init_db(self):
        """Initialize the SQLite database schema."""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS background_jobs (
                    job_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    job_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    submitted_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    result TEXT,
                    error TEXT
                )
            """)
            conn.commit()

    def _row_to_record(self, row: tuple) -> BackgroundJobRecord:
        """Map an SQLite row back to a BackgroundJobRecord dataclass."""
        job_id, tenant_id, job_type, status, submitted_at, started_at, completed_at, result_json, error = row
        
        result = None
        if result_json:
            try:
                result = json.loads(result_json)
            except Exception:
                result = result_json

        return BackgroundJobRecord(
            job_id=job_id,
            tenant_id=tenant_id,
            job_type=job_type,
            status=BackgroundJobStatus(status),
            submitted_at=datetime.fromisoformat(submitted_at),
            started_at=datetime.fromisoformat(started_at) if started_at else None,
            completed_at=datetime.fromisoformat(completed_at) if completed_at else None,
            result=result,
            error=error,
        )

    def submit(
        self,
        tenant_id: str,
        job_type: str,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> str:
        job_id = str(uuid4())
        submitted_at = datetime.now()
        
        # 1. Insert queued record into the database
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO background_jobs (job_id, tenant_id, job_type, status, submitted_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_id, tenant_id, job_type, BackgroundJobStatus.QUEUED.value, submitted_at.isoformat()),
            )
            conn.commit()

        def runner() -> Any:
            started_at = datetime.now()
            
            # 2. Update status to RUNNING
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    UPDATE background_jobs 
                    SET status = ?, started_at = ? 
                    WHERE job_id = ?
                    """,
                    (BackgroundJobStatus.RUNNING.value, started_at.isoformat(), job_id),
                )
                conn.commit()

            try:
                result = func(*args, **kwargs)
                completed_at = datetime.now()
                serialized_result = json.dumps(_serialize_value(result))
                
                # 3. Update status to COMPLETED
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        """
                        UPDATE background_jobs 
                        SET status = ?, completed_at = ?, result = ? 
                        WHERE job_id = ?
                        """,
                        (BackgroundJobStatus.COMPLETED.value, completed_at.isoformat(), serialized_result, job_id),
                    )
                    conn.commit()
                return result
            except Exception as exc:
                completed_at = datetime.now()
                
                # 4. Update status to FAILED
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        """
                        UPDATE background_jobs 
                        SET status = ?, completed_at = ?, error = ? 
                        WHERE job_id = ?
                        """,
                        (BackgroundJobStatus.FAILED.value, completed_at.isoformat(), str(exc), job_id),
                    )
                    conn.commit()
                raise

        future = self._executor.submit(runner)
        with self._lock:
            self._futures[job_id] = future

        return job_id

    def get(self, job_id: str) -> Optional[BackgroundJobRecord]:
        """Fetch a background job record from SQLite."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT job_id, tenant_id, job_type, status, submitted_at, started_at, completed_at, result, error
                FROM background_jobs WHERE job_id = ?
                """,
                (job_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return self._row_to_record(row)

    def wait(self, job_id: str, timeout: Optional[float] = None) -> Any:
        with self._lock:
            future = self._futures.get(job_id)

        if future is None:
            raise KeyError(f"Unknown job id: {job_id}")

        return future.result(timeout=timeout)

    def list_for_tenant(self, tenant_id: str) -> list[BackgroundJobRecord]:
        """Fetch all background job records for a specific tenant from SQLite."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT job_id, tenant_id, job_type, status, submitted_at, started_at, completed_at, result, error
                FROM background_jobs WHERE tenant_id = ?
                ORDER BY submitted_at DESC
                """,
                (tenant_id,),
            )
            rows = cursor.fetchall()
            return [self._row_to_record(row) for row in rows]


_BACKGROUND_JOB_MANAGER: Optional[BackgroundJobManager] = None


def get_background_job_manager() -> BackgroundJobManager:
    global _BACKGROUND_JOB_MANAGER
    if _BACKGROUND_JOB_MANAGER is None:
        _BACKGROUND_JOB_MANAGER = BackgroundJobManager()
    return _BACKGROUND_JOB_MANAGER