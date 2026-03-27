import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random
import os
import argparse

CITY_CONFIGS = {
    'mumbai': {
        'name': 'Mumbai',
        'roads': [
            {"name": "Western Express Highway", "lat": 19.1136, "lon": 72.8697, "risk": "high"},
            {"name": "Eastern Express Highway", "lat": 19.1076, "lon": 72.8856, "risk": "high"},
            {"name": "Sion-Panvel Highway", "lat": 19.0433, "lon": 72.9265, "risk": "medium"},
            {"name": "LBS Marg", "lat": 19.0728, "lon": 72.8987, "risk": "medium"},
            {"name": "SV Road Andheri", "lat": 19.1136, "lon": 72.8347, "risk": "medium"},
            {"name": "Linking Road Bandra", "lat": 19.0596, "lon": 72.8295, "risk": "low"},
            {"name": "Marine Drive", "lat": 18.9432, "lon": 72.8236, "risk": "low"},
            {"name": "Worli Sea Link", "lat": 19.0176, "lon": 72.8125, "risk": "medium"},
            {"name": "Jogeshwari-Vikhroli Link Road", "lat": 19.1258, "lon": 72.9167, "risk": "high"},
            {"name": "Ghodbunder Road", "lat": 19.2183, "lon": 72.9781, "risk": "high"}
        ]
    },
    'pune': {
        'name': 'Pune',
        'roads': [
            {"name": "Shivajinagar Road", "lat": 18.5304, "lon": 73.8467, "risk": "medium"},
            {"name": "Koregaon Park Road", "lat": 18.5362, "lon": 73.8958, "risk": "low"},
            {"name": "Viman Nagar Road", "lat": 18.5679, "lon": 73.9143, "risk": "medium"},
            {"name": "Hinjewadi IT Park Road", "lat": 18.5912, "lon": 73.7389, "risk": "high"},
            {"name": "Kothrud Road", "lat": 18.5074, "lon": 73.8077, "risk": "medium"},
            {"name": "Hadapsar Bypass", "lat": 18.5089, "lon": 73.9260, "risk": "high"},
            {"name": "Pimpri-Chinchwad Link", "lat": 18.6298, "lon": 73.8149, "risk": "high"},
            {"name": "Wakad Highway", "lat": 18.5978, "lon": 73.7636, "risk": "high"},
            {"name": "Baner Road", "lat": 18.5593, "lon": 73.7815, "risk": "medium"},
            {"name": "Deccan Road", "lat": 18.5167, "lon": 73.8410, "risk": "low"}
        ]
    },
    'delhi': {
        'name': 'Delhi',
        'roads': [
            {"name": "Outer Ring Road", "lat": 28.7041, "lon": 77.1025, "risk": "high"},
            {"name": "Ring Road", "lat": 28.6315, "lon": 77.2167, "risk": "high"},
            {"name": "NH-44", "lat": 28.7496, "lon": 77.0670, "risk": "high"},
            {"name": "Mathura Road", "lat": 28.5244, "lon": 77.2066, "risk": "medium"},
            {"name": "MG Road", "lat": 28.4595, "lon": 77.0266, "risk": "medium"},
            {"name": "DND Flyway", "lat": 28.5748, "lon": 77.3060, "risk": "medium"},
            {"name": "Rohtak Road", "lat": 28.6814, "lon": 77.1215, "risk": "high"},
            {"name": "G T Road", "lat": 28.6506, "lon": 77.2303, "risk": "high"},
            {"name": "Dwarka Expressway", "lat": 28.5921, "lon": 77.0460, "risk": "medium"},
            {"name": "Lodhi Road", "lat": 28.5877, "lon": 77.2430, "risk": "low"}
        ]
    },
    'bangalore': {
        'name': 'Bangalore',
        'roads': [
            {"name": "Old Madras Road", "lat": 12.9762, "lon": 77.6033, "risk": "high"},
            {"name": "Hosur Road", "lat": 12.8456, "lon": 77.6603, "risk": "high"},
            {"name": "Outer Ring Road", "lat": 12.9121, "lon": 77.6446, "risk": "high"},
            {"name": "Sarjapur Road", "lat": 12.9165, "lon": 77.6101, "risk": "medium"},
            {"name": "Bannerghatta Road", "lat": 12.9250, "lon": 77.5937, "risk": "medium"},
            {"name": "Airport Road", "lat": 13.1007, "lon": 77.5963, "risk": "medium"},
            {"name": "Whitefield Main Road", "lat": 12.9698, "lon": 77.7499, "risk": "high"},
            {"name": "Koramangala 80ft Road", "lat": 12.9352, "lon": 77.6245, "risk": "low"},
            {"name": "Indiranagar 100ft Road", "lat": 12.9784, "lon": 77.6408, "risk": "low"},
            {"name": "Marathahalli Bridge Road", "lat": 12.9591, "lon": 77.7012, "risk": "high"}
        ]
    },
    'chennai': {
        'name': 'Chennai',
        'roads': [
            {"name": "Anna Salai", "lat": 13.0604, "lon": 80.2608, "risk": "high"},
            {"name": "OMR", "lat": 12.9229, "lon": 80.2300, "risk": "medium"},
            {"name": "ECR", "lat": 12.8228, "lon": 80.2241, "risk": "high"},
             {"name": "Mount Road", "lat": 13.0069, "lon": 80.2201, "risk": "medium"}
        ]
    },
    'kolkata': {
        'name': 'Kolkata',
        'roads': [
            {"name": "Park Street", "lat": 22.5516, "lon": 88.3519, "risk": "medium"},
            {"name": "AJC Bose Road", "lat": 22.5401, "lon": 88.3533, "risk": "high"},
            {"name": "EM Bypass", "lat": 22.5694, "lon": 88.4116, "risk": "high"}
        ]
    },
    'hyderabad': {
        'name': 'Hyderabad',
        'roads': [
            {"name": "Necklace Road", "lat": 17.4162, "lon": 78.4716, "risk": "low"},
            {"name": "ORR", "lat": 17.4312, "lon": 78.3364, "risk": "high"},
            {"name": "Banjara Hills Rd 1", "lat": 17.4156, "lon": 78.4357, "risk": "medium"}
        ]
    },
    'chandigarh': {
        'name': 'Chandigarh',
        'roads': [
            {"name": "Madhya Marg", "lat": 30.7333, "lon": 76.7794, "risk": "low"},
            {"name": "Dakshin Marg", "lat": 30.7139, "lon": 76.7667, "risk": "medium"}
        ]
    }
}

SEVERITY_LEVELS = ["Minor", "Moderate", "Severe", "Fatal"]
WEATHER_CONDITIONS = ["Clear", "Rain", "Fog", "Heavy Rain"]
VEHICLE_TYPES = ["Car", "Bike", "Truck", "Bus", "Auto"]

def generate_accident_data(city_id, num_accidents=1000):
    city = CITY_CONFIGS[city_id]
    accidents = []
    start_date = datetime.now() - timedelta(days=3*365)
    
    for i in range(num_accidents):
        road = random.choice(city['roads'])
        lat = road["lat"] + random.uniform(-0.01, 0.01)
        lon = road["lon"] + random.uniform(-0.01, 0.01)
        random_days = random.randint(0, 3*365)
        accident_date = start_date + timedelta(days=random_days)
        hour = random.choices(range(24), weights=[2,1,1,1,1,3,5,8,8,7,4,3,3,3,3,4,5,8,9,8,6,4,3,2], k=1)[0]
        accident_time = accident_date.replace(hour=hour, minute=random.randint(0, 59))
        weather = random.choices(WEATHER_CONDITIONS, weights=[60, 25, 10, 5], k=1)[0]
        severity_weights = {"Minor": 50, "Moderate": 30, "Severe": 15, "Fatal": 5}
        if weather in ["Rain", "Heavy Rain", "Fog"]:
            severity_weights = {"Minor": 35, "Moderate": 35, "Severe": 20, "Fatal": 10}
        severity = random.choices(SEVERITY_LEVELS, weights=list(severity_weights.values()), k=1)[0]
        
        accidents.append({
            "id": i + 1,
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
            "road_name": road["name"],
            "severity": severity,
            "date": accident_date.strftime("%Y-%m-%d"),
            "time": accident_time.strftime("%H:%M"),
            "datetime": accident_time.strftime("%Y-%m-%d %H:%M:%S"),
            "weather": weather,
            "vehicle_type": random.choice(VEHICLE_TYPES),
            "road_risk_level": road["risk"]
        })
    return pd.DataFrame(accidents)

def create_road_segments(city_id):
    city = CITY_CONFIGS[city_id]
    segments = []
    for road in city['roads']:
        num_segments = random.randint(8, 12)
        for seg in range(num_segments):
            segments.append({
                "segment_id": f"{city_id}_{road['name'].replace(' ', '_')}_{seg}",
                "road_name": road["name"],
                "start_lat": road["lat"] + seg * 0.002,
                "start_lon": road["lon"] + seg * 0.002,
                "end_lat": road["lat"] + (seg + 1) * 0.002,
                "end_lon": road["lon"] + (seg + 1) * 0.002,
                "risk_level": road["risk"],
                "avg_traffic": random.randint(500, 5000),
                "speed_limit": random.choice([40, 50, 60, 80]),
                "lanes": random.choice([2, 3, 4, 6])
            })
    return pd.DataFrame(segments)

def process_city(city_id):
    print(f"============================================================")
    print(f"Generating data for {city_id.upper()}")
    print(f"============================================================")
    
    dir_path = f"data/{city_id}"
    os.makedirs(dir_path, exist_ok=True)
    
    acc_df = generate_accident_data(city_id)
    acc_df.to_csv(f"{dir_path}/accidents.csv", index=False)
    print(f"✅ Generated {len(acc_df)} accidents for {city_id}")
    
    seg_df = create_road_segments(city_id)
    seg_df.to_csv(f"{dir_path}/road_segments.csv", index=False)
    print(f"✅ Generated {len(seg_df)} road segments for {city_id}")
    
    # Ensure JSON files exist
    for f in ['route_history.json', 'live_accidents.json']:
        p = f"{dir_path}/{f}"
        if not os.path.exists(p):
            with open(p, 'w') as jf: jf.write('[]')
            print(f"✅ Created {f}")

if __name__ == "__main__":
    print("\n============================================================")
    print("                SAFE ROUTE SYSTEM UPDATED                 ")
    print("============================================================")
    print("Notice: The synthetic data generation pipeline has been ")
    print("deprecated. The True Kaggle real-world accident dataset ")
    print("is now natively powering this project (see preprocess_kaggle_data.py).")
    print("\nTo avoid replacing the authentic historical training data ")
    print("with randomized mock data, this execution block is disabled.")
    print("============================================================\n")
