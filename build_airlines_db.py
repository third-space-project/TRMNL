import csv
import io
import json
import requests
from pathlib import Path

AIRLINES_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airlines.dat"
OUTPUT_PATH = Path(__file__).parent / "backend" / "database" / "airlines.json"

COLUMNS = [
    "id", "name", "alias", "iata", "icao",
    "callsign", "country", "active"
]
