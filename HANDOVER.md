# Handover: PatientVoice Voice AI Registration System

This document provides an overview of the project, including architecture, setup, deployment, and key considerations. It is intended for a colleague taking over maintenance or further development.

---

## Overview

PatientVoice is a voice‑enabled patient registration application built with Python/ FastAPI and Vapi as the voice/LLM frontend. Callers dial a Vapi number, interact with an AI agent to supply demographic information, and the backend persists records in an SQLite database. A dashboard allows staff to view and manage patient data.

Key features:
- LLM-driven phone registration (GPT-4o via Vapi)
- REST API for patient CRUD (`/patients`)
- Dashboard served from `public/index.html` with search, stats, form, and transcript viewing
- Supports international phone numbers and simple soft-delete logic
- Deployment target: Railway (Nixpacks + persistent volume)

---

## Repository Structure

```
patient-registration/
├── main.py               # FastAPI app and lifespan hooks
├── requirements.txt
├── Procfile              # Railway start command
├── railway.toml          # Railway configuration (builder, healthcheck, volume)
├── .env.example
├── public/               # Static dashboard assets
│   └── index.html
└── app/
    ├── database.py       # SQLite initialization, schema, seed data
    ├── schemas.py        # Pydantic v2 models + validation/normalization
    ├── models/
    │   └── patient.py    # DB CRUD and helper functions
    └── routes/
        ├── patients.py   # API router endpoints
        └── vapi.py       # Vapi webhook handler + tool implementations
```

---

## Local Development

1. Clone repo and create venv:
   ```bash
   git clone <repo>
   cd patient-registration
   python -m venv venv
   .\venv\Scripts\activate    # Windows
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` (only used locally).
3. Launch server:
   ```bash
   uvicorn main:app --reload --port 3000
   ```
4. API endpoints:
   - `GET /patients` (with `?last_name`, `?phone_number`, `?date_of_birth` filters)
   - `GET /patients/{id}`
   - `POST /patients` to create
   - `PUT /patients/{id}` to update
   - `DELETE /patients/{id}` (soft delete)
   - `POST /vapi/webhook` receives Vapi events and tool calls
   - `GET /health` returns simple status JSON
5. Access dashboard at `http://localhost:3000/`.

---

## Vapi Assistant Configuration

- Use Vapi.ai dashboard to create assistant with prompts as specified in README.
- Tools:
  * `check_existing_patient` (phone_number string)
  * `register_patient` (full patient schema)
  * `update_patient` (partial update schema)
- Voice: ElevenLabs Rachel, model GPT-4o, etc.
- Server URL set to `<your domain>/vapi/webhook` (or ngrok http for local testing).

The system prompt in README contains full conversational guidance and must be copied exactly.

---

## Database

SQLite used for simplicity. The path is `/app/data/patients.db` inside the Railway volume. Schema defined in `app/database.py`:

- `patients` table with all fields plus `created_at`, `updated_at`, `deleted_at`.
- Normalization ensures phone numbers and dates are stored consistently.

Seed data added when `SEED_ON_START=true`.

---

## Deployment on Railway

1. Push repo to GitHub.
2. Create Railway project from repo; set service variables: `PORT=3000`, `SEED_ON_START=true`, `DB_PATH=/app/data/patients.db`.
3. Add volume mount at `/app/data` (persists SQLite DB).
4. Railway builds with Nixpacks; Python 3.12 specified in `railway.toml`.
5. Healthcheck path `/health`; ensure `startCommand` is correct.
6. On deploy, logs show DB init and app ready; if healthcheck fails, inspect logs for startup errors.

---

## Important Code Notes

- Phone normalization in `app/schemas.normalize_phone` accepts international numbers; validators use it.
- `app/models/patient.find_by_phone` handles suffix matching for duplicates.
- Frontend formatting removed US-only assumption; shows raw number.
- Modal forms and CRUD logic in `public/index.html` allow create/edit/delete.
- README contains detailed API reference and handshake for Vapi.

---

## Maintenance Suggestions

- Add authentication to API (currently public).
- Migrate from SQLite to PostgreSQL for production scaling.
- Add request validation and rate limiting (e.g., using `slowapi`).
- Implement webhook signature verification (check `x-vapi-secret`).
- Add unit/integration tests (`pytest` + `httpx`).
- Consider upgrading to asynchronous DB driver if scaling beyond SQLite.

---

## Troubleshooting

- **Healthcheck failures**: check Railway logs, ensure `PORT` env var set and app starts cleanly.
- **Vapi 502 errors**: verify webhook URL reachable, watch logs for exceptions.
- **Phone lookup problems**: examine normalization rules and suffix logic in `find_by_phone`.
- **UI issues**: refresh static file or inspect JS console for errors.

---

## Contact

For questions about architecture or code, reach out to the original developer or consult the README for detailed setup instructions.