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
    # Setup 1 absolute squeeze threshold (BandWidth %). 5.0 is the legacy value, which is nearly
    # always true on 5m bars; lower it (e.g. 1.5) only after comparing signal counts on recorded data.
    SQUEEZE_ABS_BW_PCT: float = float(os.getenv("SQUEEZE_ABS_BW_PCT", "5.0"))
    EXPIRY_DAY_CUTOFF_TIME: str = os.getenv("EXPIRY_DAY_CUTOFF_TIME", "14:30")
    REENTRY_COOLDOWN_SECONDS: int = int(os.getenv("REENTRY_COOLDOWN_SECONDS", "300"))
    # Entry quality guards (live mode)
    MAX_QUOTE_AGE_SECONDS: float = float(os.getenv("MAX_QUOTE_AGE_SECONDS", "30"))
    MAX_ENTRY_SPREAD_PCT: float = float(os.getenv("MAX_ENTRY_SPREAD_PCT", "25"))
    # Gap-exit labelling: fill this far (in %) beyond the intended exit level counts as a gap
    GAP_EXIT_PCT: float = float(os.getenv("GAP_EXIT_PCT", "5"))
    # Exposure caps (0 disables a cap)
    MAX_OPEN_POSITIONS: int = int(os.getenv("MAX_OPEN_POSITIONS", "8"))
    MAX_ENTRIES_PER_SYMBOL_PER_DAY: int = int(os.getenv("MAX_ENTRIES_PER_SYMBOL_PER_DAY", "3"))
    MAX_OPEN_NOTIONAL: float = float(os.getenv("MAX_OPEN_NOTIONAL", "1000000"))
    DASHBOARD_CAPABILITY: str = os.getenv("DASHBOARD_CAPABILITY", "bb-options-local-capability")

settings = Settings()
