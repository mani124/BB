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
    # BB_DATA_DIR / BB_DB_PATH let tests (and other installs) keep their data away from the real journal.
    DATA_DIR: str = os.getenv(
        "BB_DATA_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data"),
    )
    DB_PATH: str = os.getenv("BB_DB_PATH", os.path.join(DATA_DIR, "trades.db"))
    # Exchange-session guard (all times IST, HH:MM)
    ENTRY_CUTOFF_TIME: str = os.getenv("ENTRY_CUTOFF_TIME", "15:15")
    EOD_SQUARE_OFF_TIME: str = os.getenv("EOD_SQUARE_OFF_TIME", "15:20")
    # Setup 1 absolute squeeze threshold (BandWidth %). 5.0 is the legacy value, which is nearly
    # always true on 5m bars; lower it (e.g. 1.5) only after comparing signal counts on recorded data.
    SQUEEZE_ABS_BW_PCT: float = float(os.getenv("SQUEEZE_ABS_BW_PCT", "5.0"))
    # Refuse entries whose option SL/targets rely on an assumed (non-chain) delta.
    REQUIRE_REAL_DELTA: bool = os.getenv("REQUIRE_REAL_DELTA", "0") == "1"
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
    MAX_OPEN_NOTIONAL: float = float(os.getenv("MAX_OPEN_NOTIONAL", "2000000"))
    # The old public default. It is never accepted: when DASHBOARD_CAPABILITY is unset (or set to this),
    # a random key is generated once and kept in <DATA_DIR>/dashboard_key (see resolve_dashboard_capability).
    DEFAULT_DASHBOARD_CAPABILITY: str = "bb-options-local-capability"
    DASHBOARD_CAPABILITY: str = os.getenv("DASHBOARD_CAPABILITY", "")
    # Set COOKIE_SECURE=1 whenever the dashboard is served over HTTPS / beyond localhost.
    COOKIE_SECURE: bool = os.getenv("COOKIE_SECURE", "0") == "1"

settings = Settings()


def resolve_dashboard_capability(cfg: Settings) -> str:
    """Return a private dashboard key: the env value if it is set and not the old public
    default, else the key stored in <DATA_DIR>/dashboard_key, else a newly generated one
    (written to that file with 0600 permissions so it survives restarts and deploys)."""
    import logging
    import secrets

    env_key = (cfg.DASHBOARD_CAPABILITY or "").strip()
    if env_key and env_key != cfg.DEFAULT_DASHBOARD_CAPABILITY:
        return env_key
    log = logging.getLogger(__name__)
    if env_key == cfg.DEFAULT_DASHBOARD_CAPABILITY:
        log.warning("SECURITY: DASHBOARD_CAPABILITY is the old public default; ignoring it and using the key file.")
    key_path = os.path.join(cfg.DATA_DIR, "dashboard_key")
    try:
        with open(key_path) as f:
            stored = f.read().strip()
        if stored and stored != cfg.DEFAULT_DASHBOARD_CAPABILITY:
            return stored
    except FileNotFoundError:
        pass
    key = secrets.token_urlsafe(32)
    os.makedirs(cfg.DATA_DIR, exist_ok=True)
    fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(key + "\n")
    log.warning("SECURITY: generated a new dashboard key in %s; enter it in the dashboard to sign in.", key_path)
    return key


settings.DASHBOARD_CAPABILITY = resolve_dashboard_capability(settings)
