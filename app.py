import sqlite3
import requests
from flask import Flask, render_template, request

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

def get_nearby_aircraft(airport_code, radius=25):
    airport = get_airport_info(airport_code)
    if not airport:
        return {"error": f"Airport '{airport_code.upper()}' could not be found in the database."}

    params = calculate_bounding_box(airport['lat'], airport['lon'], radius_miles=radius)

    # Request the OpenSky states API, not the OpenSky website homepage.
    url = "https://opensky-network.org/api/states/all"

    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Flask Backend Flight Tracker)'}

        # Optional: If you register an account on OpenSky to prevent rate-limiting,
        # add auth=('your_username', 'your_password') inside the requests.get parameters below
        response = requests.get(url, params=params, headers=headers, timeout=10)

        if response.status_code == 429:
            return {"error": "OpenSky API rate limit reached. Please wait a minute and try again."}
        elif response.status_code != 200:
            return {"error": f"OpenSky API returned status code {response.status_code}"}

        try:
            data = response.json()
        except ValueError:
            return {"error": "Received an unexpected non-JSON response from OpenSky. The server might be down or overloaded."}

        states = data.get("states", []) or []

        aircraft_list = []
        for flight in states:
            if len(flight) > 8:
                aircraft_list.append({
                    "callsign": flight[1].strip() if flight[1] else "UNKNOWN",
                    "altitude": f"{int(flight[7])}m" if flight[7] is not None else "Unknown",
                    "on_ground": "Yes" if flight[8] else "No"
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

# --- WEB ROUTE INTERFACE ---
@app.route("/", methods=["GET"])
def home():
    # Capture search fields from the URL parameters (?airport=HECA&radius=20)
    airport_query = request.args.get("airport")
    radius_query = request.args.get("radius", default=25, type=int)

    # Base page load (User hasn't searched anything yet)
    if not airport_query:
        return render_template("index.html")

    # Fetch data based on form submission variables
    result = get_nearby_aircraft(airport_query, radius=radius_query)

    # Note: If an "error" key exists in result, make sure your template displays it!
    return render_template("index.html", **result)


if __name__ == "__main__":
    # Start server locally on http://127.0.0.1:5000
    app.run(debug=True)
