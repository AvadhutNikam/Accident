import os
import pandas as pd
from datetime import datetime
import random
from accident_reporter import AccidentReporter
from train_city_models import train_city_model, haversine

CITIES = ['mumbai', 'pune', 'delhi', 'bangalore', 'chennai', 'kolkata', 'hyderabad', 'chandigarh']
CITIES_DATA = {
    'mumbai': [19.0760, 72.8777],
    'pune': [18.5204, 73.8567],
    'delhi': [28.6139, 77.2090],
    'bangalore': [12.9716, 77.5946],
    'chennai': [13.0827, 80.2707],
    'kolkata': [22.5726, 88.3639],
    'hyderabad': [17.3850, 78.4867],
    'chandigarh': [30.7333, 76.7794]
}

def get_nearest_city(lat, lon):
    best_dist = float('inf')
    best_city = 'mumbai'
    for city, coords in CITIES_DATA.items():
        d = haversine(lat, lon, coords[0], coords[1])
        if d < best_dist:
            best_dist = d
            best_city = city
    return best_city

def get_nearest_segment(lat, lon, segments_df):
    best_dist = float('inf')
    best_row = None
    for _, row in segments_df.iterrows():
        mid_lat = (row['start_lat'] + row['end_lat']) / 2
        mid_lon = (row['start_lon'] + row['end_lon']) / 2
        d = haversine(lat, lon, mid_lat, mid_lon)
        if d < best_dist:
            best_dist = d
            best_row = row
    return best_row

def run_pipeline():
    print("\n[ML-PIPELINE] Starting Continuous Learning Loop...")
    
    total_processed = 0
    for city in CITIES:
        db_path = f"data/{city}/accidents.db"
        if not os.path.exists(db_path):
            continue
            
        reporter = AccidentReporter(db_path=db_path)
        new_accidents = reporter.get_unprocessed_verified_accidents()
        
        if not new_accidents:
            continue
            
        print(f"[ML-PIPELINE] Detected {len(new_accidents)} new verified crowd-sourced report(s) for {city.upper()}.")
        
        acc_df = pd.read_csv(f"data/{city}/accidents.csv")
        seg_df = pd.read_csv(f"data/{city}/road_segments.csv")
        
        new_rows = []
        processed_ids = []
        max_id = int(acc_df['id'].max()) if 'id' in acc_df.columns and len(acc_df) > 0 else 0
        
        for acc in new_accidents:
            max_id += 1
            segment = get_nearest_segment(acc['latitude'], acc['longitude'], seg_df)
            dt = datetime.fromisoformat(acc['timestamp'])
            
            new_row = {
                'id': max_id,
                'latitude': acc['latitude'],
                'longitude': acc['longitude'],
                'road_name': segment['road_name'] if segment is not None else "Unknown Road",
                'severity': acc['severity'].capitalize(),
                'date': dt.strftime('%Y-%m-%d'),
                'time': dt.strftime('%H:%M'),
                'datetime': dt.strftime('%Y-%m-%d %H:%M:%S'),
                'weather': random.choice(['Clear', 'Fog', 'Rain']),
                'vehicle_type': random.choice(['Car', 'Bike', 'Auto', 'Bus', 'Truck']),
                'road_risk_level': segment['risk_level'] if segment is not None else "medium"
            }
            new_rows.append(new_row)
            processed_ids.append(acc['id'])
            
        new_df = pd.DataFrame(new_rows)
        acc_df = pd.concat([acc_df, new_df], ignore_index=True)
        acc_df.to_csv(f"data/{city}/accidents.csv", index=False)
        print(f"[ML-PIPELINE] Data permanently appended to {city.upper()}/accidents.csv")
        
        from train_gnn_models import train_city_gnn
        train_city_gnn(city)
        
        reporter.mark_accidents_processed(processed_ids)
        print(f"[ML-PIPELINE] Successfully marked {len(processed_ids)} entries as PROCESSED in {city.upper()} SQLite Tracker.")
        total_processed += len(processed_ids)
        
    if total_processed == 0:
        print("[ML-PIPELINE] No new verified accidents found across any city. Pipeline safely exiting.")
        return {"status": "success", "message": "No new data to process.", "count": 0}
        
    print("[ML-PIPELINE] Training job complete.\n")
    return {"status": "success", "message": f"Successfully processed {total_processed} entries and retrained affected models.", "count": total_processed}

if __name__ == "__main__":
    run_pipeline()
