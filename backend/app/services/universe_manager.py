from pydantic import BaseModel
from typing import Literal

class Instrument(BaseModel):
    symbol: str
    name: str
    security_id: str
    exchange_segment: str
    instrument_type: Literal["INDEX", "EQUITY"]
    default_timeframe: str  # "5m" for indices, "15m" for stocks
    sector: str

class UniverseManager:
    """Manages the 4 major indices and the top curated high-beta liquid F&O momentum stocks."""
    
    INDICES: list[Instrument] = [
        Instrument(
            symbol="NIFTY 50",
            name="Nifty 50 Index",
            security_id="13",
            exchange_segment="IDX_I",
            instrument_type="INDEX",
            default_timeframe="5m",
            sector="Benchmark"
        ),
        Instrument(
            symbol="NIFTY BANK",
            name="Bank Nifty Index",
            security_id="25",
            exchange_segment="IDX_I",
            instrument_type="INDEX",
            default_timeframe="5m",
            sector="Banking"
        ),
        Instrument(
            symbol="FINNIFTY",
            name="Nifty Financial Services",
            security_id="27",
            exchange_segment="IDX_I",
            instrument_type="INDEX",
            default_timeframe="5m",
            sector="Financials"
        ),
        Instrument(
            symbol="SENSEX",
            name="BSE Sensex Index",
            security_id="51",
            exchange_segment="IDX_I",
            instrument_type="INDEX",
            default_timeframe="5m",
            sector="Benchmark"
        ),
    ]

    MOMENTUM_STOCKS: list[Instrument] = [
        # Banking & Financials
        Instrument(symbol="HDFCBANK", name="HDFC Bank", security_id="1333", exchange_segment="NSE_EQ", instrument_type="EQUITY", default_timeframe="15m", sector="Banking"),
        Instrument(symbol="ICICIBANK", name="ICICI Bank", security_id="4963", exchange_segment="NSE_EQ", instrument_type="EQUITY", default_timeframe="15m", sector="Banking"),
        Instrument(symbol="SBIN", name="State Bank of India", security_id="3045", exchange_segment="NSE_EQ", instrument_type="EQUITY", default_timeframe="15m", sector="Banking"),
        Instrument(symbol="AXISBANK", name="Axis Bank", security_id="5900", exchange_segment="NSE_EQ", instrument_type="EQUITY", default_timeframe="15m", sector="Banking"),
        Instrument(symbol="KOTAKBANK", name="Kotak Mahindra Bank", security_id="1922", exchange_segment="NSE_EQ", instrument_type="EQUITY", default_timeframe="15m", sector="Banking"),
        Instrument(symbol="BAJFINANCE", name="Bajaj Finance", security_id="317", exchange_segment="NSE_EQ", instrument_type="EQUITY", default_timeframe="15m", sector="Financials"),
        Instrument(symbol="BAJAJFINSV", name="Bajaj Finserv", security_id="16669", exchange_segment="NSE_EQ", instrument_type="EQUITY", default_timeframe="15m", sector="Financials"),
        # IT
        Instrument(symbol="INFY", name="Infosys", security_id="1594", exchange_segment="NSE_EQ", instrument_type="EQUITY", default_timeframe="15m", sector="IT"),
        Instrument(symbol="TCS", name="Tata Consultancy Services", security_id="11536", exchange_segment="NSE_EQ", instrument_type="EQUITY", default_timeframe="15m", sector="IT"),
        Instrument(symbol="HCLTECH", name="HCL Technologies", security_id="7229", exchange_segment="NSE_EQ", instrument_type="EQUITY", default_timeframe="15m", sector="IT"),
        Instrument(symbol="TECHM", name="Tech Mahindra", security_id="13538", exchange_segment="NSE_EQ", instrument_type="EQUITY", default_timeframe="15m", sector="IT"),
        # Auto & Mobility
        Instrument(symbol="TATAMOTORS", name="Tata Motors", security_id="3456", exchange_segment="NSE_EQ", instrument_type="EQUITY", default_timeframe="15m", sector="Auto"),
        Instrument(symbol="MARUTI", name="Maruti Suzuki", security_id="10999", exchange_segment="NSE_EQ", instrument_type="EQUITY", default_timeframe="15m", sector="Auto"),
        Instrument(symbol="M&M", name="Mahindra & Mahindra", security_id="2031", exchange_segment="NSE_EQ", instrument_type="EQUITY", default_timeframe="15m", sector="Auto"),
        Instrument(symbol="BAJAJ-AUTO", name="Bajaj Auto", security_id="16675", exchange_segment="NSE_EQ", instrument_type="EQUITY", default_timeframe="15m", sector="Auto"),
        # Energy, Metals & Infra
        Instrument(symbol="RELIANCE", name="Reliance Industries", security_id="2885", exchange_segment="NSE_EQ", instrument_type="EQUITY", default_timeframe="15m", sector="Energy"),
        Instrument(symbol="TATASTEEL", name="Tata Steel", security_id="3499", exchange_segment="NSE_EQ", instrument_type="EQUITY", default_timeframe="15m", sector="Metals"),
        Instrument(symbol="JSWSTEEL", name="JSW Steel", security_id="11723", exchange_segment="NSE_EQ", instrument_type="EQUITY", default_timeframe="15m", sector="Metals"),
        Instrument(symbol="HINDALCO", name="Hindalco Industries", security_id="1363", exchange_segment="NSE_EQ", instrument_type="EQUITY", default_timeframe="15m", sector="Metals"),
        Instrument(symbol="COALINDIA", name="Coal India", security_id="20374", exchange_segment="NSE_EQ", instrument_type="EQUITY", default_timeframe="15m", sector="Energy"),
        Instrument(symbol="ONGC", name="Oil and Natural Gas Corp", security_id="2475", exchange_segment="NSE_EQ", instrument_type="EQUITY", default_timeframe="15m", sector="Energy"),
        Instrument(symbol="LT", name="Larsen & Toubro", security_id="11483", exchange_segment="NSE_EQ", instrument_type="EQUITY", default_timeframe="15m", sector="Infra"),
        Instrument(symbol="ADANIENT", name="Adani Enterprises", security_id="25", exchange_segment="NSE_EQ", instrument_type="EQUITY", default_timeframe="15m", sector="Diversified"),
        Instrument(symbol="ADANIPORTS", name="Adani Ports", security_id="15083", exchange_segment="NSE_EQ", instrument_type="EQUITY", default_timeframe="15m", sector="Infra"),
        # Telecom, Consumer & Pharma
        Instrument(symbol="BHARTIARTL", name="Bharti Airtel", security_id="10604", exchange_segment="NSE_EQ", instrument_type="EQUITY", default_timeframe="15m", sector="Telecom"),
        Instrument(symbol="ITC", name="ITC Limited", security_id="1660", exchange_segment="NSE_EQ", instrument_type="EQUITY", default_timeframe="15m", sector="FMCG"),
        Instrument(symbol="TITAN", name="Titan Company", security_id="3506", exchange_segment="NSE_EQ", instrument_type="EQUITY", default_timeframe="15m", sector="Consumer"),
        Instrument(symbol="SUNPHARMA", name="Sun Pharma", security_id="3351", exchange_segment="NSE_EQ", instrument_type="EQUITY", default_timeframe="15m", sector="Pharma"),
        Instrument(symbol="CIPLA", name="Cipla", security_id="694", exchange_segment="NSE_EQ", instrument_type="EQUITY", default_timeframe="15m", sector="Pharma"),
        Instrument(symbol="DRREDDY", name="Dr. Reddy's Laboratories", security_id="881", exchange_segment="NSE_EQ", instrument_type="EQUITY", default_timeframe="15m", sector="Pharma"),
    ]

    def get_indices(self) -> list[Instrument]:
        return self.INDICES

    def get_momentum_stocks(self) -> list[Instrument]:
        return self.MOMENTUM_STOCKS

    def get_all_instruments(self) -> list[Instrument]:
        return self.INDICES + self.MOMENTUM_STOCKS
