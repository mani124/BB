import os
from pydantic import BaseModel

class Settings(BaseModel):
    APP_NAME: str = "Bollinger Bands Options Trading Dashboard PRO"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api"
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = 8001
    DHAN_API_BASE: str = "https://api.dhan.co/v2"
    DHAN_AUTH_BASE: str = os.getenv("DHAN_AUTH_BASE", "https://auth.dhan.co")
    DHAN_LOGIN_URL: str = os.getenv("DHAN_LOGIN_URL", "https://auth.dhan.co/login/consent")
    DHAN_TOKEN_URL: str = os.getenv("DHAN_TOKEN_URL", "https://auth.dhan.co/oauth/token")
    DHAN_GENERATE_CONSENT_URL: str = os.getenv("DHAN_GENERATE_CONSENT_URL", "https://auth.dhan.co/app/generate-consent")
    DHAN_CONSENT_LOGIN_URL: str = os.getenv("DHAN_CONSENT_LOGIN_URL", "https://auth.dhan.co/login/consentApp-login")
    DHAN_CONSUME_CONSENT_URL: str = os.getenv("DHAN_CONSUME_CONSENT_URL", "https://auth.dhan.co/app/consumeApp-consent")
    RATE_LIMIT_RPS: int = 5
    SCAN_INTERVAL_SECONDS: float = 3.0
    DATA_DIR: str = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
    DB_PATH: str = os.path.join(DATA_DIR, "trades.db")
    # Exchange-session guard (all times IST, HH:MM)
    ENTRY_CUTOFF_TIME: str = os.getenv("ENTRY_CUTOFF_TIME", "15:15")
    EOD_SQUARE_OFF_TIME: str = os.getenv("EOD_SQUARE_OFF_TIME", "15:20")
    REENTRY_COOLDOWN_SECONDS: int = int(os.getenv("REENTRY_COOLDOWN_SECONDS", "300"))
    DASHBOARD_CAPABILITY: str = os.getenv("DASHBOARD_CAPABILITY", "bb-options-local-capability")

settings = Settings()
