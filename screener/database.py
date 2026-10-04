"""SQLite database storage module for resumes, job descriptions, and match results.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from screener.logger import get_logger

logger = get_logger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "resume_screener.db"


class Database:
    """Manages SQLite storage for the resume screening application."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Establish SQLite connection with foreign keys enabled."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_db(self) -> None:
        """Initialize database schema if tables do not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Job Descriptions Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS job_descriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    raw_text TEXT NOT NULL,
                    min_experience_years REAL DEFAULT 0.0,
                    required_skills TEXT,  -- JSON list
                    preferred_skills TEXT, -- JSON list
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Resumes Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS resumes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    candidate_name TEXT NOT NULL,
                    email TEXT,
                    phone TEXT,
                    raw_text TEXT NOT NULL,
                    experience_years REAL DEFAULT 0.0,
                    skills TEXT,           -- JSON list
                    degrees TEXT,          -- JSON list
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Match Results Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS match_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    jd_id INTEGER,
                    resume_id INTEGER,
                    mode TEXT NOT NULL,    -- 'recruiter' or 'candidate'
                    overall_score REAL NOT NULL,
                    rating_label TEXT NOT NULL,
                    breakdown_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(jd_id) REFERENCES job_descriptions(id) ON DELETE CASCADE,
                    FOREIGN KEY(resume_id) REFERENCES resumes(id) ON DELETE CASCADE
                )
            """)

            conn.commit()
            logger.debug("Database initialized successfully.")

    def save_job_description(
        self,
        title: str,
        raw_text: str,
        min_experience_years: float,
        required_skills: List[str],
        preferred_skills: List[str],
    ) -> int:
        """Insert or return ID for job description."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO job_descriptions (title, raw_text, min_experience_years, required_skills, preferred_skills)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    title,
                    raw_text,
                    min_experience_years,
                    json.dumps(required_skills),
                    json.dumps(preferred_skills),
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def save_resume(
        self,
        filename: str,
        candidate_name: str,
        email: Optional[str],
        phone: Optional[str],
        raw_text: str,
        experience_years: float,
        skills: List[str],
        degrees: List[str],
    ) -> int:
        """Insert candidate resume record."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO resumes (filename, candidate_name, email, phone, raw_text, experience_years, skills, degrees)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    filename,
                    candidate_name,
                    email,
                    phone,
                    raw_text,
                    experience_years,
                    json.dumps(skills),
                    json.dumps(degrees),
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def save_match_result(
        self,
        jd_id: int,
        resume_id: int,
        mode: str,
        overall_score: float,
        rating_label: str,
        breakdown_dict: Dict[str, Any],
    ) -> int:
        """Insert match screening result."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO match_results (jd_id, resume_id, mode, overall_score, rating_label, breakdown_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    jd_id,
                    resume_id,
                    mode,
                    overall_score,
                    rating_label,
                    json.dumps(breakdown_dict),
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve recent match screening history."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            query = """
                SELECT 
                    m.id AS match_id,
                    m.mode,
                    m.overall_score,
                    m.rating_label,
                    m.breakdown_json,
                    m.created_at AS match_date,
                    r.id AS resume_id,
                    r.filename,
                    r.candidate_name,
                    r.email,
                    r.experience_years,
                    j.id AS jd_id,
                    j.title AS job_title
                FROM match_results m
                LEFT JOIN resumes r ON m.resume_id = r.id
                LEFT JOIN job_descriptions j ON m.jd_id = j.id
                ORDER BY m.id DESC
                LIMIT ?
            """
            cursor.execute(query, (limit,))
            rows = cursor.fetchall()
            results = []
            for r in rows:
                item = dict(r)
                if item.get("breakdown_json"):
                    try:
                        item["breakdown"] = json.loads(item["breakdown_json"])
                    except Exception:
                        item["breakdown"] = {}
                results.append(item)
            return results

    def clear_all_history(self) -> None:
        """Clear database records."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM match_results")
            cursor.execute("DELETE FROM resumes")
            cursor.execute("DELETE FROM job_descriptions")
            conn.commit()
            logger.info("Cleared all database history.")
