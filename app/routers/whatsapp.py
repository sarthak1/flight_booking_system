from fastapi import APIRouter, Request, Response, HTTPException
from urllib.parse import parse_qs
from app.core.redis import get_session, set_session, clear_session
from app.core.db import SessionLocal, User, Booking
from app.core.settings import settings
from app.services.iata import to_iata
from app.services.timeparse import parse_natural, quick_picks
from app.services.flight_search import mock_search
# from app.services.payments import create_checkout_session
from app.services.whatsapp_sender import send_whatsapp_text
from app.services.ticket_pdf import generate_ticket_pdf
from app.services.base_url import get_public_base_url
from datetime import datetime, timedelta
from decimal import Decimal
from html import escape
import pytz
import re
import calendar

router = APIRouter()

POPULAR_SOURCES = ["Mumbai", "Delhi", "Bengaluru", "Other"]
POPULAR_DESTS = ["Delhi", "Hyderabad", "Goa", "Other"]


def twilio_form(body_bytes: bytes) -> dict:
    # Twilio sends application/x-www-form-urlencoded
    q = parse_qs(body_bytes.decode())
    return {k: v[0] for k, v in q.items()}


def msg(text: str) -> Response:
    # Respond with TwiML so Twilio sends the message back to the user
    body = f"""
    <Response>
        <Message>{escape(text)}</Message>
    </Response>
    """.strip()
    return Response(content=body, media_type="application/xml")


@router.post("/webhook")
async def whatsapp_webhook(request: Request):
    raw = await request.body()
    form = twilio_form(raw)
    from_number = form.get("From", "").replace("whatsapp:", "")
    body = (form.get("Body") or "").strip()
    print("body", body)
    if not from_number:
        raise HTTPException(status_code=400, detail="Invalid sender")

    # Quick lookups: 'ticket' and 'pnr ABC123'
    low = body.lower()
    if low.startswith("pnr "):
        pnr_code = body.split(None, 1)[1].strip()
        db2 = SessionLocal()
        try:
            bookings = db2.query(Booking).order_by(Booking.created_at.desc()).all()
            found = None
            for b in bookings:
                meta = b.flight_meta or {}
                if (meta.get("pnr") or "").upper() == pnr_code.upper():
                    found = meta
                    break
            if found and found.get("ticket_url"):
                return msg(f"PNR {pnr_code}: {found['ticket_url']}")
            else:
                return msg("PNR not found.")
        finally:
            db2.close()
    if low.strip() == "ticket":
        db2 = SessionLocal()
        try:
            # Latest booking for this user
            user_bookings = db2.query(Booking).filter(Booking.user_id == db2.query(User).filter(User.whatsapp_number==from_number).first().id).order_by(Booking.created_at.desc()).all()
            meta = user_bookings[0].flight_meta if user_bookings else None
            if meta and meta.get("ticket_url"):
                return msg(f"Your latest ticket: {meta['ticket_url']}")
            return msg("No ticket found yet. Reply 'Restart' to book.")
        except Exception:
            return msg("No ticket found yet. Reply 'Restart' to book.")
        finally:
            db2.close()

    # Allow restart at any time before proceeding with FSM
    if body.lower() in ("restart", "start"):
        try:
            clear_session(from_number)
            print("body1", body)
        except Exception:
            pass
        return msg("Restarted. Where are you flying from?\n1) Mumbai  2) Delhi  3) Bengaluru  4) Other")

    db = SessionLocal()
    try:
        # Ensure user exists
        user = db.query(User).filter(User.whatsapp_number == from_number).first()
        if not user:
            user = User(whatsapp_number=from_number)
            db.add(user)
            db.commit()
            db.refresh(user)
        print("body2", body)
        # Load session; if Redis is unavailable, fall back to in-memory ephemeral session per request
        try:
            session = get_session(from_number) or {"step": "source", "timezone": settings.DEFAULT_TIMEZONE}
        except Exception:
            session = {"step": "source", "timezone": settings.DEFAULT_TIMEZONE}
        step = session.get("step", "source")
        tz = pytz.timezone(session.get("timezone", settings.DEFAULT_TIMEZONE))
        now = datetime.now(tz)
        print("body3", body)
        # Backward-compatible confirm handler (works even if prior session step was 'payment')
        if body.strip().lower() == "confirm" or step == "payment":
            if body.strip().lower() != "confirm":
                # If step=='payment' but not confirmed yet, prompt
                return msg("Please reply 'confirm' to generate your ticket PDF, or 'Restart' to start over.")
            flights = session.get("presented_flights", [])
            selected_id = session.get("selected_flight_id")
            selected = next((f for f in flights if f.get("id") == selected_id), None)
            if not selected:
                session["step"] = "flights"
                try:
                    set_session(from_number, session)
                except Exception:
                    pass
                return msg("Session expired. Please pick a flight again: reply 'Restart' to start over.")
            base_url = get_public_base_url()
            ticket_info = {
                "name": session.get("passenger_name") or "WhatsApp User",
                "phone": from_number,
                "source": session.get("source_iata"),
                "dest": session.get("dest_iata"),
                "depart_at": session.get("travel_dt_iso"),
                "flight": selected,
            }
            try:
                # Build passengers list for PDF
                pax_list = session.get("passengers") or ([{"name": session.get("passenger_name") or "WhatsApp User", "email": session.get("passenger_email")}] )
                # Apply chosen seats if present
                chosen = session.get("assigned_seats")
                if chosen and isinstance(chosen, list):
                    for i in range(min(len(pax_list), len(chosen))):
                        pax_list[i]["seat"] = chosen[i]
                ticket_info["passengers"] = pax_list
                ticket_id, _path, pnr, seats, gate = generate_ticket_pdf(ticket_info, base_url=base_url)
                seats_str = ", ".join(seats) if isinstance(seats, list) else str(seats)
                pdf_url = f"{base_url}/tickets/{ticket_id}.pdf"
                try:
                    send_whatsapp_text(from_number, f"Your flight ticket is ready. PNR: {pnr} • Seats: {seats_str} • Gate: {gate}\\nDownload: {pdf_url}", media_url=pdf_url)
                except Exception:
                    pass
                # Persist booking
                try:
                    # price may be Decimal; ensure numeric
                    price_val = None
                    try:
                        price_val = Decimal(str((selected.get('price'))))
                    except Exception:
                        pass
                    # Friendly local time string
                    try:
                        dt_iso = session.get('travel_dt_iso')
                        dt_obj = datetime.fromisoformat(dt_iso.replace('Z','+00:00')) if dt_iso else None
                        friendly = dt_obj.astimezone(tz).strftime('%Y-%m-%d %I:%M %p %Z') if dt_obj else None
                    except Exception:
                        friendly = None
                    booking = Booking(
                        user_id=user.id,
                        source_iata=session.get('source_iata'),
                        dest_iata=session.get('dest_iata'),
                        depart_at=session.get('travel_dt_iso'),
                        flight_meta={
                            "selected": selected.get('id'),
                            "pnr": pnr,
                            "seats": seats,
                            "gate": gate,
                            "ticket_id": ticket_id,
                            "ticket_url": pdf_url,
                            "passengers": pax_list,
                            "depart_at_iso": session.get('travel_dt_iso'),
                            "depart_at_local": friendly,
                            "timezone": tz.zone,
                        },
                        price=price_val,
                        currency='INR',
                        payment_status='issued',
                    )
                    db.add(booking)
                    db.commit()
                except Exception:
                    pass
                try:
                    clear_session(from_number)
                except Exception:
                    pass
                return msg(f"Ticket generated ✅ (PNR: {pnr}, Seats: {seats_str}, Gate: {gate})\\nDownload: {pdf_url}")
            except Exception:
                return msg("Could not generate ticket right now. Please try again in a moment or reply 'Restart'.")
        # FSM
        if step == "source":
            print("body4", body)
            # Only prompt if no input provided; otherwise process the input directly
            if not body:
                print("body512", body)
                if not session.get("source_prompted"):
                    print("body51", body)
                    session.update({"source_prompted": True})
                    try:
                        set_session(from_number, session)
                    except Exception:
                        pass
                return msg("Where are you flying from?\n1) Mumbai  2) Delhi  3) Bengaluru  4) Other")
            choice_map = {"1": "Mumbai", "2": "Delhi", "3": "Bengaluru", "4": "Other"}
            print("body52", body)
            choice = choice_map.get(body)
            city = choice or body
            if (choice == "Other"):
                return msg("Please enter your source city (e.g., Mumbai)")
            iata = to_iata(city)
            if not iata:
                return msg("I couldn't recognize that city. Try again (e.g., Mumbai)")
            session.update({"source_city": city, "source_iata": iata, "step": "destination"})
            try:
                set_session(from_number, session)
            except Exception:
                pass
            return msg("Where are you flying to?\n1) Delhi  2) Hyderabad  3) Goa  4) Other")

        if step == "destination":
            print("body5", body)
            choice_map = {"1": "Delhi", "2": "Hyderabad", "3": "Goa", "4": "Other"}
            choice = choice_map.get(body)
            city = choice or body
            if (choice == "Other"):
                return msg("Please enter your destination city (e.g., Delhi)")
            iata = to_iata(city)
            if not iata:
                return msg("I couldn't recognize that city. Try again (e.g., Delhi)")
            if iata == session.get("source_iata"):
                return msg("Destination must be different from source. Please enter another destination.")
            session.update({"dest_city": city, "dest_iata": iata, "step": "date"})
            try:
                set_session(from_number, session)
            except Exception:
                pass
            # Show a simple calendar for this and next month
            cal = calendar.TextCalendar()
            this_month = cal.formatmonth(now.year, now.month)
            next_month_dt = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
            next_month = cal.formatmonth(next_month_dt.year, next_month_dt.month)
            # Also compute the month after next for a broader view
            month_after_next_dt = (next_month_dt + timedelta(days=32)).replace(day=1)
            month_after_next = cal.formatmonth(month_after_next_dt.year, month_after_next_dt.month)
            prompt = (
                "Please enter your travel date (YYYY-MM-DD or DD/MM/YYYY), optionally time (HH:MM or 9am).\n"
                "Example: 2025-09-03 09:30\n"
                "It must be a future date.\n\n" \
                + this_month + "\n" + next_month + "\n" + month_after_next
            )
            return msg(prompt)

        if step == "date":
            print("body6", body)
            # Accept date with optional time; enforce minimum advance window and blackout dates
            text = body.strip()
            dt_date: datetime | None = None
            dt_time_tuple = (10, 0)  # default time
            has_time = False

            # Patterns
            m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2})(?::(\d{2}))?\s*(am|pm)?)?", text, re.IGNORECASE)
            if m:
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                hh = int(m.group(4)) if m.group(4) else None
                mm = int(m.group(5)) if m.group(5) else 0
                ap = (m.group(6) or "").lower()
                if hh is not None:
                    has_time = True
                    if ap in ("am", "pm"):
                        if hh == 12:
                            hh = 0
                        if ap == "pm":
                            hh += 12
                    dt_time_tuple = (hh, mm)
                try:
                    dt_date = tz.localize(datetime(y, mo, d))
                except Exception:
                    dt_date = None
            else:
                m2 = re.fullmatch(r"(\d{2})[/-](\d{2})[/-](\d{4})(?:\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?)?", text, re.IGNORECASE)
                if m2:
                    d, mo, y = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
                    hh = int(m2.group(4)) if m2.group(4) else None
                    mm = int(m2.group(5)) if m2.group(5) else 0
                    ap = (m2.group(6) or "").lower()
                    if hh is not None:
                        has_time = True
                        if ap in ("am", "pm"):
                            if hh == 12:
                                hh = 0
                            if ap == "pm":
                                hh += 12
                        dt_time_tuple = (hh, mm)
                    try:
                        dt_date = tz.localize(datetime(y, mo, d))
                    except Exception:
                        dt_date = None

            if not dt_date:
                # Re-prompt with three-month calendar
                cal = calendar.TextCalendar()
                this_month = cal.formatmonth(now.year, now.month)
                next_month_dt = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
                next_month = cal.formatmonth(next_month_dt.year, next_month_dt.month)
                month_after_next_dt = (next_month_dt + timedelta(days=32)).replace(day=1)
                month_after_next = cal.formatmonth(month_after_next_dt.year, month_after_next_dt.month)
                return msg("Invalid date. Please enter YYYY-MM-DD (optional time HH:MM).\n\n" + this_month + "\n" + next_month + "\n" + month_after_next)

            # If time not provided, prompt selectable times
            if not has_time:
                # store the date and ask for time
                session["travel_date_iso"] = dt_date.strftime("%Y-%m-%d")
                # build time options
                base_times = [(6,0), (9,0), (12,0), (15,0), (18,0), (21,0)]
                min_delta = timedelta(hours=getattr(settings, 'MIN_ADVANCE_HOURS', 12))
                options: list[str] = []
                for hh, mm in base_times:
                    candidate = dt_date.replace(hour=hh, minute=mm)
                    if candidate >= now + min_delta:
                        options.append(f"{hh:02d}:{mm:02d}")
                if not options:
                    session["time_choices"] = []
                    session["step"] = "time"
                    try:
                        set_session(from_number, session)
                    except Exception:
                        pass
                    return msg("All preset times have passed for that date. Reply with a custom time in HH:MM (24h) or 9am/9pm.")
                session["time_choices"] = options
                session["step"] = "time"
                try:
                    set_session(from_number, session)
                except Exception:
                    pass
                labels = [f"{i+1}) {t}" for i, t in enumerate(options[:6])]
                return msg("Select a time or reply a custom time (HH:MM):\n" + "  ".join(labels))

            # If time provided with date, validate and proceed
            depart_dt = dt_date.replace(hour=dt_time_tuple[0], minute=dt_time_tuple[1], second=0, microsecond=0)

            # Blackout dates check
            try:
                blackout_raw = settings.BLACKOUT_DATES or ""
                blackout_set = {s.strip() for s in blackout_raw.split(',') if s.strip()}
            except Exception:
                blackout_set = set()
            if depart_dt.strftime("%Y-%m-%d") in blackout_set:
                return msg("Selected date is unavailable. Please choose another date.")

            # Enforce minimum advance window
            min_delta = timedelta(hours=getattr(settings, 'MIN_ADVANCE_HOURS', 12))
            if depart_dt < now + min_delta:
                return msg(f"Please choose a time at least {int(min_delta.total_seconds()//3600)} hours from now.")

            iso = depart_dt.isoformat()
            session.update({"travel_dt_iso": iso, "step": "flights"})
            try:
                set_session(from_number, session)
            except Exception:
                pass
            # Show flights
            flights = mock_search(session["source_iata"], session["dest_iata"], depart_dt)
            session["presented_flights"] = flights
            try:
                set_session(from_number, session)
            except Exception:
                pass
            lines = []
            for idx, f in enumerate(flights, start=1):
                dep = f['depart'][11:16]
                arr = f['arrive'][11:16]
                lines.append(f"{idx}) {f['flight_no']} {dep}-{arr}, {f['duration_min']}m, INR {f['price']}")
            lines.append("Reply with 1, 2, or 3 to select a flight.")
            return msg("\n".join(lines))

        if step == "time":
            # Choose time for previously selected date
            text = body.strip().lower()
            choices = session.get("time_choices", [])
            parsed_hhmm = None
            if text.isdigit() and choices:
                i = int(text) - 1
                if 0 <= i < len(choices):
                    parsed_hhmm = choices[i]
            if not parsed_hhmm:
                # Accept HH:MM or hham/pm
                m = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
                if m:
                    hh, mm = int(m.group(1)), int(m.group(2))
                    if 0 <= hh <= 23 and 0 <= mm <= 59:
                        parsed_hhmm = f"{hh:02d}:{mm:02d}"
                else:
                    m2 = re.fullmatch(r"(\d{1,2})\s*(am|pm)", text)
                    if m2:
                        hh = int(m2.group(1))
                        ap = m2.group(2).lower()
                        if 1 <= hh <= 12:
                            if hh == 12:
                                hh = 0
                            if ap == 'pm':
                                hh += 12
                            parsed_hhmm = f"{hh:02d}:00"
            if not parsed_hhmm:
                return msg("Invalid time. Reply with a number from the list or HH:MM (24h) or 9am/9pm.")
            y, mo, d = map(int, session.get("travel_date_iso").split("-"))
            hh, mm = map(int, parsed_hhmm.split(":"))
            depart_dt = tz.localize(datetime(y, mo, d, hh, mm))

            # Check blackout and min-advance again
            try:
                blackout_raw = settings.BLACKOUT_DATES or ""
                blackout_set = {s.strip() for s in blackout_raw.split(',') if s.strip()}
            except Exception:
                blackout_set = set()
            if depart_dt.strftime("%Y-%m-%d") in blackout_set:
                return msg("Selected date is unavailable. Please choose another date.")
            min_delta = timedelta(hours=getattr(settings, 'MIN_ADVANCE_HOURS', 12))
            if depart_dt < now + min_delta:
                return msg(f"Please choose a time at least {int(min_delta.total_seconds()//3600)} hours from now.")

            session.update({"travel_dt_iso": depart_dt.isoformat(), "step": "flights"})
            try:
                set_session(from_number, session)
            except Exception:
                pass
            flights = mock_search(session["source_iata"], session["dest_iata"], depart_dt)
            session["presented_flights"] = flights
            try:
                set_session(from_number, session)
            except Exception:
                pass
            lines = []
            for idx, f in enumerate(flights, start=1):
                dep = f['depart'][11:16]
                arr = f['arrive'][11:16]
                lines.append(f"{idx}) {f['flight_no']} {dep}-{arr}, {f['duration_min']}m, INR {f['price']}")
            lines.append("Reply with 1, 2, or 3 to select a flight.")
            return msg("\n".join(lines))

        if step == "flights":
            print("body7", body)
            idx = None
            try:
                idx = int(body)
            except Exception:
                return msg("Please reply with 1, 2, or 3 to pick a flight.")
            flights = session.get("presented_flights", [])
            if not (1 <= idx <= len(flights)):
                return msg("Invalid option. Reply with 1, 2, or 3.")
            selected = flights[idx - 1]
            session.update({"selected_flight_id": selected["id"], "step": "passengers_count"})
            try:
                set_session(from_number, session)
            except Exception:
                pass
            return msg("How many passengers? Reply with a number 1-4")

        if step == "passengers_count":
            try:
                n = int(body)
            except Exception:
                return msg("Please reply with a number 1-4 for passengers.")
            if not (1 <= n <= 4):
                return msg("Please reply with a number between 1 and 4.")
            session.update({"passengers_total": n, "passenger_index": 1, "passengers": [], "step": "details"})
            try:
                set_session(from_number, session)
            except Exception:
                pass
            return msg("Passenger 1 - enter full name and email (e.g., John Doe, john@example.com)")

        if step == "details":
            # Expect name and optional email, e.g., "John Doe, john@example.com" or just "John Doe"
            text = body.strip()
            name = text
            email = None
            # If comma separated, split into name and email
            if "," in text:
                parts = [p.strip() for p in text.split(",", 1)]
                name = parts[0] or name
                email = parts[1] if len(parts) > 1 else None
            # If email present without comma
            if not email:
                m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
                if m:
                    email = m.group(0)
                    name = text.replace(email, "").replace(",", " ").strip()
            email_pattern = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
            if not name:
                return msg("Please provide passenger name, e.g., John Doe, john@example.com")
            if not email or not re.fullmatch(email_pattern, email):
                return msg("Please include a valid email as well (e.g., John Doe, john@example.com)")
            # Append passenger to list and continue or move to confirm
            pax_list = session.get("passengers", [])
            pax_list.append({"name": name, "email": email})
            session["passengers"] = pax_list
            # Also set a primary passenger name for compatibility
            session["passenger_name"] = session.get("passenger_name") or name
            total = int(session.get("passengers_total", 1))
            idx = int(session.get("passenger_index", 1))
            if idx < total:
                session["passenger_index"] = idx + 1
                session["step"] = "details"
                try:
                    user.email = email or user.email
                    db.add(user)
                    db.commit()
                    set_session(from_number, session)
                except Exception:
                    pass
                return msg(f"Passenger {idx+1} - enter full name and email (e.g., John Doe, john@example.com)")
            # Move to seat selection and then confirm
            session["step"] = "seats"
            try:
                user.email = email or user.email
                db.add(user)
                db.commit()
                set_session(from_number, session)
            except Exception:
                pass
            return msg("Seat selection: reply 'auto' or provide seats separated by space (e.g., 12A 12B). Rows 5-30, seats A-F.")

        if step == "seats":
            # Parse seats or auto-assign
            total = int(session.get("passengers_total", 1))
            tokens = body.replace(",", " ").replace(";"," ").split()
            valid = []
            if body.strip().lower() != "auto":
                for t in tokens:
                    t = t.upper()
                    if re.fullmatch(r"(\d{1,2})([A-F])", t):
                        row = int(re.match(r"(\d{1,2})", t).group(1))
                        if 5 <= row <= 30:
                            valid.append(t)
                # Deduplicate
                valid = list(dict.fromkeys(valid))
            # Fill remaining with auto
            while len(valid) < total:
                # simple auto seat generation avoiding duplicates
                candidate = f"{min(30, max(5, 5 + len(valid)))}{['A','B','C','D','E','F'][len(valid)%6]}"
                if candidate not in valid:
                    valid.append(candidate)
            session["assigned_seats"] = valid[:total]
            session["step"] = "confirm"
            try:
                set_session(from_number, session)
            except Exception:
                pass
            seats_str = " ".join(session["assigned_seats"])
            return msg(f"Seats set: {seats_str}. Reply 'confirm' to generate your ticket PDF, or 'Restart' to start over.")

        if step == "confirm":
            # Wait for explicit confirmation to issue the ticket
            if body.strip().lower() != "confirm":
                return msg("Please reply 'confirm' to generate your ticket PDF, or 'Restart' to start over.")
            flights = session.get("presented_flights", [])
            selected_id = session.get("selected_flight_id")
            selected = next((f for f in flights if f.get("id") == selected_id), None)
            if not selected:
                # Safety: go back to flight selection
                session["step"] = "flights"
                try:
                    set_session(from_number, session)
                except Exception:
                    pass
                return msg("Session expired. Please pick a flight again: reply 'Restart' to start over.")

            # Generate a simple ticket PDF and send via WhatsApp as media
            base_url = get_public_base_url()
            ticket_info = {
                "name": session.get("passenger_name") or "WhatsApp User",
                "phone": from_number,
                "source": session.get("source_iata"),
                "dest": session.get("dest_iata"),
                "depart_at": session.get("travel_dt_iso"),
                "flight": selected,
            }
            try:
                pax_list = session.get("passengers") or ([{"name": session.get("passenger_name") or "WhatsApp User", "email": session.get("passenger_email")}] )
                ticket_info["passengers"] = pax_list
                ticket_id, _path, pnr, seats, gate = generate_ticket_pdf(ticket_info, base_url=base_url)
                seats_str = ", ".join(seats) if isinstance(seats, list) else str(seats)
                pdf_url = f"{base_url}/tickets/{ticket_id}.pdf"
                # Proactively send the PDF to the user
                try:
                    send_whatsapp_text(from_number, f"Your flight ticket is ready. PNR: {pnr} • Seats: {seats_str} • Gate: {gate}\nDownload: {pdf_url}", media_url=pdf_url)
                except Exception:
                    # Even if sending fails, still respond with link
                    pass
                # Clear session and confirm via TwiML
                try:
                    clear_session(from_number)
                except Exception:
                    pass
                return msg(f"Ticket generated ✅ (PNR: {pnr}, Seats: {seats_str}, Gate: {gate})\\nDownload: {pdf_url}")
            except Exception:
                return msg("Could not generate ticket right now. Please try again in a moment or reply 'Restart'.")


        # Default fallback
        print("body9", body)
        return msg("I didn't get that. Reply 'Restart' to start over.")
    finally:
        db.close()
