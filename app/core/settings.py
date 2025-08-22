from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    ENV: str = "development"
    BASE_URL: str = "http://localhost:8000"
    DEFAULT_TIMEZONE: str = "Asia/Kolkata"

    # Date/time controls
    MIN_ADVANCE_HOURS: int = 12  # minimum hours from now for departures
    BLACKOUT_DATES: str | None = None  # comma-separated YYYY-MM-DD list

    TWILIO_ACCOUNT_SID: str
    TWILIO_AUTH_TOKEN: str
    TWILIO_WHATSAPP_NUMBER: str

    STRIPE_SECRET_KEY: str
    STRIPE_WEBHOOK_SECRET: str

    SENDGRID_API_KEY: str
    FROM_EMAIL: str
    FROM_NAME: str = "Flight Booking"

    DATABASE_URL: str
    REDIS_URL: str

settings = Settings()
