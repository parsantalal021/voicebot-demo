import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.database import init_db, seed_db
from app.routes import patients, vapi

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


# ─── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database…")
    init_db()
    if os.getenv("SEED_ON_START", "false").lower() == "true":
        seed_db()
    logger.info("Server ready.")
    yield
    logger.info("Server shutting down.")


# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Patient Registration API",
    description="Voice AI Patient Registration System — REST API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routes ───────────────────────────────────────────────────────────────────
app.include_router(patients.router, prefix="/patients", tags=["Patients"])
app.include_router(vapi.router, prefix="/vapi", tags=["Vapi"])


@app.get("/health", tags=["Health"])
def health():
    from datetime import datetime, timezone
    return {"data": {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}, "error": None}


# ─── Global exception handler ─────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"data": None, "error": {"message": "Internal server error"}},
    )


# ─── Static files (dashboard) ─────────────────────────────────────────────────
static_dir = os.path.join(os.path.dirname(__file__), "public")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
