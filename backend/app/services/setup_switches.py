"""Per-setup on/off switches for auto-entry.

Each setup runs in one of four modes: off, index (indices only), stocks (stocks only), all.
Switches are enforced where a position would be opened, so a blocked signal never trades.
"""
import re
from typing import Optional

from app.services.strategy_engine import INDEX_SYMBOLS

MODES = ("off", "index", "stocks", "all")

# Defaults from the 2026-10-15 trade review: Setups 1 and 2 lost money on stock options.
DEFAULT_MODES: dict[str, str] = {
    "1": "index",
    "2": "index",
    "3": "all",
    "4": "all",
    "5": "all",
    "6": "all",
    "7": "all",
    "8": "all",
    "9": "all",
    "10": "index",
}


def setup_number(setup_type) -> Optional[str]:
    """'Setup 5: Option Chart BB Scalp' (or the enum) -> '5'."""
    text = str(getattr(setup_type, "value", setup_type) or "")
    m = re.match(r"\s*Setup\s+(\d+)", text)
    return m.group(1) if m else None


def normalize_modes(raw: Optional[dict]) -> dict[str, str]:
    """Defaults overlaid with any valid entries from `raw`; unknown setups or modes are dropped."""
    out = dict(DEFAULT_MODES)
    for key, mode in (raw or {}).items():
        key = str(key)
        if key in DEFAULT_MODES and str(mode) in MODES:
            out[key] = str(mode)
    return out


def block_reason(modes: dict[str, str], setup_type, symbol: str) -> Optional[str]:
    """Why this setup/symbol pair is switched off, or None when it may trade."""
    num = setup_number(setup_type)
    if num is None:
        return None
    mode = modes.get(num, DEFAULT_MODES.get(num, "all"))
    is_index = str(symbol).upper() in INDEX_SYMBOLS
    if mode == "off":
        return f"Setup {num} is switched off"
    if mode == "index" and not is_index:
        return f"Setup {num} is limited to indices"
    if mode == "stocks" and is_index:
        return f"Setup {num} is limited to stocks"
    return None
