"""
Vapi webhook handler.

Vapi POSTs to this endpoint for:
  - type: "assistant-request"  → call just started, we auto-check caller's number
  - type: "tool-calls"         → agent needs to call a function
  - type: "end-of-call-report" → call summary / transcript

KEY: On "assistant-request", Vapi sends the REAL caller phone number automatically
in message.call.customer.number — we look them up immediately and inject context
into the assistant so it already knows if they're a returning patient before
the agent says a single word.
"""

import json
import logging
import os
import re
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.models.patient import create_patient, find_by_phone, update_patient
from app.schemas import PatientCreate, PatientUpdate

router = APIRouter()
logger = logging.getLogger("routes.vapi")

ASSISTANT_ID = os.getenv("VAPI_ASSISTANT_ID", "")  # set in Railway env vars


# ─── Webhook entry point ──────────────────────────────────────────────────────

@router.post("/webhook")
@router.post("/webhook/")
async def vapi_webhook(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    message = body.get("message", {})
    event_type = message.get("type", "unknown")
    logger.info(f"[VAPI] Event: {event_type}")

    # ── assistant-request: call just started ──────────────────────────────────
    # Vapi sends this BEFORE the agent speaks. We can inject variables here.
    if event_type == "assistant-request":
        return _handle_assistant_request(message)

    # ── Tool calls: agent wants to call a function ─────────────────────────────
    if event_type == "tool-calls":
        tool_call_list = message.get("toolCallList") or message.get("toolCalls") or []
        results = [_handle_tool_call(tc) for tc in tool_call_list]
        return JSONResponse(content={"results": results})

    # ── End of call report ────────────────────────────────────────────────────
    if event_type == "end-of-call-report":
        call = message.get("call", {})
        transcript = message.get("transcript", "")
        logger.info(
            f"[VAPI] Call ended | id={call.get('id')} | "
            f"transcript_preview={transcript[:300]}"
        )
        return JSONResponse(content={"received": True})

    return JSONResponse(content={"received": True})


# ─── assistant-request handler ────────────────────────────────────────────────

def _handle_assistant_request(message: dict) -> JSONResponse:
    """
    Called the moment an inbound call arrives, before the agent speaks.
    We read the real caller phone number from the call payload and check
    our DB. The result is injected as variableValues into the assistant,
    so the agent already knows on the very first line whether this is
    a new or returning patient.
    """
    call = message.get("call", {})
    customer = call.get("customer", {})
    raw_phone = customer.get("number", "")

    logger.info(f"[VAPI] Inbound call from: {raw_phone}")

    # Normalize to 10 digits
    digits = re.sub(r"\D", "", raw_phone)
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]

    caller_phone = digits  # e.g. "5551234567"

    # Look up in DB
    existing = find_by_phone(caller_phone) if caller_phone else None

    if existing:
        logger.info(f"[VAPI] Returning patient: {existing['patient_id']} — {existing['first_name']} {existing['last_name']}")
        variable_values = {
            "caller_phone":      caller_phone,
            "is_returning":      "true",
            "patient_id":        existing["patient_id"],
            "patient_first_name": existing["first_name"],
            "patient_last_name":  existing["last_name"],
        }
    else:
        logger.info(f"[VAPI] New caller: {caller_phone}")
        variable_values = {
            "caller_phone":      caller_phone,
            "is_returning":      "false",
            "patient_id":        "",
            "patient_first_name": "",
            "patient_last_name":  "",
        }

    # Return assistant config with injected variables
    response = {
        "assistantId": ASSISTANT_ID,
        "assistantOverrides": {
            "variableValues": variable_values
        }
    }
    return JSONResponse(content=response)


# ─── Tool call dispatcher ─────────────────────────────────────────────────────

def _handle_tool_call(tool_call: dict) -> dict:
    tool_call_id = tool_call.get("id")
    fn = tool_call.get("function", {})
    fn_name = fn.get("name", "")
    raw_args = fn.get("arguments", "{}")

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


# ─── Tool: check_existing_patient ────────────────────────────────────────────

def _check_existing(args: dict) -> dict:
    """Fallback tool — agent can still call this if needed."""
    phone = args.get("phone_number", "")
    existing = find_by_phone(phone)

    if existing:
        logger.info(f"[VAPI] Existing patient found: {existing['patient_id']}")
        return {
            "found": True,
            "patient_id":  existing["patient_id"],
            "first_name":  existing["first_name"],
            "last_name":   existing["last_name"],
            "message": f"Found existing record for {existing['first_name']} {existing['last_name']}.",
        }

    return {
        "found": False,
        "message": "No existing record found. Proceeding with new registration.",
    }


# ─── Tool: register_patient ───────────────────────────────────────────────────

def _register_patient(args: dict) -> dict:
    try:
        data = PatientCreate(**args)
    except ValidationError as e:
        errors = [f"{err['loc'][-1]}: {err['msg']}" for err in e.errors()]
        logger.warning(f"[VAPI] Validation failed: {errors}")
        return {
            "success": False,
            "errors":  errors,
            "message": (
                "I wasn't able to save the record. Here's what needs to be corrected: "
                + "; ".join(errors)
                + ". Could you please verify that information?"
            ),
        }

    patient = create_patient(data)
    short_id = patient["patient_id"].split("-")[0].upper()
    logger.info(f"[VAPI] Registered patient: {patient['patient_id']}")

    return {
        "success":    True,
        "patient_id": patient["patient_id"],
        "message": (
            f"Registration complete! Confirmation ID: {short_id}. "
            f"Welcome to our clinic, {patient['first_name']}."
        ),
    }


# ─── Tool: update_patient ─────────────────────────────────────────────────────

def _update_patient(args: dict) -> dict:
    patient_id = args.pop("patient_id", None)
    if not patient_id:
        return {"success": False, "message": "patient_id is required to update a record."}

    try:
        data = PatientUpdate(**args)
    except ValidationError as e:
        errors = [f"{err['loc'][-1]}: {err['msg']}" for err in e.errors()]
        return {
            "success": False,
            "errors":  errors,
            "message": "I wasn't able to update the record: " + "; ".join(errors),
        }

    patient = update_patient(patient_id, data)
    if not patient:
        return {"success": False, "message": "I couldn't find that patient record to update."}

    short_id = patient["patient_id"].split("-")[0].upper()
    logger.info(f"[VAPI] Updated patient: {patient_id}")

    return {
        "success":    True,
        "patient_id": patient["patient_id"],
        "message":    f"Your record has been updated. Confirmation ID: {short_id}.",
    }