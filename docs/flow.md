# WhatsApp Flight Booking – Flow Diagrams

Below are Mermaid diagrams describing the major flows implemented in this project.

## 1) Conversation state machine (WhatsApp flow)

```mermaid
flowchart TD
  Inbound["/whatsapp/webhook inbound message"]
  Msg{Message text}

  Inbound --> Msg

  %% Quick commands
  Msg -->|"pnr <CODE>"| PNR["Lookup booking by PNR\n→ Return ticket link or 404"]
  Msg -->|ticket| Last["Find latest booking for user\n→ Return ticket link or fallback message"]
  Msg -->|restart / start| Reset["clear_session(from_number)"] --> Source

  %% FSM dispatch
  Msg -->|other| Step{session.step}

  Step -->|source| Source["Ask/parse source city (1..4 or free text)\n→ to_iata"]
  Source -->|valid| Dest
  Source -->|invalid| Source

  Step -->|destination| Dest["Ask/parse destination city (1..4 or free text)\n→ to_iata; must differ from source"]
  Dest -->|valid| Date
  Dest -->|invalid| Dest

  Step -->|date| Date["Show 3-month calendar\nAccept date with optional time\nValidate: blackout + min advance"]
  Date -->|valid with time| Flights
  Date -->|date only| Time
  Date -->|invalid| Date

  Step -->|time| Time["Offer preset times (06,09,12,15,18,21) that satisfy min-advance\nOr parse HH:MM / 9am"]
  Time -->|valid| Flights
  Time -->|invalid| Time

  Step -->|flights| Flights["Show 3 flight options (mock_search)\nReply 1..3"]
  Flights -->|1..3| PaxCount
  Flights -->|invalid| Flights

  Step -->|passengers_count| PaxCount["Ask number of passengers 1..4"]
  PaxCount -->|valid| PaxDetails
  PaxCount -->|invalid| PaxCount

  Step -->|details| PaxDetails["Loop N times: collect 'Full Name, email' (email required)\nUpdate user.email if present"]
  PaxDetails -->|done| Seats
  PaxDetails -->|invalid| PaxDetails

  Step -->|seats| Seats["Seat selection: 'auto' or list (e.g., 12A 12B)\nValidate rows 5–30, A–F; fill missing with auto"]
  Seats -->|valid| Confirm
  Seats -->|invalid| Seats

  Step -->|confirm| Confirm["User replies 'confirm' (also accepted from legacy 'payment' step)"]
  Confirm --> Issue

  Issue["Issue ticket:\n• generate_ticket_pdf → PNR, seats[], gate\n• Save PDF in /tickets\n• Twilio: send media message\n• Persist Booking.flight_meta (pnr, seats, gate, ticket_id/url, passengers, depart_at)\n• clear_session"] --> Done["Reply TwiML with link + PNR/Seats/Gate"]
```

## 2) Ticket issuance sequence

```mermaid
sequenceDiagram
  participant W as WhatsApp (via Twilio)
  participant API as FastAPI /whatsapp/webhook
  participant PDF as ticket_pdf.generate_ticket_pdf
  participant FS as Static /tickets
  participant T as Twilio REST API

  W->>API: confirm
  API->>PDF: generate_ticket_pdf(info, base_url)
  PDF-->>API: ticket_id, pnr, seats[], gate
  API->>T: messages.create(media_url=BASE_URL/tickets/{ticket_id}.pdf)
  API->>FS: (PDF saved to ./tickets/{ticket_id}.pdf)
  API-->>W: TwiML response with link and PNR/Seats/Gate
```

## 3) PNR lookup and ticket retrieval

```mermaid
flowchart LR
  A[User sends 'pnr ABC123'] --> B[API scans Booking.flight_meta for PNR]
  B -->|found| C[Return ticket_url]
  B -->|missing| D[Reply 'PNR not found']

  E[GET /booking/{pnr}] --> F[Return JSON: pnr, seats[], gate, ticket_url, depart_at]
  G[GET /tickets/by-pnr/{pnr}.pdf] --> H[Serve ./tickets/{ticket_id}.pdf]
```

## Notes
- Session storage: in-process memory fallback is forced (Redis bypassed) — state is lost on server restart.
- Branding: FROM_NAME, BRAND_PRIMARY, BRAND_LOGO_PATH influence ticket header.
- Date/time rules: MIN_ADVANCE_HOURS and BLACKOUT_DATES from environment.
- Persistence: Bookings saved with flight_meta including pnr, seats, gate, passengers, and departure timestamps.

