import pandas as pd
import numpy as np
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split, KFold, cross_val_score
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import accuracy_score
import pickle, math, random, os, argparse
from collections import defaultdict

# ---------------------------------------------------------------------------
# Weather helpers (Ordinal mapping)
# ---------------------------------------------------------------------------
WEATHER_RISK_SCORE = {"Clear": 0, "Rain": 4, "Fog": 5, "Heavy Rain": 8}
WEATHER_RAIN_MM = {"Clear": 0.0, "Rain": 3.5, "Fog": 0.2, "Heavy Rain": 12.0}
WEATHER_HUMIDITY = {"Clear": 55, "Rain": 82, "Fog": 90, "Heavy Rain": 88}

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

def impute_weather_features(df):
    df = df.copy()
    df["weather_severity_score"] = df["weather"].map(WEATHER_RISK_SCORE).fillna(3)
    df["rain_mm"] = df["weather"].map(WEATHER_RAIN_MM).fillna(0.0) + np.random.normal(0, 0.8, len(df)).clip(-0.5)
    df["rain_mm"] = df["rain_mm"].clip(lower=0.0)
    df["humidity"] = df["weather"].map(WEATHER_HUMIDITY).fillna(60).astype(float) + np.random.normal(0, 4, len(df)).clip(-8, 8)
    df["humidity"] = df["humidity"].clip(0, 100)
    return df

def prepare_features(df):
    df = df.copy()
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["hour"] = df["datetime"].dt.hour
    df["day_of_week"] = df["datetime"].dt.dayofweek
    df["month"] = df["datetime"].dt.month
    df["is_rush_hour"] = df["hour"].apply(lambda h: 1 if (7<=h<=10) or (17<=h<=21) else 0)
    df["is_night"] = df["hour"].apply(lambda h: 1 if h>=22 or h<=5 else 0)
    df["is_weekend"] = df["day_of_week"].apply(lambda d: 1 if d>=5 else 0)
    sev_map = {"Minor": 15, "Moderate": 40, "Severe": 72, "Fatal": 95}
    df["risk_score"] = df["severity"].map(sev_map)
    return impute_weather_features(df)

def calculate_road_risk_scores(accidents_df, segments_df):
    SEV_WEIGHT = {"Minor":1, "Moderate":3, "Severe":7, "Fatal":15}
    SEV_SCORE  = {"Minor":1, "Moderate":2, "Severe":3, "Fatal":4}
    BASE_RISK  = {"low":12, "medium":30, "high":55}
    seg_mids = []
    for _, seg in segments_df.iterrows():
        seg_mids.append({"segment_id": seg["segment_id"], "road_name": seg["road_name"], 
                        "mid_lat": (seg["start_lat"]+seg["end_lat"])/2, "mid_lon": (seg["start_lon"]+seg["end_lon"])/2,
                        "risk_level": seg["risk_level"], "avg_traffic": seg["avg_traffic"]})
    seg_df = pd.DataFrame(seg_mids)
    stats = defaultdict(lambda: {"total_weight":0, "count":0, "severity_sum":0})
    for _, acc in accidents_df.iterrows():
        best_dist, best_sid = float("inf"), None
        for _, s in seg_df.iterrows():
            d = haversine(acc["latitude"], acc["longitude"], s["mid_lat"], s["mid_lon"])
            if d < best_dist: best_dist, best_sid = d, s["segment_id"]
        stats[best_sid]["total_weight"] += SEV_WEIGHT.get(acc["severity"],1)
        stats[best_sid]["count"] += 1
        stats[best_sid]["severity_sum"] += SEV_SCORE.get(acc["severity"],1)
    risk_scores = {}
    for _, seg in seg_df.iterrows():
        sid = seg["segment_id"]; s = stats.get(sid)
        if s and s["count"] > 0:
            raw = s["total_weight"] * (s["severity_sum"] / s["count"])
            score = min(100, 10 * math.log1p(raw))
        else: score = BASE_RISK.get(seg["risk_level"], 25)
        traffic_factor = min(1.3, 1.0 + (seg["avg_traffic"]-500)/15000)
        score = min(100, round(score * traffic_factor, 2))
        risk_scores[sid] = {"risk_score": score, "accident_count": s["count"] if s else 0, "road_name": seg["road_name"]}
    return risk_scores

def train_city_model(city_id):
    print(f"\n============================================================")
    print(f"Training {city_id.upper()} Model")
    print(f"============================================================")
    
    data_dir = f"data/{city_id}"
    model_dir = f"models/{city_id}"
    os.makedirs(model_dir, exist_ok=True)
    
    accidents_df = pd.read_csv(f"{data_dir}/accidents.csv")
    segments_df = pd.read_csv(f"{data_dir}/road_segments.csv")
    
    df = prepare_features(accidents_df)
    le_road = LabelEncoder(); le_vehicle = LabelEncoder()
    df["road_encoded"] = le_road.fit_transform(df["road_name"])
    df["vehicle_encoded"] = le_vehicle.fit_transform(df["vehicle_type"])
    risk_map = {"low":0, "medium":1, "high":2}
    df["road_risk_encoded"] = df["road_risk_level"].map(risk_map)

    feature_columns = ["hour", "day_of_week", "month", "is_rush_hour", "is_night", "is_weekend",
                      "weather_severity_score", "rain_mm", "humidity", "road_risk_encoded", "vehicle_encoded"]

    X = df[feature_columns]
    y_class = df["severity"].map({"Minor": 0, "Moderate": 1, "Severe": 1, "Fatal": 2}).fillna(0).astype(int)
    
    X_train, X_test, y_train, y_test = train_test_split(X, y_class, test_size=0.2, random_state=42)

    # Inject dummy rows so XGBClassifier ALWAYS outputs a shape-3 proba array for app.py
    if len(y_train.unique()) < 3:
        dummy_X = X_train.iloc[:3].copy()
        dummy_y = pd.Series([0, 1, 2], index=dummy_X.index)
        X_train = pd.concat([X_train, dummy_X])
        y_train = pd.concat([y_train, dummy_y])

    model = XGBClassifier(n_estimators=500, max_depth=6, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8, n_jobs=-1, random_state=42)
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    print(f"+ Test Accuracy: {accuracy_score(y_test, y_pred):.2f}")
    
    model_data = {
        "model": model, "le_road": le_road, "le_vehicle": le_vehicle, "feature_columns": feature_columns,
        "risk_map": risk_map, "model_type": "classifier", "weather_severity_score": WEATHER_RISK_SCORE,
        "weather_rain_mm": WEATHER_RAIN_MM, "weather_humidity": WEATHER_HUMIDITY
    }
    with open(f"{model_dir}/risk_model.pkl", "wb") as f: pickle.dump(model_data, f)
    
    risk_scores = calculate_road_risk_scores(accidents_df, segments_df)
    with open(f"{model_dir}/segment_risk_scores.pkl", "wb") as f: pickle.dump(risk_scores, f)
    print(f"+ Model & Risk Scores saved for {city_id}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--city', type=str)
    parser.add_argument('--all', action='store_true')
    args = parser.parse_args()
    
    cities = ['mumbai', 'pune', 'delhi', 'bangalore', 'chennai', 'kolkata', 'hyderabad', 'chandigarh']
    cities_to_train = [args.city] if args.city else (cities if args.all else [])
    
    if not cities_to_train:
        print("Please specify --city [city_id] or --all")
    else:
        for city in cities_to_train:
            train_city_model(city)
