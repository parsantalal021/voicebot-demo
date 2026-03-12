"""
Database layer using Python's built-in sqlite3.
Single file, WAL mode, persistent across Railway restarts via mounted volume.
"""

import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger("database")

DB_PATH = os.getenv("DB_PATH", "./data/patients.db")


def _ensure_dir():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    """Return a new SQLite connection with row_factory set."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db():
    """Context manager — commits on success, rolls back on error, always closes."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ─── Schema ───────────────────────────────────────────────────────────────────
DDL = """
CREATE TABLE IF NOT EXISTS patients (
    patient_id              TEXT PRIMARY KEY,
    first_name              TEXT NOT NULL CHECK(length(first_name) BETWEEN 1 AND 50),
    last_name               TEXT NOT NULL CHECK(length(last_name) BETWEEN 1 AND 50),
    date_of_birth           TEXT NOT NULL,
    sex                     TEXT NOT NULL CHECK(sex IN ('Male','Female','Other','Decline to Answer')),
    phone_number            TEXT NOT NULL,
    email                   TEXT,
    address_line_1          TEXT NOT NULL,
    address_line_2          TEXT,
    city                    TEXT NOT NULL CHECK(length(city) BETWEEN 1 AND 100),
    state                   TEXT NOT NULL CHECK(length(state) = 2),
    zip_code                TEXT NOT NULL,
    insurance_provider      TEXT,
    insurance_member_id     TEXT,
    preferred_language      TEXT DEFAULT 'English',
    emergency_contact_name  TEXT,
    emergency_contact_phone TEXT,
    call_transcript         TEXT,
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL,
    deleted_at              TEXT
);

CREATE INDEX IF NOT EXISTS idx_patients_last_name
    ON patients(last_name) WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_patients_phone
    ON patients(phone_number) WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_patients_dob
    ON patients(date_of_birth) WHERE deleted_at IS NULL;
"""


def init_db():
    _ensure_dir()
    with get_db() as conn:
        conn.executescript(DDL)
    logger.info(f"Database initialized at {DB_PATH}")


# ─── Seed ─────────────────────────────────────────────────────────────────────
def seed_db():
    import uuid
    from datetime import datetime, timezone

    with get_db() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM patients WHERE deleted_at IS NULL"
        ).fetchone()[0]
        if count > 0:
            logger.info("Seed skipped — records already exist.")
            return

        now = datetime.now(timezone.utc).isoformat()
        seeds = [
            {
                "patient_id": str(uuid.uuid4()),
                "first_name": "Jane",
                "last_name": "Doe",
                "date_of_birth": "1985-06-15",
                "sex": "Female",
                "phone_number": "5551234567",
                "email": "jane.doe@example.com",
                "address_line_1": "123 Maple Street",
                "address_line_2": "Apt 4B",
                "city": "Austin",
                "state": "TX",
                "zip_code": "78701",
                "insurance_provider": "Blue Cross Blue Shield",
                "insurance_member_id": "BCBS-123456",
                "preferred_language": "English",
                "emergency_contact_name": "John Doe",
                "emergency_contact_phone": "5559876543",
                "call_transcript": None,
                "created_at": now,
                "updated_at": now,
                "deleted_at": None,
            },
            {
                "patient_id": str(uuid.uuid4()),
                "first_name": "Carlos",
                "last_name": "Rivera",
                "date_of_birth": "1972-11-30",
                "sex": "Male",
                "phone_number": "5557654321",
                "email": "carlos.rivera@example.com",
                "address_line_1": "456 Oak Avenue",
                "address_line_2": None,
                "city": "Miami",
                "state": "FL",
                "zip_code": "33101",
                "insurance_provider": "Aetna",
                "insurance_member_id": "AET-789012",
                "preferred_language": "Spanish",
                "emergency_contact_name": "Maria Rivera",
                "emergency_contact_phone": "5553216547",
                "call_transcript": None,
                "created_at": now,
                "updated_at": now,
                "deleted_at": None,
            },
        ]
        conn.executemany(
            """INSERT INTO patients VALUES (
                :patient_id, :first_name, :last_name, :date_of_birth, :sex,
                :phone_number, :email, :address_line_1, :address_line_2,
                :city, :state, :zip_code, :insurance_provider,
                :insurance_member_id, :preferred_language,
                :emergency_contact_name, :emergency_contact_phone,
                :call_transcript, :created_at, :updated_at, :deleted_at
            )""",
            seeds,
        )
        logger.info(f"Seeded {len(seeds)} demo patients.")
