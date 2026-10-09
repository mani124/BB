import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
import httpx
import pandas as pd
from app.core.config import settings

logger = logging.getLogger(__name__)

class DhanClient:
    """Async HTTP client for Dhan HQ APIs with strict rate-limiting and zero-token storage."""

    def __init__(self, rps_limit: int = settings.RATE_LIMIT_RPS, min_spacing: float = 0.18):
        self._semaphore = asyncio.Semaphore(rps_limit)
        self._pace_lock = asyncio.Lock()
        self._min_spacing = min_spacing
        self._last_request_time: float = 0.0
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
            self._client = None

    async def _throttle(self):
        """Enforce smooth inter-request spacing (~0.18s) to prevent bursting and HTTP 429."""
        async with self._pace_lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            elapsed = now - self._last_request_time
            if elapsed < self._min_spacing:
                await asyncio.sleep(self._min_spacing - elapsed)
            self._last_request_time = loop.time()

    async def verify_credentials(self, client_id: str, access_token: str) -> dict:
        """
        Verify 24h Dhan access token by querying trader profile.
        Falls back to /fundlimit if /profile returns a non-200 non-auth status.
        """
        headers = {
            "client-id": client_id,
            "access-token": access_token,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        client = await self.get_client()
        try:
            async with self._semaphore:
                await self._throttle()
                resp = await client.get("/profile", headers=headers)
                if resp.status_code == 200:
                    return {"valid": True, "data": resp.json()}
                elif resp.status_code in [401, 403]:
                    return {"valid": False, "error": "Invalid or expired Dhan Access Token"}
                
                # Fallback to fundlimit endpoint if /profile route is unavailable
                logger.info(f"Dhan /profile returned HTTP {resp.status_code}, falling back to /fundlimit")
                await self._throttle()
                resp2 = await client.get("/fundlimit", headers=headers)
                if resp2.status_code == 200:
                    return {"valid": True, "data": resp2.json()}
                elif resp2.status_code in [401, 403]:
                    return {"valid": False, "error": "Invalid or expired Dhan Access Token"}
                logger.warning(f"Dhan /fundlimit fallback returned HTTP {resp2.status_code}")
                return {"valid": False, "error": f"Dhan API returned HTTP {resp2.status_code}"}
        except httpx.RequestError as exc:
            logger.error(f"Network error verifying Dhan credentials: {exc}")
            return {"valid": False, "error": f"Network error connecting to Dhan API: {str(exc)}"}
        except Exception as exc:
            logger.error(f"Unexpected error verifying Dhan credentials: {exc}")
            return {"valid": False, "error": f"Unexpected verification error: {str(exc)}"}

    async def fetch_marketfeed_quotes(
        self,
        client_id: str,
        access_token: str,
        securities: dict[str, list[int]]
    ) -> dict:
        """
        Fetch full real-time market quotes (LTP, OHLC, volume, net_change) for multiple securities
        across segments in a single API call via POST /marketfeed/quote.
        """
        headers = {
            "client-id": client_id,
            "access-token": access_token,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        try:
            client = await self.get_client()
            async with self._semaphore:
                await self._throttle()
                resp = await client.post("/marketfeed/quote", headers=headers, json=securities)
                if resp.status_code == 429:
                    logger.warning("Marketfeed quote hit 429 rate limit. Backing off 2.5s and retrying...")
                    await asyncio.sleep(2.5)
                    await self._throttle()
                    resp = await client.post("/marketfeed/quote", headers=headers, json=securities)

                if resp.status_code == 200:
                    data = resp.json()
                    res_data = data.get("data", {})
                    if isinstance(res_data, dict) and "data" in res_data and isinstance(res_data["data"], dict):
                        res_data = res_data["data"]
                    return res_data
                logger.warning(f"Marketfeed quote returned HTTP {resp.status_code}: {resp.text[:200]}")
                return {}
        except Exception as e:
            logger.warning(f"Exception fetching marketfeed quotes: {e}")
            return {}

    async def fetch_intraday_candles(
        self,
        client_id: str,
        access_token: str,
        security_id: str,
        exchange_segment: str,
        instrument_type: str = "EQUITY",
        interval: int = 5,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Fetch intraday historical candles from Dhan HQ API:
        POST /charts/intraday
        Body: {"securityId": str, "exchangeSegment": str, "instrument": str, "interval": int, "fromDate": str, "toDate": str}
        """
        now = datetime.now()
        # Dhan v2 /charts/intraday requires datetime format: 'YYYY-MM-DD HH:MM:SS'
        if not to_date:
            to_date = now.strftime("%Y-%m-%d %H:%M:%S")
        elif len(to_date) == 10:
            to_date = f"{to_date} 15:30:00"

        if not from_date:
            # Default to rolling 5 days starting from market open
            from_date = (now - timedelta(days=5)).strftime("%Y-%m-%d 09:15:00")
        elif len(from_date) == 10:
            from_date = f"{from_date} 09:15:00"

        headers = {
            "client-id": client_id,
            "access-token": access_token,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        # Primary payload according to official Dhan v2 documentation
        primary_payload = {
            "securityId": str(security_id),
            "exchangeSegment": exchange_segment,
            "instrument": instrument_type,
            "interval": str(interval),
            "oi": False,
            "fromDate": from_date,
            "toDate": to_date
        }

        candidate_payloads = [
            primary_payload,
            # Permutation 2: integer interval
            {**primary_payload, "interval": int(interval)},
            # Permutation 3: with dhanClientId as per python SDK
            {**primary_payload, "dhanClientId": str(client_id), "interval": int(interval)},
            # Permutation 4: date only (YYYY-MM-DD)
            {**primary_payload, "fromDate": from_date.split()[0], "toDate": to_date.split()[0], "interval": int(interval)}
        ]

        data = None
        try:
            client = await self.get_client()
            async with self._semaphore:
                await self._throttle()
                
                for idx, payload in enumerate(candidate_payloads):
                    resp = await client.post("/charts/intraday", headers=headers, json=payload)
                    
                    # Handle rate limiting with exponential backoff retry
                    if resp.status_code == 429:
                        logger.warning(f"Dhan rate limit (429) hit for sec_id={security_id}. Retrying after backoff...")
                        await asyncio.sleep(1.0)
                        await self._throttle()
                        resp = await client.post("/charts/intraday", headers=headers, json=payload)

                    if resp.status_code == 200:
                        if idx > 0:
                            logger.info(f"Dhan intraday success with candidate payload {idx} for sec_id={security_id}")
                        data = resp.json()
                        break
                    elif resp.status_code == 400:
                        logger.warning(f"Dhan intraday payload candidate {idx} returned HTTP 400: {resp.text}")
                        continue
                    else:
                        logger.warning(f"Dhan intraday chart error: HTTP {resp.status_code} for sec_id={security_id}: {resp.text}")
                        break

                if data is None:
                    return pd.DataFrame()
        except Exception as e:
            logger.warning(f"Exception fetching intraday candles for sec_id={security_id}: {e}")
            return pd.DataFrame()

        if not isinstance(data, dict):
            return pd.DataFrame()

        # Handle potential nested 'data' key in Dhan API responses
        candles = data.get("data") if isinstance(data.get("data"), dict) else data

        if not isinstance(candles, dict) or "close" not in candles or not candles["close"]:
            return pd.DataFrame()

        try:
            timestamps = (
                candles.get("start_Time")
                or candles.get("timestamp")
                or candles.get("startTime")
                or candles.get("time")
                or []
            )
            parsed_ts = self._parse_dhan_timestamps(timestamps)

            volume = candles.get("volume") or [0] * len(candles["close"])
            return pd.DataFrame({
                "timestamp": parsed_ts,
                "open": candles["open"],
                "high": candles["high"],
                "low": candles["low"],
                "close": candles["close"],
                "volume": volume
            })
        except Exception as e:
            logger.warning(f"Error assembling DataFrame from Dhan candles: {e}")
            return pd.DataFrame()

    def _parse_dhan_timestamps(self, timestamps: list) -> pd.DatetimeIndex:
        """
        Convert Dhan timestamps (UTC epoch seconds or strings) to Indian Standard Time (IST) naive datetimes.
        """
        if not timestamps or len(timestamps) == 0:
            return pd.DatetimeIndex([])

        first = timestamps[0]
        is_epoch = False
        try:
            val = float(first)
            is_epoch = True
        except (ValueError, TypeError):
            is_epoch = False

        if is_epoch:
            # Dhan epoch timestamps:
            # Usually epoch seconds (10 digits, e.g. ~1.7e9). Milliseconds if > 1e11.
            val = float(first)
            unit = "ms" if val > 1e11 else "s"
            numeric_ts = pd.to_numeric(timestamps, errors="coerce")
            dt_idx = pd.to_datetime(numeric_ts, unit=unit, utc=True, errors="coerce")
            return dt_idx.tz_convert("Asia/Kolkata").tz_localize(None)
        else:
            dt_idx = pd.to_datetime(timestamps, errors="coerce")
            if dt_idx.tz is not None:
                return dt_idx.tz_convert("Asia/Kolkata").tz_localize(None)
            return dt_idx
