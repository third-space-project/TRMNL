import json
from pathlib import Path

AIRCRAFT_DB_PATH = Path(__file__).parent / "backend" / "database" / "aircraft.json"

_aircraft_cache = dict | None = None

def _load():
    global _aircraft_cache
    if _aircraft_cache is None:
        with open(AIRCRAFT_DB_PATH, "r", encoding = "utf-8") as f:
            _aircraft_cache = json.load(f)

        return _aircraft_cache

def resolve_operator(callsign: str):
    if not callsign:
        return "Unknown Operator"

    prefix = callsign.strip().upper()[:3]
    db = _load()
    return db.get(prefix, "Unknown Operator")