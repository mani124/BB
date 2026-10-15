"""Entry liquidity filter: wide bid-ask spread, thin volume / open interest, optional premium floor.

Thresholds are PROVISIONAL. No real liquidity data existed when this was written, so the
defaults only drive the "would skip" log. The filter does not block entries unless
LIQ_FILTER_ENABLED=1. Use scripts/liquidity_analysis.py on trades.db to pick real values.
A threshold of 0 disables that check; a missing quote field never triggers a skip.
"""
import logging
from typing import Any, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


def spread_pct(bid: Optional[float], ask: Optional[float]) -> Optional[float]:
    """Same definition as the logged entry_spread_pct: (ask - bid) / ask * 100."""
    if not bid or not ask or bid <= 0 or ask <= 0 or bid > ask:
        return None
    return (ask - bid) / ask * 100.0


def evaluate(bid=None, ask=None, volume=None, oi=None, premium=None, cfg: Any = None) -> list[str]:
    """Return the reasons this option fails the liquidity thresholds (empty list = passes)."""
    cfg = cfg or settings
    reasons: list[str] = []
    max_spread = float(getattr(cfg, "LIQ_MAX_SPREAD_PCT", 0) or 0)
    sp = spread_pct(bid, ask)
    if max_spread > 0 and sp is not None and sp > max_spread:
        reasons.append(f"spread {sp:.1f}% > {max_spread:g}%")
    min_vol = float(getattr(cfg, "LIQ_MIN_VOLUME", 0) or 0)
    if min_vol > 0 and volume is not None and volume < min_vol:
        reasons.append(f"volume {volume:g} < {min_vol:g}")
    min_oi = float(getattr(cfg, "LIQ_MIN_OI", 0) or 0)
    if min_oi > 0 and oi is not None and oi < min_oi:
        reasons.append(f"OI {oi:g} < {min_oi:g}")
    min_prem = float(getattr(cfg, "LIQ_MIN_PREMIUM", 0) or 0)
    if min_prem > 0 and premium is not None and premium < min_prem:
        reasons.append(f"premium {premium:g} < {min_prem:g}")
    return reasons


def check_recommendation(rec: Any, symbol: str = "", side: str = "", cfg: Any = None) -> Optional[str]:
    """Evaluate a strike recommendation. Logs LIQ_FILTER would_skip / blocked.

    Returns a block reason only when the filter is enabled; otherwise None (shadow mode)."""
    cfg = cfg or settings
    ask = getattr(rec, "real_ask_price", None)
    premium = ask if ask else getattr(rec, "estimated_option_entry", None)
    reasons = evaluate(
        bid=getattr(rec, "real_bid_price", None), ask=ask,
        volume=getattr(rec, "real_volume", None), oi=getattr(rec, "real_oi", None),
        premium=premium, cfg=cfg,
    )
    if not reasons:
        return None
    text = "; ".join(reasons)
    enabled = bool(getattr(cfg, "LIQ_FILTER_ENABLED", False))
    logger.warning("LIQ_FILTER %s symbol=%s side=%s reasons=%s",
                   "blocked" if enabled else "would_skip", symbol, side, text)
    return text if enabled else None
