from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.deps import DB

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz():
    return {"ok": True}


@router.get("/readyz")
async def readyz(session: DB):
    try:
        await session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        return JSONResponse({"db": "down", "queue": "unknown"}, status_code=503)
    return {"db": "ok", "queue": "ok"}
