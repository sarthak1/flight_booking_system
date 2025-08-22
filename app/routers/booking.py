from fastapi import APIRouter, HTTPException
from starlette.responses import FileResponse
import os
from typing import Optional

from app.core.db import SessionLocal, Booking, User

router = APIRouter()


def _find_booking_by_pnr(db, pnr: str) -> Optional[Booking]:
    # Simple scan over recent bookings; for small dev DBs this is fine
    q = db.query(Booking).order_by(Booking.created_at.desc()).all()
    for b in q:
        meta = b.flight_meta or {}
        if (meta or {}).get("pnr", "").upper() == pnr.upper():
            return b
    return None


@router.get("/booking/{pnr}")
def get_booking(pnr: str):
    db = SessionLocal()
    try:
        b = _find_booking_by_pnr(db, pnr)
        if not b:
            raise HTTPException(status_code=404, detail="PNR not found")
        meta = b.flight_meta or {}
        return {
            "id": b.id,
            "user_id": b.user_id,
            "pnr": meta.get("pnr"),
            "seats": meta.get("seats"),
            "gate": meta.get("gate"),
            "ticket_id": meta.get("ticket_id"),
            "ticket_url": meta.get("ticket_url"),
            "source": b.source_iata,
            "dest": b.dest_iata,
            "depart_at": b.depart_at,
            "price": str(b.price) if b.price is not None else None,
            "currency": b.currency,
        }
    finally:
        db.close()


@router.get("/tickets/by-pnr/{pnr}.pdf")
def get_ticket_pdf_by_pnr(pnr: str):
    db = SessionLocal()
    try:
        b = _find_booking_by_pnr(db, pnr)
        if not b:
            raise HTTPException(status_code=404, detail="PNR not found")
        meta = b.flight_meta or {}
        ticket_id = meta.get("ticket_id")
        if not ticket_id:
            raise HTTPException(status_code=404, detail="Ticket not found")
        pdf_path = os.path.join("tickets", f"{ticket_id}.pdf")
        if not os.path.exists(pdf_path):
            raise HTTPException(status_code=404, detail="Ticket file missing")
        return FileResponse(pdf_path, media_type="application/pdf", filename=f"{pnr}.pdf")
    finally:
        db.close()
