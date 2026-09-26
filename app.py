import os
import sqlite3
import requests
import math
import re
import time
from pathlib import Path
from functools import lru_cache
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
DATABASE_PATH = Path(__file__).resolve().parent / "backend" / "database" / "airports.db"
OPEN_SKY_CACHE_TTL_SECONDS = 25
OPEN_SKY_CACHE = {}

def get_airport_info(airport_code):
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    query = "SELECT latitude_deg, longitude_deg, name FROM airports WHERE ident = ? OR iata_code = ? LIMIT 1"
    cursor.execute(query, (airport_code.upper(), airport_code.upper()))
    result = cursor.fetchone()
    conn.close()
    return {"lat": result[0], "lon": result[1], "name": result[2]} if result else None

def calculate_bounding_box(lat, lon, radius_miles=20):
    lat_offset = radius_miles / 69.0
    lon_offset = radius_miles / (69.172 * max(math.cos(math.radians(lat)), 0.01))
    return {"lamin": lat - lat_offset, "lamax": lat + lat_offset, "lomin": lon - lon_offset, "lomax": lon + lon_offset}

def project_aircraft_position(flight_lat, flight_lon, airport_lat, airport_lon, radius_miles):
    earth_radius_miles = 3958.7613
    airport_lat_radians = math.radians(airport_lat)
    flight_lat_radians = math.radians(flight_lat)
    lat_delta = flight_lat_radians - airport_lat_radians
    lon_delta = math.radians(flight_lon - airport_lon)
    haversine = (math.sin(lat_delta / 2) ** 2
                 + math.cos(airport_lat_radians) * math.cos(flight_lat_radians)
                 * math.sin(lon_delta / 2) ** 2)
    distance_miles = earth_radius_miles * 2 * math.atan2(math.sqrt(haversine), math.sqrt(1 - haversine))
    bearing = math.atan2(
        math.sin(lon_delta) * math.cos(flight_lat_radians),
        math.cos(airport_lat_radians) * math.sin(flight_lat_radians)
        - math.sin(airport_lat_radians) * math.cos(flight_lat_radians) * math.cos(lon_delta),
    )
    bearing_radians = bearing % (2 * math.pi)
    x_percent = 50 + math.sin(bearing_radians) * (distance_miles / radius_miles) * 40
    y_percent = 50 - math.cos(bearing_radians) * (distance_miles / radius_miles) * 40

    return {
        "x_percent": max(5, min(95, x_percent)),
        "y_percent": max(5, min(95, y_percent)),
        "distance_miles": round(distance_miles, 1),
    }

@lru_cache(maxsize=512)
def get_aircraft_metadata(icao24):
    try:
        response = requests.get(
            f"https://opensky-network.org/api/metadata/aircraft/icao24/{icao24}",
            timeout=5,
        )
        return response.json() if response.status_code == 200 else None
    except (requests.exceptions.RequestException, ValueError):
        return None


OPERATOR_PREFIXES = {
    "AAL": "American Airlines",
    "ACA": "Air Canada",
    "AFR": "Air France",
    "AIC": "Air India",
    "ANA": "All Nippon Airways",
    "ASA": "Alaska Airlines",
    "BAW": "British Airways",
    "BER": "Air Berlin",
    "DAL": "Delta Air Lines",
    "DLH": "Lufthansa",
    "EZY": "easyJet",
    "FDX": "FedEx",
    "GFA": "Gulf Air",
    "HKA": "Hainan Airlines",
    "JAL": "Japan Airlines",
    "KLM": "KLM Royal Dutch Airlines",
    "LHA": "Lufthansa",
    "NKS": "Spirit Airlines",
    "QFA": "Qantas",
    "SWA": "Southwest Airlines",
    "THY": "Turkish Airlines",
    "UAL": "United Airlines",
    "UPS": "United Parcel Service",
    "VIR": "Virgin Atlantic",
    "VLG": "Vueling",
    "NAX": "Norwegian Air Shuttle",
    "KAL": "Korean Air",
    "ETD": "Etihad Airways",
    "UAE": "Emirates",
    "RYR": "Ryanair",
    "IBE": "Iberia",
    "BPA": "Jet2",
    "SAS": "Scandinavian Airlines",
    "AZA": "Alitalia",
    "AFL": "AeroFlot",
    "SKW": "SkyWest Airlines",
    "CPA": "Cathay Pacific",
    "CXA": "Cathay Pacific",
    "DXA": "DHL Aviation",
    "CFS": "China Southern Airlines",
    "CSN": "China Southern Airlines",
    "EVA": "EVA Air",
    "JBU": "JetBlue Airways",
    "NWA": "Northwest Airlines",
    "TAM": "LATAM Airlines",
    "AMX": "Aeromexico",
    "BIM": "Biman Bangladesh Airlines",
    "HVN": "Vietnam Airlines",
    "LNX": "Lynx Air",
    "MAY": "Malaysia Airlines",
    "MUA": "KLM Cityhopper",
}

MODEL_ALIASES = {
    "A319": "Airbus A319",
    "A320": "Airbus A320",
    "A321": "Airbus A321",
    "A332": "Airbus A330-200",
    "A333": "Airbus A330-300",
    "A342": "Airbus A340-200",
    "A343": "Airbus A340-300",
    "A345": "Airbus A340-500",
    "A346": "Airbus A340-600",
    "A350": "Airbus A350",
    "A359": "Airbus A350-900",
    "A388": "Airbus A380-800",
    "B737": "Boeing 737",
    "B737800": "Boeing 737-800",
    "B738": "Boeing 737-800",
    "B739": "Boeing 737-900",
    "B744": "Boeing 747-400",
    "B752": "Boeing 757-200",
    "B753": "Boeing 757-300",
    "B763": "Boeing 767-300",
    "B764": "Boeing 767-400",
    "B772": "Boeing 777-200",
    "B773": "Boeing 777-300",
    "B77L": "Boeing 777-200LR",
    "B788": "Boeing 787-8",
    "B789": "Boeing 787-9",
    "B78X": "Boeing 787",
    "B190": "Beechcraft 1900",
    "E145": "Embraer ERJ-145",
    "E170": "Embraer E170",
    "E190": "Embraer E190",
    "E195": "Embraer E195",
    "CRJ2": "Bombardier CRJ200",
    "CRJ7": "Bombardier CRJ700",
    "CRJ9": "Bombardier CRJ900",
    "C172": "Cessna 172",
    "C182": "Cessna 182",
    "P28A": "Piper PA-28 Cherokee",
    "AT72": "ATR 72-600",
    "AT75": "ATR 75",
    "DH8D": "De Havilland Dash 8 Q400",
    "MD83": "McDonnell Douglas MD-83",
    "MD88": "McDonnell Douglas MD-88",
    "MD11": "McDonnell Douglas MD-11",
    "A320F": "Airbus A320 Freighter",
    "B737F": "Boeing 737 Freighter",
    "B767F": "Boeing 767 Freighter",
    "B777F": "Boeing 777 Freighter",
}


def normalize_aircraft_model(raw_model):
    if not raw_model:
        return "Aircraft type unavailable"
    candidate = re.sub(r"[^A-Z0-9]", "", str(raw_model).upper())
    if candidate in MODEL_ALIASES:
        return MODEL_ALIASES[candidate]
    for prefix, label in sorted(MODEL_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if candidate.startswith(prefix):
            return label
    return str(raw_model).strip() or "Aircraft type unavailable"


def resolve_operator_name(callsign, metadata=None):
    if metadata and metadata.get("operatorname"):
        return metadata["operatorname"]
    if metadata and metadata.get("operatoricao"):
        return metadata["operatoricao"]
    prefix = (callsign or "").strip().upper()
    if len(prefix) >= 3:
        airline = OPERATOR_PREFIXES.get(prefix[:3])
        if airline:
            return airline
    if len(prefix) >= 2:
        airline = OPERATOR_PREFIXES.get(prefix[:2])
        if airline:
            return airline
    return "Operator unavailable"


def resolve_aircraft_meta(icao24, category_id, callsign=None):
    metadata = get_aircraft_metadata(icao24) or {}
    category_names = {
        1: "Unknown",
        2: "Light",
        3: "Small",
        4: "Large",
        5: "High performance",
        6: "Helicopter",
        7: "Glider",
        8: "Lighter-than-air",
        9: "Parachutist",
        10: "Ultralight",
        11: "Reserved",
        12: "Drone",
        13: "Space vehicle",
        14: "Emergency",
        15: "Service",
        16: "Point obstacle",
    }
    typecode = (metadata.get("typecode") or "").upper()
    model = normalize_aircraft_model(metadata.get("model") or typecode)
    operator = resolve_operator_name(callsign, metadata)
    aircraft_type = category_names.get(category_id, "Unknown")

    if category_id in (2, 3, 6, 7, 8, 9, 10, 12):
        visual_type = "private"
    elif category_id in (13, 14, 15, 16):
        visual_type = "military"
    elif typecode.endswith("F") or "FREIGHT" in model.upper() or "CARGO" in model.upper():
        visual_type = "cargo"
    else:
        visual_type = "commercial"

    return {
        "model": model,
        "operator": operator or "Operator unavailable",
        "aircraft_type": aircraft_type,
        "type": visual_type,
    }




def build_demo_aircraft(airport, radius=25, operator_filter=None):
    sample_flights = [
        {"callsign": "AAL128", "operator": "American Airlines", "model": "Airbus A320", "type": "commercial", "aircraft_type": "Large", "heading": 115, "offset_deg": 0.28, "distance": 7.4},
        {"callsign": "DAL411", "operator": "Delta Air Lines", "model": "Boeing 737-800", "type": "commercial", "aircraft_type": "Large", "heading": 230, "offset_deg": 0.16, "distance": 12.2},
        {"callsign": "UPS214", "operator": "United Parcel Service", "model": "Boeing 767 Freighter", "type": "cargo", "aircraft_type": "Large", "heading": 300, "offset_deg": 0.34, "distance": 18.7},
        {"callsign": "N123AB", "operator": "Private Owner", "model": "Cessna 172", "type": "private", "aircraft_type": "Small", "heading": 80, "offset_deg": -0.22, "distance": 5.9},
    ]

    flights = []
    for idx, sample in enumerate(sample_flights):
        if operator_filter and operator_filter.lower() not in sample["operator"].lower():
            continue
        bearing = (idx * 1.7) + sample["offset_deg"]
        lat_offset = (sample["distance"] / 69.0) * math.cos(bearing)
        lon_offset = (sample["distance"] / (69.172 * max(math.cos(math.radians(airport['lat'])), 0.01))) * math.sin(bearing)
        lat = airport['lat'] + lat_offset
        lon = airport['lon'] + lon_offset
        position = project_aircraft_position(lat, lon, airport['lat'], airport['lon'], radius)
        flights.append({
            "icao24": f"demo{idx}",
            "callsign": sample["callsign"],
            "altitude": f"{12000 + idx * 2500} ft",
            "on_ground": "No",
            "speed": f"{420 - idx * 40} kts",
            "heading": sample["heading"],
            "model": sample["model"],
            "operator": sample["operator"],
            "aircraft_type": sample["aircraft_type"],
            "type": sample["type"],
            "x_percent": position["x_percent"],
            "y_percent": position["y_percent"],
            "distance_miles": position["distance_miles"],
        })

    return flights


def get_nearby_aircraft(airport_code, radius=25, operator_filter=None):
    airport = get_airport_info(airport_code)
    if not airport:
        return {"error": f"Airport '{airport_code.upper()}' could not be found in the database."}

    cache_key = (airport_code.upper(), radius, (operator_filter or "").lower())
    cached_result = OPEN_SKY_CACHE.get(cache_key)
    if cached_result and time.monotonic() - cached_result["timestamp"] < OPEN_SKY_CACHE_TTL_SECONDS:
        return cached_result["result"]

    params = calculate_bounding_box(airport['lat'], airport['lon'], radius_miles=radius)
    url = "https://opensky-network.org/api/states/all"
    last_error = None

    try:
        headers = {'User-Agent': 'TRMNL Flight Radar/1.0'}
        response = requests.get(url, params=params, headers=headers, timeout=6)

        if response.status_code == 429:
            return {"error": "OpenSky API rate limit reached. Please wait a minute."}
        if response.status_code != 200:
            raise requests.exceptions.HTTPError(f"status {response.status_code}")

        data = response.json()
        states = data.get("states", []) or []

        aircraft_list = []
        for flight in states:
            if len(flight) > 8:
                icao24 = flight[0]
                latitude = flight[6]
                longitude = flight[5]
                if latitude is None or longitude is None:
                    continue

                position = project_aircraft_position(latitude, longitude, airport['lat'], airport['lon'], radius)
                if position["distance_miles"] > radius:
                    continue

                velocity_ms = flight[9]
                speed_knots = int(velocity_ms * 1.94384) if velocity_ms is not None else 0
                heading = int(flight[10]) if flight[10] is not None else 0
                category_id = flight[17] if len(flight) > 17 else None

                callsign = flight[1].strip() if flight[1] else "UNKNOWN"
                meta = resolve_aircraft_meta(icao24, category_id, callsign=callsign)
                if meta["operator"] == "Operator unavailable" and callsign != "UNKNOWN":
                    meta["operator"] = f"{callsign[:3]} (callsign)"
                if operator_filter and operator_filter.lower() not in meta["operator"].lower():
                    continue

                aircraft_list.append({
                    "icao24": icao24,
                    "callsign": callsign,
                    "altitude": f"{int(flight[7] * 3.28084)} ft" if flight[7] is not None else "Ground / Unknown",
                    "on_ground": "Yes" if flight[8] else "No",
                    "speed": f"{speed_knots} kts",
                    "heading": heading,
                    "model": meta["model"],
                    "operator": meta["operator"],
                    "aircraft_type": meta["aircraft_type"],
                    "type": meta["type"],
                    "x_percent": position["x_percent"],
                    "y_percent": position["y_percent"],
                    "distance_miles": position["distance_miles"],
                })

        result = {
            "airport_name": airport['name'],
            "code": airport_code.upper(),
            "search_radius": radius,
            "tower": {"lat": airport["lat"], "lon": airport["lon"], "label": "ATC tower"},
            "operator_filter": operator_filter or "",
            "aircraft_count": len(aircraft_list),
            "flights": aircraft_list,
            "source": "live",
        }
        OPEN_SKY_CACHE[cache_key] = {"timestamp": time.monotonic(), "result": result}
        return result
    except requests.exceptions.RequestException as error:
        last_error = error

    fallback_flights = build_demo_aircraft(airport, radius=radius, operator_filter=operator_filter)
    return {
        "airport_name": airport['name'],
        "code": airport_code.upper(),
        "search_radius": radius,
        "tower": {"lat": airport["lat"], "lon": airport["lon"], "label": "ATC tower"},
        "operator_filter": operator_filter or "",
        "aircraft_count": len(fallback_flights),
        "flights": fallback_flights,
        "source": "demo",
        "warning": f"OpenSky timed out; showing demo aircraft data. ({last_error.__class__.__name__ if last_error else 'network'})",
    }

@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")


@app.route("/api/flights", methods=["GET"])
def flights_api():
    airport_query = request.args.get("airport", "").strip()
    radius_query = request.args.get("radius", default=25, type=int) or 25
    operator_filter = request.args.get("operator", "").strip() or None

    if not airport_query:
        return jsonify({"error": "An airport code is required."}), 400

    radius_query = max(5, min(250, radius_query))
    result = get_nearby_aircraft(airport_query, radius=radius_query, operator_filter=operator_filter)
    return jsonify(result), 404 if "error" in result else 200

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
