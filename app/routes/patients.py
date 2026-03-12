import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.models.patient import (
    create_patient,
    delete_patient,
    get_patient,
    list_patients,
    update_patient,
)
from app.schemas import PatientCreate, PatientUpdate

router = APIRouter()
logger = logging.getLogger("routes.patients")


def ok(data: dict, status: int = 200):
    return JSONResponse(status_code=status, content={"data": data, "error": None})


def fail(message: str, status: int = 400):
    return JSONResponse(status_code=status, content={"data": None, "error": {"message": message}})


# ─── GET /patients ────────────────────────────────────────────────────────────
@router.get("/")
def route_list_patients(
    last_name:     Optional[str] = Query(None),
    date_of_birth: Optional[str] = Query(None),
    phone_number:  Optional[str] = Query(None),
):
    patients = list_patients(last_name=last_name, date_of_birth=date_of_birth, phone_number=phone_number)
    return ok({"patients": patients, "total": len(patients)})


# ─── GET /patients/{id} ───────────────────────────────────────────────────────
@router.get("/{patient_id}")
def route_get_patient(patient_id: str):
    patient = get_patient(patient_id)
    if not patient:
        return fail("Patient not found", 404)
    return ok({"patient": patient})


# ─── POST /patients ───────────────────────────────────────────────────────────
@router.post("/")
def route_create_patient(body: PatientCreate):
    try:
        patient = create_patient(body)
        return ok({"patient": patient}, 201)
    except Exception as e:
        logger.error(f"Create patient error: {e}", exc_info=True)
        return fail("Failed to create patient record", 500)


# ─── PUT /patients/{id} ───────────────────────────────────────────────────────
@router.put("/{patient_id}")
def route_update_patient(patient_id: str, body: PatientUpdate):
    patient = update_patient(patient_id, body)
    if patient is None:
        return fail("Patient not found", 404)
    return ok({"patient": patient})


# ─── DELETE /patients/{id} ────────────────────────────────────────────────────
@router.delete("/{patient_id}")
def route_delete_patient(patient_id: str):
    success = delete_patient(patient_id)
    if not success:
        return fail("Patient not found", 404)
    return ok({"message": "Patient record deactivated"})
