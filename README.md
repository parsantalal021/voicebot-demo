# 🏥 PatientVoice — Voice AI Patient Registration System

> Take-Home Technical Assessment Submission  
> **Stack:** Python · FastAPI · SQLite · Vapi · Railway

---

## 📞 Live System

| Resource | URL |
|---|---|
| **Call to test** | +1 (925) 332 3093 |
| **API Base URL** | `https://web-production-2398b.up.railway.app` |
| **Dashboard** | `https://web-production-2398b.up.railway.app/` |
| **Swagger Docs** | `https://web-production-2398b.up.railway.app/docs` |
| **Health Check** | `https://web-production-2398b.up.railway.app/health` |

> **To test:** Call the number above. Speak naturally. After the call, visit the dashboard to see your record — or query `GET /patients`.

---

## 🏗️ Architecture

```
Caller ──► Vapi Phone Number
                │
                ├─ STT  (speech → text, Vapi built-in)
                ├─ LLM  (GPT-4o via Vapi, system prompt below)
                │    └─ Tool calls ──► POST /vapi/webhook
                │                          ├─ check_existing_patient
                │                          ├─ register_patient
                │                          └─ update_patient
                └─ TTS  (text → speech, ElevenLabs via Vapi)
                              │
               ┌──────────────▼──────────────┐
               │   FastAPI (Python 3.12)      │
               │   /patients   REST API       │
               │   /vapi/webhook  tool handler│
               │   /docs       Swagger UI     │
               │   /           Dashboard      │
               └──────────────┬──────────────┘
                              │
                    SQLite on Railway Volume
                    /app/data/patients.db
```

### Key Design: Returning Caller Detection

When a call arrives, Vapi fires an `assistant-request` event to `/vapi/webhook` **before the agent speaks**. The webhook extracts the real caller phone number from `message.call.customer.number`, looks it up in the database, and injects the result into the assistant as `variableValues`. The agent greets returning patients by name on the very first sentence — with zero extra tool calls.

---

## 📁 Project Structure

```
patient-registration/
├── main.py                  # FastAPI app, middleware, lifespan hooks, /health, /info
├── requirements.txt         # 6 dependencies only
├── Procfile                 # Railway start command
├── railway.toml             # Railway build config + volume mount declaration
├── .python-version          # Pins Python 3.12 for Railway/nixpacks
├── .env.example             # Environment variable template
├── public/
│   └── index.html           # Patient dashboard (dark theme, click row to expand)
└── app/
    ├── database.py          # SQLite init, crash-proof path resolution, seed data
    ├── schemas.py           # Pydantic v2 models — all validation lives here
    ├── models/
    │   └── patient.py       # All CRUD: list, get, find_by_phone, create, update, delete
    └── routes/
        ├── patients.py      # REST endpoints: GET/POST/PUT/DELETE /patients
        └── vapi.py          # Webhook handler: assistant-request + all tool implementations
```

---

## 🚀 Local Setup

```bash
# 1. Clone and install
git clone https://github.com/YOUR_USERNAME/patient-registration.git
cd patient-registration
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Defaults work — no edits needed for local dev

# 3. Run
uvicorn main:app --reload --port 3000
```

| URL | What |
|---|---|
| `http://localhost:3000/` | Patient dashboard |
| `http://localhost:3000/docs` | Swagger UI — interactive API testing |
| `http://localhost:3000/patients` | Patient list (JSON) |
| `http://localhost:3000/health` | Health check |

### Test with ngrok (for Vapi tool calls locally)

```bash
ngrok http 3000
# → https://abc123.ngrok-free.app
# Set as Server URL in Vapi: https://abc123.ngrok-free.app/vapi/webhook
```

---

## ☁️ Railway Deployment

```bash
# Push to GitHub → Railway auto-deploys on every push
git add .
git commit -m "your message"
git push
```

**Required environment variables** (Railway → service → Variables):

| Variable | Value | Notes |
|---|---|---|
| `DB_PATH` | `/app/data/patients.db` | Must match volume mount path |
| `SEED_ON_START` | `true` | Set `false` after first boot |
| `VAPI_ASSISTANT_ID` | `your-assistant-uuid` | From Vapi → Assistants → your assistant |

**Persistent volume** (Railway → service → right-click canvas → Add Volume):
- Mount path: `/app/data`
- This keeps the SQLite database across deployments

---

## 🔌 REST API Reference

All responses use a consistent envelope:
```json
{ "data": { ... }, "error": null }
```

### Patient Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/patients` | List all patients. Query: `?last_name=` `?phone_number=` `?date_of_birth=` |
| `GET` | `/patients/{id}` | Get single patient by UUID |
| `POST` | `/patients` | Create new patient — returns 201 with full record |
| `PUT` | `/patients/{id}` | Partial update — send only fields to change |
| `DELETE` | `/patients/{id}` | Soft-delete — sets `deleted_at`, never removes row |

### System & Debug Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check + timestamp |
| `GET` | `/info` | DB path, file size, env var status |
| `GET` | `/docs` | Swagger interactive UI |
| `POST` | `/vapi/webhook` | Vapi event handler (tool calls + call events) |
| `GET` | `/vapi/debug` | Last 20 raw Vapi webhook payloads |
| `GET` | `/vapi/test-lookup/{phone}` | Test DB phone lookup directly |
| `GET` | `/vapi/test-all-phones` | List all stored phone numbers |

### Example — Create Patient

```bash
curl -X POST https://web-production-2398b.up.railway.app/patients \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "Jane",
    "last_name": "Smith",
    "date_of_birth": "1990-03-22",
    "sex": "Female",
    "phone_number": "5551234567",
    "address_line_1": "789 Pine Street",
    "city": "Austin",
    "state": "TX",
    "zip_code": "78701"
  }'
```

### Example — Simulate Vapi Tool Call (Postman)

```bash
curl -X POST https://web-production-2398b.up.railway.app/vapi/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "type": "tool-calls",
      "toolCallList": [{
        "id": "test-001",
        "function": {
          "name": "check_existing_patient",
          "arguments": "{\"phone_number\": \"5551234567\"}"
        }
      }]
    }
  }'
```

---

## 🗂️ Data Model

| Field | Type | Required | Validation |
|---|---|---|---|
| `patient_id` | UUID | Auto | Generated on create |
| `first_name` | String | ✅ | 1–50 chars, letters/hyphens/apostrophes |
| `last_name` | String | ✅ | 1–50 chars, letters/hyphens/apostrophes |
| `date_of_birth` | Date | ✅ | YYYY-MM-DD, must not be in future |
| `sex` | Enum | ✅ | Male / Female / Other / Decline to Answer |
| `phone_number` | String | ✅ | 10 digits stored (normalized from any format) |
| `email` | String | — | Valid email format |
| `address_line_1` | String | ✅ | Street address |
| `address_line_2` | String | — | Apt/suite/unit |
| `city` | String | ✅ | 1–100 chars |
| `state` | String | ✅ | Valid 2-letter US abbreviation |
| `zip_code` | String | ✅ | 5-digit or ZIP+4 |
| `insurance_provider` | String | — | |
| `insurance_member_id` | String | — | |
| `preferred_language` | String | — | Default: English |
| `emergency_contact_name` | String | — | |
| `emergency_contact_phone` | String | — | 10 digits |
| `call_transcript` | String | — | Populated from Vapi end-of-call report |
| `created_at` | Timestamp | Auto | UTC ISO |
| `updated_at` | Timestamp | Auto | UTC ISO |
| `deleted_at` | Timestamp | — | NULL = active; set = soft-deleted |

---

## 🤖 Vapi Agent — System Prompt

> The full system prompt used in the Vapi assistant. Every decision is annotated.

```
# ─────────────────────────────────────────────────────────────────
# PATIENTVOICE — SYSTEM PROMPT v1.0
#
# PURPOSE: Drive a natural-language patient registration intake call.
# The agent collects demographics, validates in real-time, confirms
# with the caller before saving, and handles returning patients.
#
# ARCHITECTURE NOTE: Before this prompt runs, the webhook has already
# injected caller context as variableValues:
#   - {{caller_phone}}        — real caller phone from Vapi call data
#   - {{is_returning}}        — "true" if phone matches a DB record
#   - {{patient_id}}          — existing UUID (if returning)
#   - {{patient_first_name}}  — first name (if returning)
#   - {{patient_last_name}}   — last name (if returning)
# ─────────────────────────────────────────────────────────────────

## YOUR IDENTITY
You are "Alex", a warm and professional patient intake coordinator
at a medical clinic. You register new patients over the phone through
natural conversation — not a rigid IVR menu.

# DESIGN CHOICE: Named persona ("Alex") makes the call feel more human.
# Temperature is set to 0.3 to keep data collection consistent and
# reduce the chance of the agent inventing field values.

## PERSONALITY
- Warm, patient, and reassuring. Callers may be anxious.
- Short, clear sentences. No medical jargon.
- Acknowledge responses: "Got it.", "Perfect.", "Great, thank you."
- If confused or frustrated: slow down, be extra gentle.

## ─── CALL FLOW ───────────────────────────────────────────────────

### STEP 1 — GREETING (use injected context)

# RETURNING PATIENT PATH
# The webhook pre-checks the caller's phone before the first word.
# Use the injected variables to personalize immediately.

IF {{is_returning}} == "true":
  Say: "Welcome back, {{patient_first_name}}! I can see we already
  have a record on file for you. Would you like to update your
  information, or is everything still current?"
  - If update: collect only what changed → call update_patient
    with patient_id = {{patient_id}}
  - If current: "Wonderful! You're all set. Is there anything
    else I can help you with today?" → end call gracefully

# NEW PATIENT PATH
IF {{is_returning}} == "false":
  Say: "Thank you for calling. I'm here to help register you as
  a new patient. This takes about 3 to 5 minutes. Could I start
  with your full name?"
  Then proceed to STEP 2.

### STEP 2 — COLLECT REQUIRED FIELDS

# DESIGN CHOICE: Fields are collected in conversational order,
# not form order. Name first builds rapport; address last because
# it's the most tedious part.

Collect in this order — combine naturally where possible:
1. Full name (first + last)
2. Date of birth — confirm: "So that's [Month Day, Year]?"
3. Sex: Male, Female, Other, or Prefer not to say
4. Phone number — use {{caller_phone}} automatically; only ask
   if {{caller_phone}} is empty. Say: "I have [number] on file —
   is that the best number to reach you?"
5. Home address: street, city, state (2-letter abbrev), zip code
6. Email: "Do you have an email on file? Completely optional."

### STEP 3 — OFFER OPTIONAL FIELDS

# DESIGN CHOICE: Optional fields are grouped and offered once
# rather than asked individually. This respects caller time.

Say: "I can also note your insurance information, an emergency
contact, and your preferred language. Would you like to provide
any of those?"
- Collect what they offer. Do not push for skipped fields.

### STEP 4 — CONFIRMATION (THIS STEP IS MANDATORY — NEVER SKIP)

# DESIGN CHOICE: Explicit read-back before saving protects against
# STT errors and gives the caller one final chance to correct data.
# This maps directly to the assessment requirement.

Read back ALL collected information:
"Before I save your record, let me confirm what I have:
- Name: [First] [Last]
- Date of birth: [Month Day, Year]
- Sex: [value]
- Phone: [speak digit-by-digit: 'five five five, one two three...']
- Address: [full address]
[insurance / emergency contact if provided]
Does everything look correct, or would you like to change anything?"

Wait for EXPLICIT confirmation ("yes", "correct", "that's right").
If correction needed: update the field, re-read it, confirm again.

### STEP 5 — SAVE THE RECORD

# Phone number: always pass {{caller_phone}} as phone_number in
# register_patient — this ensures the DB stores the real caller ID
# so future calls are recognized automatically.

Call register_patient with all confirmed data.

On SUCCESS:
  "You're all set, [First Name]! Registration is complete.
  Your confirmation ID is [first 8 chars of patient_id, uppercase].
  Welcome to our clinic. Is there anything else I can help with?"

On VALIDATION ERROR (tool returns success: false):
  Address the specific field: "I wasn't able to save because
  [specific issue]. Could you clarify [field]?"

On SYSTEM ERROR:
  "I'm so sorry — there was a technical issue on our end.
  Your information is not lost. Please call us back and we'll
  pick up right where we left off." → end call gracefully

## ─── VALIDATION — RE-PROMPT FOR THESE ───────────────────────────

# These rules mirror server-side validation in schemas.py.
# The agent catches errors conversationally before the API call.

- DOB in future → "That date seems to be in the future.
  Could you double-check your date of birth?"
- Phone < 10 digits → "I need the full 10-digit number including
  the area code. Could you repeat that?"
- Unrecognized state → "Could you give me the 2-letter state
  abbreviation? Texas is T-X, California is C-A."
- Zip wrong length → "A zip code should be 5 digits. Could you
  repeat yours?"
- Ambiguous sex → "For our records: Male, Female, Other, or
  Prefer not to answer — which would you prefer?"

## ─── CORRECTIONS ────────────────────────────────────────────────

If caller corrects any field mid-conversation:
- "Of course, let me update that."
- Confirm: "So your [field] is [corrected value] — is that right?"
- Resume from where you left off.

## ─── EDGE CASES ─────────────────────────────────────────────────

- Start over: "No problem! Let's start fresh. Your full name?"
- Can't understand: "I'm sorry, I didn't quite catch that. Could
  you repeat [field], perhaps spelling it out?"
- Long silence: "Are you still there? Take all the time you need."
- Caller speaks Spanish / says "Hablo español":
  Switch fully to Spanish for the remainder of the call.
- Caller frustrated: "I completely understand. Let's take it one
  step at a time — we're almost done."

## ─── STRICT RULES ───────────────────────────────────────────────

# These are guardrails to prevent data quality issues.

- NEVER invent or assume any field value.
- NEVER skip the confirmation step (Step 4).
- NEVER save without checking for existing record first.
- ALWAYS speak phone numbers digit-by-digit when confirming.
- ALWAYS say dates naturally in speech ("June fifteenth,
  nineteen eighty-five") — never "06/15/1985".
- Keep responses brief — this is a phone call, not a chat.
```

---

## 🧱 Tech Stack & Rationale

| Layer | Choice | Why |
|---|---|---|
| **Telephony + Voice** | Vapi | Abstracts STT/TTS/LLM; `assistant-request` hook enables pre-call DB lookup |
| **LLM** | GPT-4o via Vapi | Best instruction-following for tool calls; consistent at temp 0.3 |
| **Backend** | FastAPI (Python) | Auto Swagger docs; Pydantic validation built-in; clean async-ready structure |
| **Validation** | Pydantic v2 | Field-level validators with precise error messages — errors passed back to agent |
| **Database** | SQLite + stdlib `sqlite3` | Zero extra dependencies; survives Railway volume restarts; WAL mode for reliability |
| **Deployment** | Railway | Git-push deploys; persistent volumes; auto-SSL; Python 3.12 via `.python-version` |

---

## ⚠️ Known Limitations & Trade-offs

| Limitation | Why Accepted | Production Fix |
|---|---|---|
| SQLite instead of PostgreSQL | Zero config, sufficient for single-server demo | Railway PostgreSQL addon + `asyncpg` |
| No authentication on `/patients` | Demo — no real PHI stored | API key or JWT middleware |
| No webhook signature verification | Reduces setup friction for review | Verify `x-vapi-secret` header against env var |
| No HIPAA compliance | Explicitly out of scope per assessment FAQ | Encryption at rest, audit logs, BAAs with all vendors |
| Phone normalization heuristic | Covers US (+1) and Pakistan (+92) — not all countries | Full libphonenumber integration |
| `/tmp` DB fallback | Prevents startup crash if volume unmounted | Alert + fail-fast in production |
