# WhatsApp Flight Booking (FastAPI)

A WhatsApp-based flight booking flow with preset choices + "Other", payment via Stripe, and email confirmation via SendGrid.

## Stack
- FastAPI, SQLAlchemy, Redis, Postgres
- Twilio WhatsApp, Stripe, SendGrid
- Deployed on Railway

## Setup
1. Create and fill `.env` from `.env.example`.
2. Create virtualenv and install requirements:
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Run locally:
   ```bash
   uvicorn app.main:app --reload
   ```

## Webhooks
- Twilio: POST {BASE_URL}/whatsapp/webhook
- Stripe: POST {BASE_URL}/stripe/webhook

## Railway
- Add services: Web, Postgres, Redis.
- Set env vars from `.env.example`.
- Use `Procfile` to run server.
