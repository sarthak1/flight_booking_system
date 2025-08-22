from fastapi import APIRouter, Request, HTTPException
import stripe
from app.core.settings import settings
from app.core.redis import get_session, clear_session
from app.core.db import SessionLocal, User, Booking
from app.services.emailer import send_confirmation

router = APIRouter()

stripe.api_key = settings.STRIPE_SECRET_KEY


@router.post("/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    try:
        event = stripe.Webhook.construct_event(
            payload=payload, sig_header=sig_header, secret=settings.STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if event['type'] == 'checkout.session.completed':
        session_obj = event['data']['object']
        meta = session_obj.get('metadata', {})
        from_number = meta.get('from')
        db = SessionLocal()
        try:
            if from_number:
                session = get_session(from_number)
                user = db.query(User).filter(User.whatsapp_number == from_number).first()
                if user and session:
                    # Create booking record
                    booking = Booking(
                        user_id=user.id,
                        source_iata=session.get('source_iata'),
                        dest_iata=session.get('dest_iata'),
                        depart_at=session.get('travel_dt_iso'),
                        flight_meta={"selected": session.get('selected_flight_id')},
                        price=session.get('presented_flights', [{}])[0].get('price', 0),
                        currency='INR',
                        payment_status='paid',
                        stripe_session_id=session_obj.get('id'),
                    )
                    db.add(booking)
                    db.commit()
                    # Send email if available
                    if user.email:
                        html = f"<p>Your flight {booking.source_iata} -> {booking.dest_iata} on {booking.depart_at} is confirmed.</p>"
                        try:
                            send_confirmation(user.email, "Flight Booking Confirmed", html)
                        except Exception:
                            pass
                    clear_session(from_number)
        finally:
            db.close()

    return {"received": True}
