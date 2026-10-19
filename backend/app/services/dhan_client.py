import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
import httpx
import pandas as pd
from app.core.config import settings
from app.services import market_hours

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
        # Shared 429 backoff: one cooldown for every endpoint, never a sleep inside a held request slot.
        self._cooldown_until: float = 0.0
        self._cooldown_step: int = 0
        self._last_429_at: float = 0.0
        self._rate_limit_counts: dict[str, int] = {}
        # Option chains are shared by every caller (scanner, earnings engine): one fetch per key per TTL.
        self._chain_cache: dict[tuple, tuple[float, dict, bool]] = {}  # key -> (monotonic ts, chain, fetch ok)
        self._chain_inflight: dict[tuple, asyncio.Future] = {}

    # ------------------------------------------------------------------ 429 handling
    def _note_rate_limited(self, endpoint: str) -> float:
        """Count a 429 and start (or lengthen) the shared cooldown. Returns the cooldown length in seconds."""
        loop_now = asyncio.get_running_loop().time()
        day = market_hours.now_ist().date().isoformat()
        self._rate_limit_counts[day] = self._rate_limit_counts.get(day, 0) + 1
        for old in sorted(self._rate_limit_counts)[:-7]:
            self._rate_limit_counts.pop(old, None)
        # Consecutive 429s (no success in between) double the wait: 2s, 4s, 8s ... capped at 30s.
        self._cooldown_step = min(self._cooldown_step + 1, 5)
        length = min(self.COOLDOWN_MAX_S, self.COOLDOWN_BASE_S * (2 ** (self._cooldown_step - 1)))
        self._cooldown_until = max(self._cooldown_until, loop_now + length)
        self._last_429_at = loop_now
        logger.warning(f"Dhan 429 on {endpoint}: pausing all Dhan REST calls for {length:.0f}s")
        return length

    def _note_ok(self) -> None:
        if self._cooldown_step and asyncio.get_running_loop().time() >= self._cooldown_until:
            self._cooldown_step = 0

    def cooldown_remaining(self) -> float:
        try:
            return max(0.0, self._cooldown_until - asyncio.get_running_loop().time())
        except RuntimeError:
            return 0.0

    def rate_limit_status(self) -> dict:
        """Today's 429 count (IST day), recent days, and whether the client is cooling down right now."""
        day = market_hours.now_ist().date().isoformat()
        return {"today": self._rate_limit_counts.get(day, 0), "by_day": dict(sorted(self._rate_limit_counts.items())),
                "cooldown_s": round(self.cooldown_remaining(), 1)}

    COOLDOWN_BASE_S = 2.0
    COOLDOWN_MAX_S = 30.0
    CHAIN_TTL_S = 15.0
    CHAIN_FAIL_TTL_S = 20.0

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
        wait = self.cooldown_remaining()
        if wait > 0:
            await asyncio.sleep(wait)  # outside the pace lock: other callers are not blocked behind this sleep
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
        securities: dict[str, list[int]],
        batch_size: int = 1000
    ) -> dict:
        """
        Fetch full real-time market quotes (LTP, OHLC, volume, net_change) for multiple securities
        across segments in a single API call via POST /marketfeed/quote.
        Supports up to 1,000 instruments per request (Dhan official limit).
        """
        headers = {
            "client-id": client_id,
            "access-token": access_token,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        # Chunk requests so that no single call exceeds batch_size (Dhan limit 1,000)
        chunks: list[dict[str, list[int]]] = []
        current_chunk: dict[str, list[int]] = {}
        current_count = 0

        for seg, sec_ids in securities.items():
            for i in range(0, len(sec_ids), batch_size):
                batch = sec_ids[i:i + batch_size]
                if current_count + len(batch) <= batch_size:
                    current_chunk.setdefault(seg, []).extend(batch)
                    current_count += len(batch)
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                    current_chunk = {seg: list(batch)}
                    current_count = len(batch)

        if current_chunk:
            chunks.append(current_chunk)

        if not chunks:
            return {}

        merged_results: dict[str, dict] = {}
        try:
            client = await self.get_client()
            for idx, chunk in enumerate(chunks):
                if idx > 0:
                    # Dhan market quote endpoint allows 1 request per second
                    await asyncio.sleep(1.1)

                async with self._semaphore:
                    await self._throttle()
                    resp = await client.post("/marketfeed/quote", headers=headers, json=chunk)
                    if resp.status_code == 429:
                        self._note_rate_limited("marketfeed/quote")
                        await self._throttle()  # waits out the shared cooldown
                        resp = await client.post("/marketfeed/quote", headers=headers, json=chunk)
                        logger.info(f"Marketfeed retry status: {resp.status_code}")

                    if resp.status_code == 200:
                        data = resp.json()
                        res_data = data.get("data", {})
                        if isinstance(res_data, dict) and "data" in res_data and isinstance(res_data["data"], dict):
                            res_data = res_data["data"]
                        if isinstance(res_data, dict):
                            for seg, seg_quotes in res_data.items():
                                if isinstance(seg_quotes, dict):
                                    merged_results.setdefault(seg, {}).update(seg_quotes)
                    else:
                        logger.warning(f"Marketfeed quote returned HTTP {resp.status_code}: {resp.text[:200]}")
            return merged_results
        except Exception as e:
            logger.warning(f"Exception fetching marketfeed quotes: {e}")
            return merged_results

    async def fetch_expiry_list(
        self,
        client_id: str,
        access_token: str,
        underlying_scrip: int,
        underlying_seg: str
    ) -> list[str]:
        """
        Fetch available option contract expiry dates from Dhan:
        POST /optionchain/expirylist
        Body: {"UnderlyingScrip": int, "UnderlyingSeg": str}
        """
        headers = {
            "client-id": client_id,
            "access-token": access_token,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        payload = {
            "UnderlyingScrip": int(underlying_scrip),
            "UnderlyingSeg": underlying_seg
        }
        if self.cooldown_remaining() > 0:
            return []  # cooling down after a 429: the caller caches the miss instead of retrying
        try:
            client = await self.get_client()
            async with self._semaphore:
                await self._throttle()
                resp = await client.post("/optionchain/expirylist", headers=headers, json=payload)
                if resp.status_code == 429:
                    self._note_rate_limited("optionchain/expirylist")
                    return []

                if resp.status_code == 200:
                    self._note_ok()
                    data = resp.json()
                    expiries = data.get("data", [])
                    if isinstance(expiries, list):
                        return expiries
                logger.warning(f"Expirylist returned HTTP {resp.status_code}: {resp.text[:200]}")
                return []
        except Exception as e:
            logger.warning(f"Exception fetching expirylist: {e}")
            return []

    async def fetch_option_chain(
        self,
        client_id: str,
        access_token: str,
        underlying_scrip: int,
        underlying_seg: str,
        expiry: str
    ) -> dict:
        """
        Fetch full option chain with real quotes and Greeks from Dhan (POST /optionchain).

        Shared by every caller: a chain fetched in the last CHAIN_TTL_S seconds is returned from memory, a failed fetch
        (429, error, empty chain) is remembered for CHAIN_FAIL_TTL_S so callers do not hammer Dhan, and concurrent
        callers for the same chain wait on one request.
        """
        key = (int(underlying_scrip), underlying_seg, expiry)
        loop = asyncio.get_running_loop()
        hit = self._chain_cache.get(key)
        if hit:
            ts, oc, ok = hit
            if loop.time() - ts < (self.CHAIN_TTL_S if ok else self.CHAIN_FAIL_TTL_S):
                return oc
        pending = self._chain_inflight.get(key)
        if pending is not None:
            return await asyncio.shield(pending)
        fut: asyncio.Future = loop.create_future()
        self._chain_inflight[key] = fut
        oc: dict = {}
        try:
            if self.cooldown_remaining() > 0:
                return {}  # cooling down after a 429: do not cache, the cooldown itself is the memory
            oc = await self._request_option_chain(client_id, access_token, underlying_scrip, underlying_seg, expiry)
            self._chain_cache[key] = (loop.time(), oc, bool(oc))
            if len(self._chain_cache) > 400:
                for k in [k for k, v in self._chain_cache.items() if loop.time() - v[0] > self.CHAIN_FAIL_TTL_S * 3]:
                    self._chain_cache.pop(k, None)
            return oc
        finally:
            self._chain_inflight.pop(key, None)
            if not fut.done():
                fut.set_result(oc)

    async def _request_option_chain(self, client_id: str, access_token: str, underlying_scrip: int,
                                    underlying_seg: str, expiry: str) -> dict:
        headers = {
            "client-id": client_id,
            "access-token": access_token,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        payload = {
            "UnderlyingScrip": int(underlying_scrip),
            "UnderlyingSeg": underlying_seg,
            "Expiry": expiry
        }
        try:
            client = await self.get_client()
            async with self._semaphore:
                await self._throttle()
                resp = await client.post("/optionchain", headers=headers, json=payload)
                if resp.status_code == 429:
                    self._note_rate_limited("optionchain")
                    return {}

                if resp.status_code == 200:
                    self._note_ok()
                    data = resp.json()
                    d = data.get("data", {})
                    return d.get("oc", {}) if isinstance(d, dict) else {}
                logger.warning(f"Optionchain returned HTTP {resp.status_code}: {resp.text[:200]}")
                return {}
        except Exception as e:
            logger.warning(f"Exception fetching optionchain: {e}")
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
        now = market_hours.now_ist_naive()
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
                        self._note_rate_limited("charts/intraday")
                        await self._throttle()
                        resp = await client.post("/charts/intraday", headers=headers, json=payload)

                    if resp.status_code == 200:
                        if idx > 0:
                            logger.info(f"Dhan intraday success with candidate payload {idx} for sec_id={security_id}")
                        data = resp.json()
                        break
                    elif resp.status_code == 400:
                        logger.debug(f"Dhan intraday charts returned HTTP 400 for sec_id={security_id}: {resp.text[:120]}")
                        break
                    else:
                        logger.warning(f"Dhan intraday chart error: HTTP {resp.status_code} for sec_id={security_id}: {resp.text[:120]}")
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

    async def fetch_daily_candles(
        self,
        client_id: str,
        access_token: str,
        security_id: str,
        exchange_segment: str,
        instrument_type: str = "EQUITY",
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Fetch daily candles from Dhan HQ API: POST /charts/historical
        Body: {"securityId", "exchangeSegment", "instrument", "expiryCode": 0, "oi": false, "fromDate", "toDate"} (YYYY-MM-DD).
        Returns columns date (YYYY-MM-DD, IST), open, high, low, close, volume; empty on any failure.
        Whether Dhan adjusts these for splits and bonuses is not documented: check on a known split date before trusting history.
        """
        now = market_hours.now_ist_naive()
        to_date = (to_date or now.strftime("%Y-%m-%d"))[:10]
        from_date = (from_date or (now - timedelta(days=30)).strftime("%Y-%m-%d"))[:10]
        headers = {"client-id": client_id, "access-token": access_token,
                   "Content-Type": "application/json", "Accept": "application/json"}
        payload = {"securityId": str(security_id), "exchangeSegment": exchange_segment, "instrument": instrument_type,
                   "expiryCode": 0, "oi": False, "fromDate": from_date, "toDate": to_date}
        try:
            client = await self.get_client()
            async with self._semaphore:
                await self._throttle()
                resp = await client.post("/charts/historical", headers=headers, json=payload)
                if resp.status_code == 429:
                    self._note_rate_limited("charts/historical")
                    await self._throttle()
                    resp = await client.post("/charts/historical", headers=headers, json=payload)
                if resp.status_code != 200:
                    logger.warning(f"Dhan daily chart error: HTTP {resp.status_code} for sec_id={security_id}: {resp.text[:120]}")
                    return pd.DataFrame()
                data = resp.json()
        except Exception as e:
            logger.warning(f"Exception fetching daily candles for sec_id={security_id}: {e}")
            return pd.DataFrame()
        candles = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else data
        if not isinstance(candles, dict) or not candles.get("close"):
            return pd.DataFrame()
        try:
            timestamps = candles.get("start_Time") or candles.get("timestamp") or candles.get("startTime") or candles.get("time") or []
            parsed = self._parse_dhan_timestamps(timestamps)
            df = pd.DataFrame({
                "date": parsed.strftime("%Y-%m-%d"),
                "open": candles["open"], "high": candles["high"], "low": candles["low"], "close": candles["close"],
                "volume": candles.get("volume") or [0] * len(candles["close"]),
            })
            return df.dropna().drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)
        except Exception as e:
            logger.warning(f"Error assembling DataFrame from Dhan daily candles: {e}")
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
