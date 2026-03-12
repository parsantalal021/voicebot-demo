"""
Pydantic v2 schemas for request/response validation.
All normalization (phone digits, date format, state uppercase) happens here.
"""

import re
from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

# ─── Constants ────────────────────────────────────────────────────────────────

US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
    "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
    "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
    "VA","WA","WV","WI","WY","DC",
}

PHONE_RE  = re.compile(r"^\d{10}$")
ZIP_RE    = re.compile(r"^\d{5}(-\d{4})?$")
NAME_RE   = re.compile(r"^[a-zA-Z\-']{1,50}$")


class SexEnum(str, Enum):
    male     = "Male"
    female   = "Female"
    other    = "Other"
    decline  = "Decline to Answer"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def normalize_phone(value: Optional[str]) -> Optional[str]:
    """Strip non-digits, remove leading country code 1 if present, validate 10 digits."""
    if value is None:
        return None
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    if len(digits) != 10:
        raise ValueError("must be a valid 10-digit U.S. phone number")
    return digits


def normalize_date(value) -> str:
    """Accept YYYY-MM-DD, MM/DD/YYYY, or date objects. Returns YYYY-MM-DD string."""
    if isinstance(value, date):
        d = value
    elif isinstance(value, str):
        value = value.strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
            d = date.fromisoformat(value)
        elif re.match(r"^\d{1,2}/\d{1,2}/\d{4}$", value):
            m, day, y = value.split("/")
            d = date(int(y), int(m), int(day))
        else:
            # Try natural language parsing via datetime
            from datetime import datetime as dt
            d = dt.strptime(value, "%B %d %Y").date() if re.match(r"[A-Za-z]", value) else None
            if d is None:
                raise ValueError("unrecognized date format — use YYYY-MM-DD or MM/DD/YYYY")
    else:
        raise ValueError("invalid date")

    if d > date.today():
        raise ValueError("date of birth cannot be in the future")
    if d.year < 1900:
        raise ValueError("date of birth must be after 1900")
    return d.isoformat()


# ─── Schemas ──────────────────────────────────────────────────────────────────

class PatientCreate(BaseModel):
    # Required
    first_name:     str = Field(..., min_length=1, max_length=50)
    last_name:      str = Field(..., min_length=1, max_length=50)
    date_of_birth:  str
    sex:            SexEnum
    phone_number:   str
    address_line_1: str = Field(..., min_length=1)
    city:           str = Field(..., min_length=1, max_length=100)
    state:          str = Field(..., min_length=2, max_length=2)
    zip_code:       str

    # Optional
    email:                   Optional[EmailStr] = None
    address_line_2:          Optional[str] = None
    insurance_provider:      Optional[str] = None
    insurance_member_id:     Optional[str] = None
    preferred_language:      Optional[str] = "English"
    emergency_contact_name:  Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    call_transcript:         Optional[str] = None

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not NAME_RE.match(v):
            raise ValueError("only letters, hyphens, and apostrophes allowed")
        return v

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def validate_dob(cls, v) -> str:
        return normalize_date(v)

    @field_validator("phone_number", mode="before")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return normalize_phone(v)

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: str) -> str:
        upper = v.upper()
        if upper not in US_STATES:
            raise ValueError(f"'{v}' is not a valid U.S. state abbreviation")
        return upper

    @field_validator("zip_code")
    @classmethod
    def validate_zip(cls, v: str) -> str:
        if not ZIP_RE.match(v):
            raise ValueError("must be a 5-digit or ZIP+4 U.S. zip code")
        return v

    @field_validator("emergency_contact_phone", mode="before")
    @classmethod
    def validate_ec_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        return normalize_phone(v)


class PatientUpdate(BaseModel):
    """All fields optional for partial updates."""
    first_name:              Optional[str] = None
    last_name:               Optional[str] = None
    date_of_birth:           Optional[str] = None
    sex:                     Optional[SexEnum] = None
    phone_number:            Optional[str] = None
    email:                   Optional[EmailStr] = None
    address_line_1:          Optional[str] = None
    address_line_2:          Optional[str] = None
    city:                    Optional[str] = None
    state:                   Optional[str] = None
    zip_code:                Optional[str] = None
    insurance_provider:      Optional[str] = None
    insurance_member_id:     Optional[str] = None
    preferred_language:      Optional[str] = None
    emergency_contact_name:  Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    call_transcript:         Optional[str] = None

    @field_validator("first_name", "last_name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v and not NAME_RE.match(v):
            raise ValueError("only letters, hyphens, and apostrophes allowed")
        return v

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def validate_dob(cls, v) -> Optional[str]:
        if v is None:
            return None
        return normalize_date(v)

    @field_validator("phone_number", mode="before")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return normalize_phone(v)

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        upper = v.upper()
        if upper not in US_STATES:
            raise ValueError(f"'{v}' is not a valid U.S. state abbreviation")
        return upper

    @field_validator("zip_code")
    @classmethod
    def validate_zip(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not ZIP_RE.match(v):
            raise ValueError("must be a 5-digit or ZIP+4 U.S. zip code")
        return v

    @field_validator("emergency_contact_phone", mode="before")
    @classmethod
    def validate_ec_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        return normalize_phone(v)


class PatientResponse(BaseModel):
    patient_id:              str
    first_name:              str
    last_name:               str
    date_of_birth:           str
    sex:                     str
    phone_number:            str
    email:                   Optional[str]
    address_line_1:          str
    address_line_2:          Optional[str]
    city:                    str
    state:                   str
    zip_code:                str
    insurance_provider:      Optional[str]
    insurance_member_id:     Optional[str]
    preferred_language:      Optional[str]
    emergency_contact_name:  Optional[str]
    emergency_contact_phone: Optional[str]
    created_at:              str
    updated_at:              str
