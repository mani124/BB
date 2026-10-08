import pytest
import asyncio
from app.services.universe_manager import UniverseManager
from app.services.scanner_worker import ScannerWorker

def test_universe_manager_curation():
    mgr = UniverseManager()
    indices = mgr.get_indices()
    stocks = mgr.get_momentum_stocks()
    all_inst = mgr.get_all_instruments()
    
    assert len(indices) == 4
    assert any(i.symbol == "NIFTY 50" for i in indices)
    assert any(i.symbol == "NIFTY BANK" for i in indices)
    assert len(stocks) >= 25
    assert len(all_inst) >= 29

@pytest.mark.asyncio
async def test_scanner_worker_demo_cycle():
    worker = ScannerWorker(universe_mgr=UniverseManager())
    # Execute one full scan cycle in demo/synthetic mode
    state = await worker.run_single_scan_cycle(client_id=None, access_token=None)
    
    assert state.scan_cycle_count >= 1
    assert state.universe_count >= 29
    assert len(state.radar) == 4
    assert "NIFTY 50" in state.radar
    assert "NIFTY BANK" in state.radar
    assert isinstance(state.signals, list)
    assert state.scan_progress == 100.0
