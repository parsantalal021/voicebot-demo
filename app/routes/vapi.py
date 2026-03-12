"""
Vapi webhook handler.

FIXED:
- Robust phone extraction from all possible Vapi payload locations
- Debug endpoint to see exactly what Vapi sends
- Works even without VAPI_ASSISTANT_ID (uses assistantOverrides only)
- check_existing_patient tool also works as manual fallback
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

ASSISTANT_ID = os.getenv("VAPI_ASSISTANT_ID", "")

# Stores last 50 raw webhook payloads for debugging
_debug_log: list[dict] = []


# ─── Debug endpoint ───────────────────────────────────────────────────────────

@router.get("/debug")
def get_debug_log():
    """
    Visit /vapi/debug after a call to see exactly what Vapi sent.
    This tells us where the phone number is coming from.
    """
    return JSONResponse(content={
        "total_events": len(_debug_log),
        "last_20": _debug_log[-20:],
    })


@router.delete("/debug")
def clear_debug_log():
    _debug_log.clear()
    return JSONResponse(content={"cleared": True})


# ─── Main webhook ─────────────────────────────────────────────────────────────

@router.post("/webhook")
@router.post("/webhook/")
async def vapi_webhook(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    message = body.get("message", {})
    event_type = message.get("type", "unknown")

    # ── Log everything for debugging ──────────────────────────────────────────
    call     = message.get("call", {})
    customer = call.get("customer", {})
    _debug_log.append({
        "event_type":            event_type,
        "call_id":               call.get("id", ""),
        # Every possible phone number location in Vapi payload:
        "customer.number":       customer.get("number", ""),
        "customer.phoneNumber":  customer.get("phoneNumber", ""),
        "call.from":             call.get("from", ""),
        "call.callerPhoneNumber": call.get("callerPhoneNumber", ""),
        "message.from":          message.get("from", ""),
        "call_keys":             list(call.keys()),
        "customer_keys":         list(customer.keys()),
    })
    # Keep only last 50
    if len(_debug_log) > 50:
        _debug_log.pop(0)

    logger.info(f"[VAPI] Event={event_type} | customer={customer} | call_keys={list(call.keys())}")

    # ── Route events ──────────────────────────────────────────────────────────
    if event_type == "assistant-request":
        return _handle_assistant_request(message)

    if event_type == "tool-calls":
        tool_call_list = message.get("toolCallList") or message.get("toolCalls") or []
        results = [_handle_tool_call(tc) for tc in tool_call_list]
        return JSONResponse(content={"results": results})

    if event_type == "end-of-call-report":
        logger.info(f"[VAPI] Call ended | id={call.get('id')} | transcript={message.get('transcript','')[:200]}")
        return JSONResponse(content={"received": True})

    return JSONResponse(content={"received": True})


# ─── Phone normalizer ─────────────────────────────────────────────────────────

def _normalize_phone(raw: str) -> str:
    """
    Strip everything except digits.
    Remove leading country codes (1 for US, 92 for Pakistan, etc).
    Return 10-digit string or empty string if invalid.
    """
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)

    # Remove leading 1 (US country code) if 11 digits
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]

    # Remove leading 92 (Pakistan country code) if 12 digits
    if len(digits) == 12 and digits[:2] == "92":
        digits = digits[2:]

    # Remove leading 0 (local format in some countries) if 11 digits
    if len(digits) == 11 and digits[0] == "0":
        digits = digits[1:]

    return digits if len(digits) == 10 else digits  # return whatever we have


def _extract_caller_phone(message: dict) -> str:
    """Try every known location Vapi puts the caller's number."""
    call     = message.get("call", {})
    customer = call.get("customer", {})

    candidates = [
        customer.get("number", ""),
        customer.get("phoneNumber", ""),
        call.get("from", ""),
        call.get("callerPhoneNumber", ""),
        message.get("from", ""),
    ]

    for raw in candidates:
        if raw and raw.strip():
            normalized = _normalize_phone(raw.strip())
            logger.info(f"[VAPI] Phone candidate raw='{raw}' → normalized='{normalized}'")
            if normalized:
                return normalized

    logger.warning(f"[VAPI] No phone number found. call keys={list(call.keys())} customer keys={list(customer.keys())}")
    return ""


# ─── assistant-request handler ────────────────────────────────────────────────

def _handle_assistant_request(message: dict) -> JSONResponse:
    caller_phone = _extract_caller_phone(message)
    logger.info(f"[VAPI] assistant-request | caller_phone='{caller_phone}'")

    # Look up by phone
    existing = None
    if caller_phone:
        existing = find_by_phone(caller_phone)
        logger.info(f"[VAPI] DB lookup for '{caller_phone}' → {'FOUND' if existing else 'NOT FOUND'}")

    if existing:
        logger.info(f"[VAPI] RETURNING: {existing['first_name']} {existing['last_name']} ({existing['patient_id']})")
        variables = {
            "caller_phone":       caller_phone,
            "is_returning":       "true",
            "patient_id":         existing["patient_id"],
            "patient_first_name": existing["first_name"],
            "patient_last_name":  existing["last_name"],
        }
    else:
        logger.info(f"[VAPI] NEW caller: '{caller_phone}'")
        variables = {
            "caller_phone":       caller_phone,
            "is_returning":       "false",
            "patient_id":         "",
            "patient_first_name": "",
            "patient_last_name":  "",
        }

    overrides = {"variableValues": variables}

    # With assistant ID → tell Vapi which assistant to use + inject variables
    # Without assistant ID → just inject variables (Vapi uses the one linked to the phone number)
    if ASSISTANT_ID:
        return JSONResponse(content={
            "assistantId":       ASSISTANT_ID,
            "assistantOverrides": overrides,
        })
    else:
        return JSONResponse(content={
            "assistantOverrides": overrides,
        })


# ─── Tool call dispatcher ─────────────────────────────────────────────────────

def _handle_tool_call(tool_call: dict) -> dict:
    tool_call_id = tool_call.get("id")
    fn           = tool_call.get("function", {})
    fn_name      = fn.get("name", "")
    raw_args     = fn.get("arguments", "{}")

    args: dict[str, Any] = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
    logger.info(f"[VAPI] Tool={fn_name} args={json.dumps(args)}")

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
    """
    Manual fallback — agent calls this with whatever phone number the caller says.
    Also handles email lookup as a secondary method.
    """
    phone = args.get("phone_number", "")
    existing = find_by_phone(phone) if phone else None

    if existing:
        logger.info(f"[VAPI] Tool found patient: {existing['patient_id']}")
        return {
            "found":      True,
            "patient_id": existing["patient_id"],
            "first_name": existing["first_name"],
            "last_name":  existing["last_name"],
            "message":    f"Found record for {existing['first_name']} {existing['last_name']}.",
        }

    return {
        "found":   False,
        "message": "No record found for that phone number.",
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
            "message": "Could not save record. Issues: " + "; ".join(errors),
        }

    patient  = create_patient(data)
    short_id = patient["patient_id"].split("-")[0].upper()
    logger.info(f"[VAPI] Registered: {patient['patient_id']}")
    return {
        "success":    True,
        "patient_id": patient["patient_id"],
        "message":    f"Registration complete! ID: {short_id}. Welcome, {patient['first_name']}.",
    }


# ─── Tool: update_patient ─────────────────────────────────────────────────────

def _update_patient(args: dict) -> dict:
    patient_id = args.pop("patient_id", None)
    if not patient_id:
        return {"success": False, "message": "patient_id is required."}

    try:
        data = PatientUpdate(**args)
    except ValidationError as e:
        errors = [f"{err['loc'][-1]}: {err['msg']}" for err in e.errors()]
        return {"success": False, "errors": errors,
                "message": "Could not update: " + "; ".join(errors)}

    patient = update_patient(patient_id, data)
    if not patient:
        return {"success": False, "message": "Patient not found."}

    short_id = patient["patient_id"].split("-")[0].upper()
    logger.info(f"[VAPI] Updated: {patient_id}")
    return {
        "success":    True,
        "patient_id": patient["patient_id"],
        "message":    f"Record updated. Confirmation ID: {short_id}.",
    }