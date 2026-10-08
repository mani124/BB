from fastapi import APIRouter
from app.services.universe_manager import UniverseManager

router = APIRouter(prefix="/universe", tags=["universe"])
universe_mgr = UniverseManager()

@router.get("")
def get_universe_list():
    return {
        "indices": [i.model_dump() for i in universe_mgr.get_indices()],
        "stocks": [s.model_dump() for s in universe_mgr.get_momentum_stocks()],
        "total_count": len(universe_mgr.get_all_instruments())
    }
