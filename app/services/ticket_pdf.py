import os
import uuid
import random
from datetime import datetime, timedelta
from typing import Tuple, Optional

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF

from app.core.settings import settings


def _generate_pnr() -> str:
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # avoid 0/O/1/I
    return "".join(random.choice(alphabet) for _ in range(6))


def _assign_seat() -> str:
    row = random.randint(5, 30)
    seat = random.choice(list("ABCDEF"))
    return f"{row}{seat}"


def _assign_gate() -> str:
    letter = random.choice(list("ABCDEFGH"))
    num = random.randint(1, 25)
    return f"{letter}{num}"


def generate_ticket_pdf(info: dict, base_url: Optional[str] = None) -> Tuple[str, str, str, list[str], str]:
    """
    Generate a branded flight ticket PDF under ./tickets/{ticket_id}.pdf

    info expects keys: name, phone, source, dest, depart_at (ISO), flight (dict)
    base_url: if provided, embed https URL to the PDF in QR code
    Returns: (ticket_id, path, pnr, seat, gate)
    """
    ticket_id = uuid.uuid4().hex[:10]
    pnr = _generate_pnr()

    # Build passengers list
    passengers = info.get("passengers")
    if not passengers or not isinstance(passengers, list):
        passengers = [{"name": info.get("name") or "WhatsApp User", "email": info.get("email")}]  # single pax fallback

    # Assign seat/gate
    seats: list[str] = []
    gate = (info.get("gate") or _assign_gate()).upper()
    for p in passengers:
        seats.append(((p.get("seat") or _assign_seat()).upper()))

    os.makedirs("tickets", exist_ok=True)
    path = os.path.join("tickets", f"{ticket_id}.pdf")

    c = canvas.Canvas(path, pagesize=A4)
    width, height = A4

    # Brand header bar
    brand = getattr(settings, "FROM_NAME", None) or "Flight Booking"
    primary_hex = os.getenv("BRAND_PRIMARY", "#0b5fff")
    try:
        primary_color = colors.HexColor(primary_hex)
    except Exception:
        primary_color = colors.HexColor("#0b5fff")

    c.setFillColor(primary_color)
    c.rect(0, height - 40 * mm, width, 40 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(25 * mm, height - 22 * mm, brand)
    c.setFont("Helvetica", 10)
    c.drawString(25 * mm, height - 30 * mm, "E-Ticket Itinerary / Receipt")

    # Optional logo at top-left
    logo_path = os.getenv("BRAND_LOGO_PATH") or os.path.join("assets", "logo.png")
    try:
        if os.path.exists(logo_path):
            img = ImageReader(logo_path)
            c.drawImage(img, 10 * mm, height - 35 * mm, width=12 * mm, height=12 * mm, mask='auto')
    except Exception:
        pass

    # QR code at top-right
    qr_data = f"Ticket:{ticket_id}|PNR:{pnr}|Name:{(info.get('name') or '').strip()}"
    if base_url:
        qr_data = f"{base_url.rstrip('/')}/tickets/{ticket_id}.pdf"
    try:
        qr_code = qr.QrCodeWidget(qr_data)
        b = qr_code.getBounds()
        qr_w = 28 * mm
        qr_h = 28 * mm
        w = b[2] - b[0]
        h = b[3] - b[1]
        d = Drawing(qr_w, qr_h, transform=[qr_w / w, 0, 0, qr_h / h, 0, 0])
        d.add(qr_code)
        renderPDF.draw(d, c, width - 38 * mm, height - 36 * mm)
    except Exception:
        pass

    # Body details panel
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(20 * mm, height - 55 * mm, "Passenger & Flight Details")

    y = height - 70 * mm

    def line(label: str, value: str, bold_value: bool = False):
        nonlocal y
        c.setFont("Helvetica", 11)
        c.drawString(20 * mm, y, f"{label}:")
        c.setFont("Helvetica-Bold" if bold_value else "Helvetica", 11)
        c.drawString(60 * mm, y, value or "-")
        y -= 8 * mm

    flight = info.get("flight", {})
    depart_iso = info.get("depart_at") or ""
    try:
        depart_dt = datetime.fromisoformat(depart_iso.replace("Z", "+00:00")) if depart_iso else None
    except Exception:
        depart_dt = None
    depart_txt = depart_dt.strftime("%d %b %Y, %I:%M %p") if depart_dt else (depart_iso or "-")
    boarding_txt = (depart_dt - timedelta(minutes=45)).strftime("%I:%M %p") if depart_dt else "-"

    # Passenger summary
    primary_pax = passengers[0]
    line("Passenger", primary_pax.get("name") or "WhatsApp User", True)
    line("Phone", info.get("phone") or "-")
    line("PNR", pnr, True)
    line("From", info.get("source") or "-")
    line("To", info.get("dest") or "-")
    line("Flight", f"{flight.get('flight_no','-')} ({flight.get('airline','-')})")
    line("Departure", depart_txt)
    line("Boarding", boarding_txt)
    line("Gate", gate)
    # Passenger list
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, y, "Passengers")
    y -= 8 * mm
    c.setFont("Helvetica", 11)
    for i, p in enumerate(passengers, start=1):
        nm = p.get("name") or f"Passenger {i}"
        st = seats[i-1] if i-1 < len(seats) else "-"
        c.drawString(20 * mm, y, f"{i}. {nm} — Seat {st}")
        y -= 7 * mm
    y -= 2 * mm
    line("Duration", f"{flight.get('duration_min','-')} minutes")
    line("Fare", f"INR {flight.get('price','-')}")

    # Footer
    c.setFont("Helvetica-Oblique", 9)
    c.setFillColor(colors.grey)
    c.drawString(20 * mm, 18 * mm, f"Ticket ID: {ticket_id}  •  PNR: {pnr}")
    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, 13 * mm, "Please carry a valid photo ID. This is a system-generated ticket.")

    c.showPage()
    c.save()

    return ticket_id, path, pnr, seats, gate

