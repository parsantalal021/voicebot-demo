"""
Patient data access layer.
All DB operations go through here — routes stay thin.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.database import get_db
from app.schemas import PatientCreate, PatientUpdate

logger = logging.getLogger("models.patient")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row) -> Optional[dict]:
    if row is None:
        return None
    d = dict(row)
    d.pop("deleted_at", None)
    return d


# ─── Queries ──────────────────────────────────────────────────────────────────

def list_patients(
    last_name: Optional[str] = None,
    date_of_birth: Optional[str] = None,
    phone_number: Optional[str] = None,
) -> list[dict]:
    query = "SELECT * FROM patients WHERE deleted_at IS NULL"
    params: list = []

    if last_name:
        query += " AND last_name LIKE ?"
        params.append(f"%{last_name}%")
    if date_of_birth:
        query += " AND date_of_birth = ?"
        params.append(date_of_birth)
    if phone_number:
        # Strip non-digits for comparison
        import re
        digits = re.sub(r"\D", "", phone_number)
        query += " AND phone_number = ?"
        params.append(digits)

    query += " ORDER BY created_at DESC"

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_patient(patient_id: str) -> Optional[dict]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM patients WHERE patient_id = ? AND deleted_at IS NULL",
            (patient_id,),
        ).fetchone()
    return _row_to_dict(row)


def find_by_phone(phone_number: str) -> Optional[dict]:
    """
    Find patient by phone number.
    Matches on last 10 digits — handles country code mismatches
    (e.g. Vapi sends +923001234567, DB has 3001234567).
    """
    import re
    if not phone_number:
        return None

    digits = re.sub(r"\D", "", phone_number)
    # Always compare last 10 digits to handle any country code prefix
    last10 = digits[-10:] if len(digits) >= 10 else digits

    logger.info(f"[DB] find_by_phone: raw={phone_number!r} digits={digits!r} last10={last10!r}")

    with get_db() as conn:
        # Try exact match on stored 10 digits
        row = conn.execute(
            "SELECT * FROM patients WHERE phone_number = ? AND deleted_at IS NULL",
            (last10,),
        ).fetchone()

        if not row:
            # Try LIKE match on last 10 digits in case stored with different format
            row = conn.execute(
                "SELECT * FROM patients WHERE phone_number LIKE ? AND deleted_at IS NULL",
                (f"%{last10}",),
            ).fetchone()

    if row:
        logger.info(f"[DB] find_by_phone: FOUND {dict(row).get('patient_id')}")
    else:
        logger.info(f"[DB] find_by_phone: NOT FOUND for last10={last10!r}")

    return _row_to_dict(row)


def create_patient(data: PatientCreate) -> dict:
    patient_id = str(uuid.uuid4())
    now = _now()
    row = {
        "patient_id":              patient_id,
        "first_name":              data.first_name,
        "last_name":               data.last_name,
        "date_of_birth":           data.date_of_birth,
        "sex":                     data.sex.value,
        "phone_number":            data.phone_number,
        "email":                   data.email,
        "address_line_1":          data.address_line_1,
        "address_line_2":          data.address_line_2,
        "city":                    data.city,
        "state":                   data.state,
        "zip_code":                data.zip_code,
        "insurance_provider":      data.insurance_provider,
        "insurance_member_id":     data.insurance_member_id,
        "preferred_language":      data.preferred_language or "English",
        "emergency_contact_name":  data.emergency_contact_name,
        "emergency_contact_phone": data.emergency_contact_phone,
        "call_transcript":         data.call_transcript,
        "created_at":              now,
        "updated_at":              now,
        "deleted_at":              None,
    }

    with get_db() as conn:
        conn.execute(
            """INSERT INTO patients VALUES (
                :patient_id, :first_name, :last_name, :date_of_birth, :sex,
                :phone_number, :email, :address_line_1, :address_line_2,
                :city, :state, :zip_code, :insurance_provider,
                :insurance_member_id, :preferred_language,
                :emergency_contact_name, :emergency_contact_phone,
                :call_transcript, :created_at, :updated_at, :deleted_at
            )""",
            row,
        )

    logger.info(f"Created patient {patient_id} — {data.first_name} {data.last_name}")
    return get_patient(patient_id)


def update_patient(patient_id: str, data: PatientUpdate) -> Optional[dict]:
    existing = get_patient(patient_id)
    if not existing:
        return None

    updates = data.model_dump(exclude_unset=True)
    if not updates:
        return existing  # nothing to change

    # Serialize enum if present
    if "sex" in updates and updates["sex"] is not None:
        updates["sex"] = updates["sex"].value

    updates["updated_at"] = _now()

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["patient_id"] = patient_id

    with get_db() as conn:
        conn.execute(
            f"UPDATE patients SET {set_clause} WHERE patient_id = :patient_id AND deleted_at IS NULL",
            updates,
        )

    logger.info(f"Updated patient {patient_id}")
    return get_patient(patient_id)


def delete_patient(patient_id: str) -> bool:
    existing = get_patient(patient_id)
    if not existing:
        return False

    now = _now()
    with get_db() as conn:
        conn.execute(
            "UPDATE patients SET deleted_at = ?, updated_at = ? WHERE patient_id = ?",
            (now, now, patient_id),
        )

    logger.info(f"Soft-deleted patient {patient_id}")
    return True