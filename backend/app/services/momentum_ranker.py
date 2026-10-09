from typing import Literal, Optional
from pydantic import BaseModel, Field

class StockMomentumProfile(BaseModel):
    symbol: str
    ltp: float
    change_pct: float
    vwap: float
    vwap_distance_pct: float
    range_position_pct: float  # 0 to 100
    composite_score: float
    bias: Literal["BULLISH", "BEARISH", "NEUTRAL"]

class MomentumRankings(BaseModel):
    top_bullish: list[str] = Field(default_factory=list)
    top_bearish: list[str] = Field(default_factory=list)
    profiles: dict[str, StockMomentumProfile] = Field(default_factory=dict)

    def get_bias(self, symbol: str) -> Literal["BULLISH", "BEARISH", "NEUTRAL"]:
        if symbol in self.top_bullish:
            return "BULLISH"
        if symbol in self.top_bearish:
            return "BEARISH"
        return "NEUTRAL"

class MomentumRanker:
    """
    Ranks stocks based on live daily/intraday momentum metrics:
    - Day % Change from previous close / open
    - Proximity to Day High vs Day Low (range position)
    - Distance above/below VWAP
    """

    def __init__(
        self,
        top_n: int = 5,
        min_bullish_change_pct: float = 0.75,
        min_bearish_change_pct: float = -0.75,
        min_bullish_range_pos: float = 65.0,
        max_bearish_range_pos: float = 35.0,
    ):
        self.top_n = top_n
        self.min_bullish_change_pct = min_bullish_change_pct
        self.min_bearish_change_pct = min_bearish_change_pct
        self.min_bullish_range_pos = min_bullish_range_pos
        self.max_bearish_range_pos = max_bearish_range_pos

    def rank_stocks(self, quotes: dict[str, dict]) -> MomentumRankings:
        profiles: dict[str, StockMomentumProfile] = {}
        bullish_candidates: list[tuple[float, str]] = []
        bearish_candidates: list[tuple[float, str]] = []

        for symbol, q in quotes.items():
            if not isinstance(q, dict):
                continue

            ltp = float(q.get("last_price", 0.0))
            if ltp <= 0:
                continue

            ohlc = q.get("ohlc", {})
            prev_close = float(ohlc.get("close", 0.0))
            day_open = float(ohlc.get("open", ltp))
            day_high = max(float(ohlc.get("high", ltp)), ltp)
            day_low = min(float(ohlc.get("low", ltp)), ltp)
            vwap = float(q.get("average_price", ltp))
            if vwap <= 0:
                vwap = ltp

            # 1. Day Change %
            if prev_close > 0:
                change_pct = ((ltp - prev_close) / prev_close) * 100.0
            elif day_open > 0:
                change_pct = ((ltp - day_open) / day_open) * 100.0
            else:
                change_pct = 0.0

            # 2. VWAP Distance %
            vwap_dist_pct = ((ltp - vwap) / vwap) * 100.0

            # 3. Range Position % (0% = at low, 100% = at high)
            range_span = day_high - day_low
            if range_span > 0:
                range_pos_pct = ((ltp - day_low) / range_span) * 100.0
            else:
                range_pos_pct = 50.0

            # 4. Composite Momentum Score
            # Weight: 40% change_pct + 30% vwap_dist_pct + 30% normalized range_pos
            score = (change_pct * 0.4) + (vwap_dist_pct * 0.3) + ((range_pos_pct - 50.0) * 0.3)

            # Classify candidate
            bias: Literal["BULLISH", "BEARISH", "NEUTRAL"] = "NEUTRAL"
            if (
                change_pct >= self.min_bullish_change_pct
                and ltp > vwap
                and range_pos_pct >= self.min_bullish_range_pos
                and score > 0
            ):
                bias = "BULLISH"
                bullish_candidates.append((score, symbol))
            elif (
                change_pct <= self.min_bearish_change_pct
                and ltp < vwap
                and range_pos_pct <= self.max_bearish_range_pos
                and score < 0
            ):
                bias = "BEARISH"
                bearish_candidates.append((score, symbol))

            profiles[symbol] = StockMomentumProfile(
                symbol=symbol,
                ltp=round(ltp, 2),
                change_pct=round(change_pct, 2),
                vwap=round(vwap, 2),
                vwap_distance_pct=round(vwap_dist_pct, 2),
                range_position_pct=round(range_pos_pct, 1),
                composite_score=round(score, 2),
                bias=bias,
            )

        # Sort bullish descending (highest score first)
        bullish_candidates.sort(key=lambda x: x[0], reverse=True)
        # Sort bearish ascending (most negative score first)
        bearish_candidates.sort(key=lambda x: x[0])

        top_bullish = [sym for _, sym in bullish_candidates[: self.top_n]]
        top_bearish = [sym for _, sym in bearish_candidates[: self.top_n]]

        return MomentumRankings(
            top_bullish=top_bullish,
            top_bearish=top_bearish,
            profiles=profiles,
        )
