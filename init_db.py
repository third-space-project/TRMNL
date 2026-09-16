import sqlite3
import pandas as pd

def build_airport_database():
    print("Step 1: Downloading latest global airport data from OurAirports...")
    # FIX: Point directly to the raw CSV data instead of the GitHub landing webpage
    csv_url = "https://raw.githubusercontent.com/davidmegginson/ourairports-data/refs/heads/main/airports.csv"
    
    try:
        # Read the CSV directly from the web
        df = pd.read_csv(csv_url)
    except Exception as e:
        print(f"Failed to download data: {e}")
        return

    print("🧹 Step 2: Filtering and cleaning columns...")
    
    columns_to_keep = ['ident', 'iata_code', 'name', 'type', 'latitude_deg', 'longitude_deg', 'elevation_ft']
    df_filtered = df[columns_to_keep].copy()

    df_filtered.to_csv('airports.csv', index=False)
    print("💾 Backup saved locally as 'airports.csv'")

    print("🗄️ Step 3: Connecting to SQLite and inserting records...")
    conn = sqlite3.connect('airports.db')
    
    df_filtered.to_sql('airports', conn, if_exists='replace', index=False)

    print("Step 4: Building database indexes for lightning-fast search...")
    cursor = conn.cursor()
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ident ON airports(ident);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_iata ON airports(iata_code);")
    
    conn.commit()
    conn.close()
    
    print("Success! 'airports.db' is ready to use with your tracking script.")

if __name__ == "__main__":
    build_airport_database()
