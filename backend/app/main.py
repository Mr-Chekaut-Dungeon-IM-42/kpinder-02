import subprocess

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DisconnectionError, OperationalError

from app.auth.router import router as auth_router
from app.chat.router import router as chat_router
from app.matching.router import router as matching_router
from app.shared.config import settings


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


_GIT_SHA = _git_sha()

app = FastAPI(
    title="Kpinder API",
    description="Dating service MVP API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(matching_router)
app.include_router(chat_router)


@app.exception_handler(OperationalError)
@app.exception_handler(DisconnectionError)
def db_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": "Service unavailable"})


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version")
def version() -> dict[str, str]:
    return {"sha": _GIT_SHA}
