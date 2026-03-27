import pandas as pd
import numpy as np
from datetime import datetime
import os
import random
import math
import sys

# Import config from existing file
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from generate_city_data import CITY_CONFIGS, create_road_segments, VEHICLE_TYPES
except ImportError:
    print("Cannot find generate_city_data.py")
    sys.exit(1)

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

def snap_to_closest_road(lat, lon, city_roads):
    best_dist = float("inf")
    best_road = None
    for road in city_roads:
        d = haversine(lat, lon, road["lat"], road["lon"])
        if d < best_dist:
            best_dist = d
            best_road = road
    return best_road

def preprocess_data(csv_path):
    print(f"Loading Kaggle dataset from {csv_path}...")
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"Error loading Kaggle dataset: {e}")
        return

    # To lower string columns for safe mapping
    df['city'] = df['city'].str.lower()
    df['weather'] = df['weather'].str.title()
    df['accident_severity'] = df['accident_severity'].str.title()

    # Map kaggle 'fatal' literally, and cap 'minor', 'major' to 'Minor', 'Severe' respectively
    # Severity Expected: "Minor", "Moderate", "Severe", "Fatal"
    severity_map = {
        'Minor': 'Minor',
        'Major': 'Severe',
        'Fatal': 'Fatal'
    }
    df['severity'] = df['accident_severity'].map(severity_map).fillna('Moderate')

    weather_map = {
        'Clear': 'Clear',
        'Rain': 'Rain',
        'Fog': 'Fog',
        'Heavy Rain': 'Heavy Rain'
    }
    df['weather'] = df['weather'].map(weather_map).fillna('Clear')

    supported_cities = list(CITY_CONFIGS.keys())
    
    for city_id in supported_cities:
        print(f"\n============================================================")
        print(f"Processing real-world data for {city_id.upper()}")
        print(f"============================================================")
        
        city_df = df[df['city'] == city_id].copy()
        print(f"Found {len(city_df)} accidents in {city_id.upper()}")
        
        if len(city_df) == 0:
            print("Skipping city due to no data.")
            continue
            
        dir_path = f"data/{city_id}"
        os.makedirs(dir_path, exist_ok=True)
        
        # 1. Generate Structural Road Segments (Map paths)
        seg_df = create_road_segments(city_id)
        seg_df.to_csv(f"{dir_path}/road_segments.csv", index=False)
        print(f"Generated base road segment polylines for map rendering")
        
        # 2. Map Accidents to expected columns
        processed_accidents = []
        city_roads = CITY_CONFIGS[city_id]['roads']
        
        for idx, row in city_df.iterrows():
            # Date/Time Parsing
            # Kaggle: date is YYYY-MM-DD, time is something like 5:00
            try:
                date_str = str(row['date'])
                time_str = str(row['time']).zfill(5) # pad "5:00" to "05:00"
                if len(time_str) < 5:
                    time_str = "00:00"
                dt_str = f"{date_str} {time_str}:00"
            except:
                dt_str = "2024-01-01 12:00:00"
                
            closest_road = snap_to_closest_road(row['latitude'], row['longitude'], city_roads)
            
            processed_accidents.append({
                "id": len(processed_accidents) + 1,
                "latitude": row['latitude'],
                "longitude": row['longitude'],
                "road_name": closest_road["name"],
                "severity": row['severity'],
                "date": date_str,
                "time": time_str,
                "datetime": dt_str,
                "weather": row['weather'],
                "vehicle_type": random.choice(VEHICLE_TYPES), # Synthesize since kaggle lacks it
                "road_risk_level": closest_road["risk"]
            })
            
        final_acc_df = pd.DataFrame(processed_accidents)
        final_acc_df.to_csv(f"{dir_path}/accidents.csv", index=False)
        print(f"Successfully snapped {len(final_acc_df)} real accidents to the road network")
        
        # Ensure json config exists
        for f in ['route_history.json', 'live_accidents.json']:
            p = f"{dir_path}/{f}"
            if not os.path.exists(p):
                with open(p, 'w') as jf: jf.write('[]')

if __name__ == "__main__":
    KAGGLE_CSV = r"C:\Users\Rasika\.cache\kagglehub\datasets\sehaj1104\indian-road-accident-dataset-20222025\versions\1\indian_roads_dataset.csv"
    if not os.path.exists(KAGGLE_CSV):
        print(f"Dataset not found at {KAGGLE_CSV}")
    else:
        preprocess_data(KAGGLE_CSV)
        print("\nAll cities parsed successfully.")
