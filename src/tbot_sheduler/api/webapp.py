"""Web App static file serving."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["webapp"])

WEBAPP_DIR = Path(__file__).resolve().parent.parent / "webapp"


@router.get("/webapp/create-slots", response_class=HTMLResponse)
async def create_slots_page() -> str:
    """Serve the admin slot creation Web App."""
    file_path = WEBAPP_DIR / "create_slots.html"
    if file_path.exists():
        return HTMLResponse(file_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Web App not found</h1>", status_code=404)


@router.get("/webapp/book", response_class=HTMLResponse)
async def booking_page() -> HTMLResponse:
    """Serve the user booking Web App."""
    file_path = WEBAPP_DIR / "book.html"
    if file_path.exists():
        return HTMLResponse(file_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Web App not found</h1>", status_code=404)
