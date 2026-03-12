"""
Vapi webhook handler.

Vapi POSTs to this endpoint for:
  - type: "tool-calls"       → agent needs to call a function
  - type: "end-of-call-report" → call summary/transcript

Tool call flow:
  1. Vapi sends { message: { type: "tool-calls", toolCallList: [...] } }
  2. We execute the function and return { results: [{ toolCallId, result }] }
  3. Vapi reads the result string aloud (or uses it in the next LLM turn)
"""

import json
import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.models.patient import create_patient, find_by_phone, update_patient
from app.schemas import PatientCreate, PatientUpdate

router = APIRouter()
logger = logging.getLogger("routes.vapi")


# ─── Webhook entry point ──────────────────────────────────────────────────────

@router.post("/webhook")
async def vapi_webhook(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    message = body.get("message", {})
    event_type = message.get("type", "unknown")
    logger.info(f"[VAPI] Event received: {event_type}")

    # ── Tool calls ────────────────────────────────────────────────────────────
    if event_type == "tool-calls":
        tool_call_list = message.get("toolCallList") or message.get("toolCalls") or []
        results = [_handle_tool_call(tc) for tc in tool_call_list]
        return JSONResponse(content={"results": results})

    # ── End-of-call report ────────────────────────────────────────────────────
    if event_type == "end-of-call-report":
        call = message.get("call", {})
        transcript = message.get("transcript", "")
        logger.info(f"[VAPI] Call ended | id={call.get('id')} | transcript_preview={transcript[:200]}")
        return JSONResponse(content={"received": True})

    # ── All other events ──────────────────────────────────────────────────────
    return JSONResponse(content={"received": True})


# ─── Tool call dispatcher ─────────────────────────────────────────────────────

def _handle_tool_call(tool_call: dict) -> dict:
    tool_call_id = tool_call.get("id")
    fn = tool_call.get("function", {})
    fn_name = fn.get("name", "")
    raw_args = fn.get("arguments", "{}")

    # Arguments may arrive as a JSON string or already-parsed dict
    args: dict[str, Any] = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
    logger.info(f"[VAPI] Tool call: {fn_name} | args={json.dumps(args)}")

    try:
        if fn_name == "check_existing_patient":
            result = _check_existing(args)
        elif fn_name == "register_patient":
            result = _register_patient(args)
        elif fn_name == "update_patient":
            result = _update_patient(args)
        else:
            result = {"error": f"Unknown tool: {fn_name}"}
    except Exception as exc:
        logger.error(f"[VAPI] Tool error ({fn_name}): {exc}", exc_info=True)
        result = {"error": "An internal error occurred. Please try again."}

    return {"toolCallId": tool_call_id, "result": json.dumps(result)}


# ─── Tool implementations ─────────────────────────────────────────────────────

def _check_existing(args: dict) -> dict:
    """check_existing_patient — look up by phone before registering."""
    phone = args.get("phone_number", "")
    existing = find_by_phone(phone)

    if existing:
        logger.info(f"[VAPI] Existing patient found: {existing['patient_id']}")
        return {
            "found": True,
            "patient_id": existing["patient_id"],
            "first_name": existing["first_name"],
            "last_name": existing["last_name"],
            "message": (
                f"Found an existing record for {existing['first_name']} {existing['last_name']}."
            ),
        }

    return {
        "found": False,
        "message": "No existing record found for this phone number. Proceeding with new registration.",
    }


def _register_patient(args: dict) -> dict:
    """register_patient — validate and persist a new patient."""
    try:
        data = PatientCreate(**args)
    except ValidationError as e:
        errors = [f"{err['loc'][-1]}: {err['msg']}" for err in e.errors()]
        logger.warning(f"[VAPI] Validation failed: {errors}")
        return {
            "success": False,
            "errors": errors,
            "message": (
                f"I wasn't able to save the record. Here's what needs to be corrected: "
                + "; ".join(errors)
                + ". Could you please verify that information?"
            ),
        }

    patient = create_patient(data)
    short_id = patient["patient_id"].split("-")[0].upper()
    logger.info(f"[VAPI] Registered patient: {patient['patient_id']}")

    return {
        "success": True,
        "patient_id": patient["patient_id"],
        "message": (
            f"Your registration is complete! Your confirmation ID is {short_id}. "
            f"Welcome to our clinic, {patient['first_name']}."
        ),
    }


def _update_patient(args: dict) -> dict:
    """update_patient — partial update for returning callers."""
    patient_id = args.pop("patient_id", None)
    if not patient_id:
        return {"success": False, "message": "patient_id is required to update a record."}

    try:
        data = PatientUpdate(**args)
    except ValidationError as e:
        errors = [f"{err['loc'][-1]}: {err['msg']}" for err in e.errors()]
        return {
            "success": False,
            "errors": errors,
            "message": "I wasn't able to update the record: " + "; ".join(errors),
        }

    patient = update_patient(patient_id, data)
    if not patient:
        return {"success": False, "message": "I couldn't find that patient record to update."}

    short_id = patient["patient_id"].split("-")[0].upper()
    logger.info(f"[VAPI] Updated patient: {patient_id}")

    return {
        "success": True,
        "patient_id": patient["patient_id"],
        "message": f"Your record has been updated successfully. Confirmation ID: {short_id}.",
    }
