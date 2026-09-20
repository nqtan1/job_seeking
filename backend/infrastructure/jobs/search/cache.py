import hashlib
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from domain.jobs.search.schema import UnifiedJobSearchResponse
from utils.logger import get_logger


def _generate_search_key(
    provider: str,
    query: Optional[str],
    dept: Optional[str],
    contract: Optional[str],
    page: int,
    limit: int,
) -> str:
    q = query or ""
    d = dept or ""
    c = contract or ""
    raw_key = f"{provider}:{q}:{d}:{c}:{page}:{limit}"
    return hashlib.md5(raw_key.encode("utf-8")).hexdigest()


class JobCacheManager:
    """
    Manages persistent SQLite-backed caching for search requests and detailed job postings.
    Stores caches in db/job_cache.db to avoid write locks on the main transactions database.
    """

    def __init__(self, db_path: Optional[str] = None, logger_name: str = "jobs.search.cache") -> None:
        self.logger = get_logger(name=logger_name, log_file="jobs_api.log", level="INFO")

        if db_path is None:
            project_root = Path(__file__).resolve().parent.parent.parent.parent
            self.db_path = str(project_root / "db" / "job_cache.db")
        else:
            self.db_path = db_path

        self._init_db()

    def _init_db(self) -> None:
        """Initializes the SQLite cache database schema."""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS search_cache (
                    cache_key TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    query_params TEXT NOT NULL,
                    response_data TEXT NOT NULL,
                    cached_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS detail_cache (
                    job_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    detail_data TEXT NOT NULL,
                    cached_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    PRIMARY KEY (job_id, provider)
                )
            """)
            conn.commit()

    def get_cached_search(
        self,
        provider: str,
        query: Optional[str],
        dept: Optional[str],
        contract: Optional[str],
        page: int,
        limit: int,
    ) -> Optional[UnifiedJobSearchResponse]:
        """
        Retrieves a cached search response if it exists and has not expired.
        """
        cache_key = _generate_search_key(provider, query, dept, contract, page, limit)
        now_str = datetime.now().isoformat()

        try:
            with sqlite3.connect(self.db_path) as conn:
                # Delete expired entries to keep database lean
                conn.execute("DELETE FROM search_cache WHERE expires_at <= ?", (now_str,))
                conn.commit()

                cursor = conn.cursor()
                cursor.execute(
                    "SELECT response_data FROM search_cache WHERE cache_key = ? AND expires_at > ?",
                    (cache_key, now_str),
                )
                row = cursor.fetchone()
                if row:
                    self.logger.debug(f"Search cache hit for provider {provider} with key {cache_key}")
                    data = json.loads(row[0])
                    return UnifiedJobSearchResponse.model_validate(data)
        except Exception as e:
            self.logger.error(f"Error reading search cache: {e}")

        return None

    def save_cached_search(
        self,
        provider: str,
        query: Optional[str],
        dept: Optional[str],
        contract: Optional[str],
        page: int,
        limit: int,
        response: UnifiedJobSearchResponse,
        ttl_seconds: int = 43200,
    ) -> None:
        """
        Saves a search response into the cache with a defined Time To Live.
        """
        cache_key = _generate_search_key(provider, query, dept, contract, page, limit)
        now = datetime.now()
        cached_at = now.isoformat()
        expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()

        query_params_dict = {
            "provider": provider,
            "query": query,
            "dept": dept,
            "contract": contract,
            "page": page,
            "limit": limit,
        }

        try:
            response_json = response.model_dump_json()
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO search_cache (cache_key, provider, query_params, response_data, cached_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (cache_key, provider, json.dumps(query_params_dict), response_json, cached_at, expires_at),
                )
                conn.commit()
                self.logger.debug(f"Saved search cache for provider {provider} with key {cache_key}")
        except Exception as e:
            self.logger.error(f"Error saving search cache: {e}")

    def get_cached_detail(self, provider: str, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves a cached job detail dict if it exists and has not expired.
        """
        now_str = datetime.now().isoformat()

        try:
            with sqlite3.connect(self.db_path) as conn:
                # Delete expired entries to keep database lean
                conn.execute("DELETE FROM detail_cache WHERE expires_at <= ?", (now_str,))
                conn.commit()

                cursor = conn.cursor()
                cursor.execute(
                    "SELECT detail_data FROM detail_cache WHERE job_id = ? AND provider = ? AND expires_at > ?",
                    (job_id, provider, now_str),
                )
                row = cursor.fetchone()
                if row:
                    self.logger.debug(f"Detail cache hit for job_id {job_id} and provider {provider}")
                    data: Dict[str, Any] = json.loads(row[0])
                    return data
        except Exception as e:
            self.logger.error(f"Error reading detail cache: {e}")

        return None

    def save_cached_detail(
        self,
        provider: str,
        job_id: str,
        detail_data: Dict[str, Any],
        ttl_seconds: int = 604800,
    ) -> None:
        """
        Saves job detail data into the cache with a defined Time To Live.
        """
        now = datetime.now()
        cached_at = now.isoformat()
        expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()

        try:
            detail_json = json.dumps(detail_data)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO detail_cache (job_id, provider, detail_data, cached_at, expires_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (job_id, provider, detail_json, cached_at, expires_at),
                )
                conn.commit()
                self.logger.debug(f"Saved detail cache for job_id {job_id} and provider {provider}")
        except Exception as e:
            self.logger.error(f"Error saving detail cache: {e}")
