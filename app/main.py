from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app.core.settings import settings
from app.core.db import init_db
from app.routers.whatsapp import router as whatsapp_router
from app.routers.stripe_webhook import router as stripe_router
from app.routers.booking import router as booking_router

app = FastAPI(title="WhatsApp Flight Booking")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    init_db()
    # Ensure tickets directory exists for serving generated PDFs
    os.makedirs("tickets", exist_ok=True)

# Ensure the tickets directory exists at import time to satisfy StaticFiles
os.makedirs("tickets", exist_ok=True)
# Serve generated ticket PDFs
app.mount("/tickets", StaticFiles(directory="tickets", check_dir=False), name="tickets")

app.include_router(whatsapp_router, prefix="/whatsapp", tags=["whatsapp"]) 
app.include_router(stripe_router, prefix="/stripe", tags=["stripe"]) 
app.include_router(booking_router, tags=["booking"]) 

@app.get("/")
@app.post("/")
def root():
    print("Hello World")
    return {
        "status": "ok",
        "message": "WhatsApp Flight Booking API",
        "endpoints": ["/health", "/whatsapp/webhook", "/docs"],
    }

@app.get("/health")
def health():
    return {"status": "ok", "env": settings.ENV}
