import os
from pydantic import BaseModel

class Settings(BaseModel):
    APP_NAME: str = "Bollinger Bands Options Trading Dashboard PRO"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api"
    HOST: str = "0.0.0.0"
    PORT: int = 8001
    DHAN_API_BASE: str = "https://api.dhan.co/v2"
    RATE_LIMIT_RPS: int = 5
    SCAN_INTERVAL_SECONDS: float = 8.0
    DATA_DIR: str = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
    DB_PATH: str = os.path.join(DATA_DIR, "trades.db")

settings = Settings()
