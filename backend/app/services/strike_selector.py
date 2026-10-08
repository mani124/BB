from pydantic import BaseModel
from typing import Literal

class OptionStrikeRecommendation(BaseModel):
    symbol: str
    underlying_price: float
    option_type: Literal["CE", "PE"]
    atm_strike: int
    recommended_strike: int  # 1-strike ITM for best delta/gamma vs theta balance
    strike_symbol: str
    risk: float
    stop_loss: float
    target_1: float  # 1:1.5 RR
    target_2: float  # 1:2.5 RR

INDEX_STRIKE_STEPS: dict[str, int] = {
    "NIFTY 50": 50,
    "NIFTY": 50,
    "NIFTY BANK": 100,
    "BANKNIFTY": 100,
    "FINNIFTY": 50,
    "NIFTY FINANCIAL SERVICES": 50,
    "SENSEX": 100,
    "MIDCPNIFTY": 25,
}

STOCK_STRIKE_STEPS: dict[str, int] = {
    "RELIANCE": 20,
    "HDFCBANK": 10,
    "ICICIBANK": 10,
    "SBIN": 5,
    "AXISBANK": 10,
    "KOTAKBANK": 10,
    "INFY": 20,
    "TCS": 50,
    "TATAMOTORS": 10,
    "MARUTI": 100,
    "LT": 20,
    "BHARTIARTL": 10,
    "BAJFINANCE": 50,
    "BAJAJFINSV": 20,
    "TATASTEEL": 2,
    "JSWSTEEL": 10,
    "ITC": 5,
    "TITAN": 20,
    "SUNPHARMA": 10,
}

def get_strike_step(symbol: str, price: float) -> int:
    clean_sym = symbol.upper().strip()
    if clean_sym in INDEX_STRIKE_STEPS:
        return INDEX_STRIKE_STEPS[clean_sym]
    if clean_sym in STOCK_STRIKE_STEPS:
        return STOCK_STRIKE_STEPS[clean_sym]
    
    # Generic estimation based on price tier
    if price < 250:
        return 5
    elif price < 500:
        return 10
    elif price < 1500:
        return 20
    elif price < 3500:
        return 50
    else:
        return 100

def recommend_strike(
    symbol: str,
    underlying_price: float,
    option_type: Literal["CE", "PE"],
    stop_loss: float
) -> OptionStrikeRecommendation:
    step = get_strike_step(symbol, underlying_price)
    
    # ATM strike
    atm_strike = int(round(underlying_price / step) * step)
    
    # 1-strike ITM for highest delta responsiveness (Delta ~0.55-0.60)
    if option_type == "CE":
        recommended_strike = atm_strike - step
    else:
        recommended_strike = atm_strike + step

    strike_symbol = f"{symbol} {recommended_strike} {option_type}"
    risk = round(abs(underlying_price - stop_loss), 2)
    
    # Target calculations based on underlying price move
    if option_type == "CE":
        target_1 = round(underlying_price + 1.5 * risk, 2)
        target_2 = round(underlying_price + 2.5 * risk, 2)
    else:
        target_1 = round(underlying_price - 1.5 * risk, 2)
        target_2 = round(underlying_price - 2.5 * risk, 2)

    return OptionStrikeRecommendation(
        symbol=symbol,
        underlying_price=round(underlying_price, 2),
        option_type=option_type,
        atm_strike=atm_strike,
        recommended_strike=recommended_strike,
        strike_symbol=strike_symbol,
        risk=risk,
        stop_loss=round(stop_loss, 2),
        target_1=target_1,
        target_2=target_2
    )
