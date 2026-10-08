import asyncio
import logging
from typing import Optional
import httpx
import pandas as pd
from app.core.config import settings

logger = logging.getLogger(__name__)

class DhanClient:
    """Async HTTP client for Dhan HQ APIs with strict rate-limiting and zero-token storage."""

    def __init__(self, rps_limit: int = settings.RATE_LIMIT_RPS):
        self._semaphore = asyncio.Semaphore(rps_limit)
        self._base_url = settings.DHAN_API_BASE
        self._client: Optional[httpx.AsyncClient] = None

    async def get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(10.0, connect=5.0),
                headers={"Accept": "application/json"}
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def verify_credentials(self, client_id: str, access_token: str) -> dict:
        """Verify 24h Dhan access token by querying trader profile/fund limits."""
        headers = {
            "client-id": client_id,
            "access-token": access_token
        }
        client = await self.get_client()
        async with self._semaphore:
            resp = await client.get("/user/profile", headers=headers)
            if resp.status_code == 200:
                return {"valid": True, "data": resp.json()}
            elif resp.status_code == 401:
                return {"valid": False, "error": "Invalid or expired Dhan Access Token"}
            else:
                # Some accounts respond on fund-limit endpoint
                resp2 = await client.get("/fund-limit", headers=headers)
                if resp2.status_code == 200:
                    return {"valid": True, "data": resp2.json()}
                return {"valid": False, "error": f"Dhan API returned HTTP {resp.status_code}"}

    async def fetch_intraday_candles(
        self,
        client_id: str,
        access_token: str,
        security_id: str,
        exchange_segment: str,
        instrument_type: str = "EQUITY",
        interval: int = 5
    ) -> pd.DataFrame:
        """
        Fetch intraday historical candles from Dhan HQ API:
        POST /v2/charts/intraday
        Body: {"securityId": str, "exchangeSegment": str, "instrument": str, "interval": int}
        """
        headers = {
            "client-id": client_id,
            "access-token": access_token,
            "Content-Type": "application/json"
        }
        payload = {
            "securityId": str(security_id),
            "exchangeSegment": exchange_segment,
            "instrument": instrument_type,
            "interval": interval
        }

        client = await self.get_client()
        async with self._semaphore:
            await asyncio.sleep(0.18)  # ~5 req/sec smooth spacing
            resp = await client.post("/charts/intraday", headers=headers, json=payload)
            if resp.status_code != 200:
                logger.warning(f"Dhan intraday chart error: HTTP {resp.status_code} for sec_id={security_id}")
                return pd.DataFrame()

            data = resp.json()
            # Dhan response format:
            # {"open": [...], "high": [...], "low": [...], "close": [...], "volume": [...], "start_Time": [...]}
            if not isinstance(data, dict) or "close" not in data or not data["close"]:
                return pd.DataFrame()

            timestamps = data.get("start_Time") or data.get("timestamp") or []
            return pd.DataFrame({
                "timestamp": pd.to_datetime(timestamps, unit="s", errors="coerce"),
                "open": data["open"],
                "high": data["high"],
                "low": data["low"],
                "close": data["close"],
                "volume": data["volume"]
            })
