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
from typing import Any, Callable, Dict, Optional, List
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
        """Initialize the SQLite database schema with background jobs and recruitment tracking tables."""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            # 1. Background Jobs Table
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
            
            # 2. Candidates Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS candidates (
                    candidate_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    email TEXT,
                    phone TEXT,
                    extracted_data TEXT NOT NULL,  -- JSON string of CVInformation
                    created_at TEXT NOT NULL
                )
            """)
            try:
                conn.execute("ALTER TABLE candidates ADD COLUMN file_path TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                pass  # column already exists
            
            # 3. Jobs Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    job_title TEXT NOT NULL,
                    company TEXT NOT NULL,
                    extracted_data TEXT NOT NULL,  -- JSON string of JobPosition
                    created_at TEXT NOT NULL
                )
            """)
            
            # 4. Fit Analyses Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS fit_analyses (
                    analysis_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    fit_score INTEGER NOT NULL,
                    fit_data TEXT NOT NULL,        -- JSON string of FitCheck or analysis response
                    created_at TEXT NOT NULL
                )
            """)

            # 5. Applications Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS applications (
                    application_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    company_name TEXT NOT NULL,
                    source TEXT NOT NULL,
                    applied_date TEXT NOT NULL,
                    jd_summary TEXT,
                    status TEXT NOT NULL,
                    recruiter_response TEXT,
                    cv_file TEXT,
                    cover_letter_file TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            try:
                conn.execute("ALTER TABLE applications ADD COLUMN special_documents TEXT")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE applications ADD COLUMN document_prep_completed_at TEXT")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE applications ADD COLUMN applied_confirmed_at TEXT")
            except sqlite3.OperationalError:
                pass
            
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

    # ==========================================
    # Candidates DAL Methods
    # ==========================================
    def save_candidate(
        self,
        tenant_id: str,
        name: str,
        email: Optional[str],
        phone: Optional[str],
        extracted_data_json: str,
        file_path: Optional[str] = None,
    ) -> str:
        """Persist structured candidate profile in SQLite database, upserting if email or name matches to prevent duplicates."""
        created_at = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Check if candidate with same email already exists for this tenant
            if email:
                cursor.execute(
                    "SELECT candidate_id FROM candidates WHERE tenant_id = ? AND email = ?",
                    (tenant_id, email),
                )
                row = cursor.fetchone()
                if row:
                    candidate_id = row[0]
                    # Update existing record and preserve original created_at
                    cursor.execute(
                        """
                        UPDATE candidates
                        SET name = ?, phone = ?, extracted_data = ?, file_path = COALESCE(?, file_path)
                        WHERE candidate_id = ?
                        """,
                        (name, phone, extracted_data_json, file_path, candidate_id),
                    )
                    conn.commit()
                    return candidate_id
            
            # Fallback to name if no email is provided
            cursor.execute(
                "SELECT candidate_id FROM candidates WHERE tenant_id = ? AND name = ? AND email IS NULL",
                (tenant_id, name),
            )
            row = cursor.fetchone()
            if row:
                candidate_id = row[0]
                cursor.execute(
                    """
                    UPDATE candidates
                    SET phone = ?, extracted_data = ?, file_path = COALESCE(?, file_path)
                    WHERE candidate_id = ?
                    """,
                    (phone, extracted_data_json, file_path, candidate_id),
                )
                conn.commit()
                return candidate_id

            # If brand new, insert
            candidate_id = str(uuid4())
            cursor.execute(
                """
                INSERT INTO candidates (candidate_id, tenant_id, name, email, phone, extracted_data, file_path, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (candidate_id, tenant_id, name, email, phone, extracted_data_json, file_path, created_at),
            )
            conn.commit()
        return candidate_id

    def get_candidate(self, candidate_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve candidate profile by ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT candidate_id, tenant_id, name, email, phone, extracted_data, file_path, created_at FROM candidates WHERE candidate_id = ?",
                (candidate_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return {
                "candidate_id": row[0],
                "tenant_id": row[1],
                "name": row[2],
                "email": row[3],
                "phone": row[4],
                "extracted_data": json.loads(row[5]),
                "file_path": row[6],
                "created_at": row[7],
            }

    def list_candidates_for_tenant(self, tenant_id: str) -> List[Dict[str, Any]]:
        """List all candidates registered under a specific tenant."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT candidate_id, tenant_id, name, email, phone, extracted_data, file_path, created_at FROM candidates WHERE tenant_id = ? ORDER BY created_at DESC",
                (tenant_id,),
            )
            rows = cursor.fetchall()
            return [
                {
                    "candidate_id": row[0],
                    "tenant_id": row[1],
                    "name": row[2],
                    "email": row[3],
                    "phone": row[4],
                    "extracted_data": json.loads(row[5]),
                    "file_path": row[6],
                    "created_at": row[7],
                }
                for row in rows
            ]

    # ==========================================
    # Jobs DAL Methods
    # ==========================================
    def save_job(
        self,
        tenant_id: str,
        job_title: str,
        company: str,
        extracted_data_json: str,
    ) -> str:
        """Persist structured job description in SQLite database."""
        job_id = str(uuid4())
        created_at = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO jobs (job_id, tenant_id, job_title, company, extracted_data, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (job_id, tenant_id, job_title, company, extracted_data_json, created_at),
            )
            conn.commit()
        return job_id

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve job description by ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT job_id, tenant_id, job_title, company, extracted_data, created_at FROM jobs WHERE job_id = ?",
                (job_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return {
                "job_id": row[0],
                "tenant_id": row[1],
                "job_title": row[2],
                "company": row[3],
                "extracted_data": json.loads(row[4]),
                "created_at": row[5],
            }

    def list_jobs_for_tenant(self, tenant_id: str) -> List[Dict[str, Any]]:
        """List all jobs parsed under a specific tenant."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT job_id, tenant_id, job_title, company, extracted_data, created_at FROM jobs WHERE tenant_id = ? ORDER BY created_at DESC",
                (tenant_id,),
            )
            rows = cursor.fetchall()
            return [
                {
                    "job_id": row[0],
                    "tenant_id": row[1],
                    "job_title": row[2],
                    "company": row[3],
                    "extracted_data": json.loads(row[4]),
                    "created_at": row[5],
                }
                for row in rows
            ]

    # ==========================================
    # Fit Analyses DAL Methods
    # ==========================================
    def save_fit_analysis(
        self,
        tenant_id: str,
        candidate_id: str,
        job_id: str,
        fit_score: int,
        fit_data_json: str,
    ) -> str:
        """Persist structured candidate-to-job matching analysis in SQLite database."""
        analysis_id = str(uuid4())
        created_at = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO fit_analyses (analysis_id, tenant_id, candidate_id, job_id, fit_score, fit_data, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (analysis_id, tenant_id, candidate_id, job_id, fit_score, fit_data_json, created_at),
            )
            conn.commit()
        return analysis_id

    def get_fit_analysis(self, analysis_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve fit analysis by ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT analysis_id, tenant_id, candidate_id, job_id, fit_score, fit_data, created_at FROM fit_analyses WHERE analysis_id = ?",
                (analysis_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return {
                "analysis_id": row[0],
                "tenant_id": row[1],
                "candidate_id": row[2],
                "job_id": row[3],
                "fit_score": row[4],
                "fit_data": json.loads(row[5]),
                "created_at": row[6],
            }

    # ==========================================
    # Background Jobs Methods
    # ==========================================
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

    # ==========================================
    # ==========================================
    # Applications DAL Methods
    # ==========================================
    def save_application(
        self,
        tenant_id: str,
        company_name: str,
        source: str,
        applied_date: str,
        status: str,
        jd_summary: Optional[str] = None,
        recruiter_response: Optional[str] = None,
        cv_file: Optional[str] = None,
        cover_letter_file: Optional[str] = None,
        special_documents: Optional[str] = None,
        document_prep_completed_at: Optional[str] = None,
        applied_confirmed_at: Optional[str] = None,
    ) -> str:
        """Persist structured application details in SQLite database."""
        application_id = str(uuid4())
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO applications (
                    application_id, tenant_id, company_name, source, applied_date,
                    jd_summary, status, recruiter_response, cv_file, cover_letter_file,
                    special_documents, document_prep_completed_at, applied_confirmed_at,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    application_id, tenant_id, company_name, source, applied_date,
                    jd_summary, status, recruiter_response, cv_file, cover_letter_file,
                    special_documents, document_prep_completed_at, applied_confirmed_at,
                    now, now
                ),
            )
            conn.commit()
        return application_id

    def get_application(self, application_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve application by ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT application_id, tenant_id, company_name, source, applied_date,
                       jd_summary, status, recruiter_response, cv_file, cover_letter_file,
                       special_documents, document_prep_completed_at, applied_confirmed_at,
                       created_at, updated_at
                FROM applications WHERE application_id = ?
                """,
                (application_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return {
                "application_id": row[0],
                "tenant_id": row[1],
                "company_name": row[2],
                "source": row[3],
                "applied_date": row[4],
                "jd_summary": row[5],
                "status": row[6],
                "recruiter_response": row[7],
                "cv_file": row[8],
                "cover_letter_file": row[9],
                "special_documents": row[10],
                "document_prep_completed_at": row[11],
                "applied_confirmed_at": row[12],
                "created_at": row[13],
                "updated_at": row[14],
            }

    def update_application(
        self,
        application_id: str,
        company_name: str,
        source: str,
        applied_date: str,
        status: str,
        jd_summary: Optional[str] = None,
        recruiter_response: Optional[str] = None,
        cv_file: Optional[str] = None,
        cover_letter_file: Optional[str] = None,
        special_documents: Optional[str] = None,
        document_prep_completed_at: Optional[str] = None,
        applied_confirmed_at: Optional[str] = None,
    ) -> bool:
        """Update application details by ID."""
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE applications
                SET company_name = ?, source = ?, applied_date = ?, status = ?,
                    jd_summary = ?, recruiter_response = ?, cv_file = ?, cover_letter_file = ?,
                    special_documents = ?, document_prep_completed_at = ?, applied_confirmed_at = ?,
                    updated_at = ?
                WHERE application_id = ?
                """,
                (
                    company_name, source, applied_date, status,
                    jd_summary, recruiter_response, cv_file, cover_letter_file,
                    special_documents, document_prep_completed_at, applied_confirmed_at,
                    now, application_id
                ),
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_application(self, application_id: str) -> bool:
        """Delete application by ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM applications WHERE application_id = ?", (application_id,))
            conn.commit()
            return cursor.rowcount > 0

    def list_applications_for_tenant(
        self,
        tenant_id: str,
        status: Optional[str] = None,
        source: Optional[str] = None,
        sort_by_date: str = "desc"
    ) -> List[Dict[str, Any]]:
        """List all applications for a specific tenant with filtering and sorting."""
        query = """
            SELECT application_id, tenant_id, company_name, source, applied_date,
                   jd_summary, status, recruiter_response, cv_file, cover_letter_file,
                   special_documents, document_prep_completed_at, applied_confirmed_at,
                   created_at, updated_at
            FROM applications WHERE tenant_id = ?
        """
        params = [tenant_id]

        if status:
            query += " AND status = ?"
            params.append(status)
        if source:
            query += " AND source = ?"
            params.append(source)

        order = "DESC" if sort_by_date.lower() == "desc" else "ASC"
        query += f" ORDER BY applied_date {order}"

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            return [
                {
                    "application_id": row[0],
                    "tenant_id": row[1],
                    "company_name": row[2],
                    "source": row[3],
                    "applied_date": row[4],
                    "jd_summary": row[5],
                    "status": row[6],
                    "recruiter_response": row[7],
                    "cv_file": row[8],
                    "cover_letter_file": row[9],
                    "special_documents": row[10],
                    "document_prep_completed_at": row[11],
                    "applied_confirmed_at": row[12],
                    "created_at": row[13],
                    "updated_at": row[14],
                }
                for row in rows
            ]


_BACKGROUND_JOB_MANAGER: Optional[BackgroundJobManager] = None


def get_background_job_manager() -> BackgroundJobManager:
    global _BACKGROUND_JOB_MANAGER
    if _BACKGROUND_JOB_MANAGER is None:
        _BACKGROUND_JOB_MANAGER = BackgroundJobManager()
    return _BACKGROUND_JOB_MANAGER