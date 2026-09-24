import sqlite3
import requests
import math
from flask import Flask, render_template, request
from aircraft_lookup import resolve_operator

app = Flask(__name__)

def get_airport_info(airport_code):
    conn = sqlite3.connect('backend/database/airports.db')
    cursor = conn.cursor()
    query = "SELECT latitude_deg, longitude_deg, name FROM airports WHERE ident = ? OR iata_code = ? LIMIT 1"
    cursor.execute(query, (airport_code.upper(), airport_code.upper()))
    result = cursor.fetchone()
    conn.close()
    return {"lat": result[0], "lon": result[1], "name": result[2]} if result else None

def calculate_bounding_box(lat, lon, radius_miles=20):
    lat_offset = radius_miles / 69.0
    lon_offset = radius_miles / 57.0
    return {"lamin": lat - lat_offset, "lamax": lat + lat_offset, "lomin": lon - lon_offset, "lomax": lon + lon_offset}

def project_aircraft_position(flight_lat, flight_lon, airport_lat, airport_lon, radius_miles):
    lat_delta = flight_lat - airport_lat
    lon_delta = flight_lon - airport_lon
    avg_lat = (flight_lat + airport_lat) / 2.0
    x_miles = lon_delta * 69.172 * math.cos(math.radians(avg_lat))
    y_miles = lat_delta * 69.0

    x_percent = 50 + (x_miles / radius_miles) * 40
    y_percent = 50 - (y_miles / radius_miles) * 40

    return {
        "x_percent": max(5, min(95, x_percent)),
        "y_percent": max(5, min(95, y_percent)),
        "distance_miles": round(math.hypot(x_miles, y_miles), 1),
    }


def classify_aircraft_type(category_id):
    if category_id is None:
        return "commercial"
    if 1 <= category_id <= 6:
        return "private"
    if category_id == 8:
        return "cargo"
    if category_id == 19:
        return "military"
    return "commercial"


def get_nearby_aircraft(airport_code, radius=25):
    airport = get_airport_info(airport_code)
    if not airport:
        return {"error": f"Airport '{airport_code.upper()}' could not be found in the database."}

    params = calculate_bounding_box(airport['lat'], airport['lon'], radius_miles=radius)
    url = "https://opensky-network.org/api/states/all"

    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Flask Backend Flight Tracker)'}
        response = requests.get(url, params=params, headers=headers, timeout=10)

        if response.status_code == 429:
            return {"error": "OpenSky API rate limit reached. Please wait a minute."}
        elif response.status_code != 200:
            return {"error": f"OpenSky API returned status code {response.status_code}"}

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
                
                # Fetch telemetry fields safely
                velocity_ms = flight[9]
                speed_knots = int(velocity_ms * 1.94384) if velocity_ms is not None else 0
                heading = int(flight[10]) if flight[10] is not None else 0
                category_id = flight[17] if len(flight) > 17 else None
                
                callsign = flight[1].strip() if flight[1] else "UNKNOWN"
                operator = resolve_operator(callsign)
                aircraft_type = classify_aircraft_type(category_id)

                aircraft_list.append({
                    "callsign": callsign,
                    "altitude": f"{int(flight[7] * 3.28084)} ft" if flight[7] is not None else "Ground / Unknown",
                    "on_ground": "Yes" if flight[8] else "No",
                    "speed": f"{speed_knots} kts",
                    "heading": heading,
                    "operator": operator,
                    "type": aircraft_type,
                    "x_percent": position["x_percent"],
                    "y_percent": position["y_percent"],
                    "distance_miles": position["distance_miles"],
                })

        return {
            "airport_name": airport['name'],
            "code": airport_code.upper(),
            "search_radius": radius,
            "aircraft_count": len(aircraft_list),
            "flights": aircraft_list
        }
    except requests.exceptions.RequestException as e:
        return {"error": f"Failed to connect to flight data stream: {str(e)}"}
    

@app.route("/", methods=["GET"])
def home():
    airport_query = request.args.get("airport")
    radius_query = request.args.get("radius", default=25, type=int)

    if not airport_query:
        return render_template("index.html")

    result = get_nearby_aircraft(airport_query, radius=radius_query)
    return render_template("index.html", **result)

if __name__ == "__main__":
    app.run(debug=True)
