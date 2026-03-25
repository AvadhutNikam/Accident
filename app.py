import sqlite3
from flask import Flask, render_template, request, jsonify
import pickle
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import random
import math
import os
import json
import uuid

app = Flask(__name__)

from accident_reporter import AccidentReporter
from route_history import RouteHistoryManager
from weather_service import WeatherService
from traffic_integration import TrafficIntegration

weather_service = WeatherService()

# ═══════════════════════════════════════════════════════════════════════
# MULTI-CITY CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════

CITIES_DATA = {
    'mumbai': {
        'name': 'Mumbai',
        'center': [19.0760, 72.8777],
        'zoom': 11,
        'locations': {
            "Bandra": [19.0596, 72.8295], "Andheri": [19.1136, 72.8697], "Powai": [19.1197, 72.9067], "Worli": [19.0176, 72.8125],
            "Marine Drive": [18.9432, 72.8236], "BKC": [19.0653, 72.8684], "Goregaon": [19.1663, 72.8526], "Thane": [19.1972, 73.0032],
            "Navi Mumbai": [19.0330, 73.0297], "Malad": [19.1867, 72.8483], "Borivali": [19.2304, 72.8571], "Dadar": [19.0176, 72.8479],
            "Churchgate": [18.9322, 72.8264], "CST": [18.9398, 72.8355], "Lower Parel": [18.9968, 72.8265], "Kurla": [19.0728, 72.8987],
            "Ghatkopar": [19.0860, 72.9081], "Mulund": [19.1726, 72.9586], "Juhu": [19.0969, 72.8265], "Nariman Point": [18.9256, 72.8235]
        }
    },
    'pune': {
        'name': 'Pune',
        'center': [18.5204, 73.8567],
        'zoom': 12,
        'locations': {
            "Shivajinagar": [18.5304, 73.8467], "Koregaon Park": [18.5362, 73.8958], "Viman Nagar": [18.5679, 73.9143],
            "Hinjewadi": [18.5912, 73.7389], "Kothrud": [18.5074, 73.8077], "Hadapsar": [18.5089, 73.9260],
            "Pimpri": [18.6298, 73.8149], "Wakad": [18.5978, 73.7636], "Baner": [18.5593, 73.7815], "Deccan": [18.5167, 73.8410]
        }
    },
    'delhi': {
        'name': 'Delhi',
        'center': [28.7041, 77.1025],
        'zoom': 11,
        'locations': {
            "Connaught Place": [28.6315, 77.2167], "Karol Bagh": [28.6519, 77.1903], "Dwarka": [28.5921, 77.0460],
            "Rohini": [28.7496, 77.0670], "Saket": [28.5244, 77.2066], "Nehru Place": [28.5494, 77.2501],
            "Chandni Chowk": [28.6506, 77.2303], "Lajpat Nagar": [28.5677, 77.2430], "Rajouri Garden": [28.6414, 77.1215],
            "Noida City Centre": [28.5748, 77.3560]
        }
    },
    'bangalore': {
        'name': 'Bangalore',
        'center': [12.9716, 77.5946],
        'zoom': 11,
        'locations': {
            "MG Road": [12.9762, 77.6033], "Koramangala": [12.9352, 77.6245], "Whitefield": [12.9698, 77.7499],
            "Electronic City": [12.8456, 77.6603], "Indiranagar": [12.9784, 77.6408], "HSR Layout": [12.9121, 77.6446],
            "Marathahalli": [12.9591, 77.7012], "Jayanagar": [12.9250, 77.5937], "Yelahanka": [13.1007, 77.5963],
            "BTM Layout": [12.9165, 77.6101]
        }
    }
}

# Backward compatibility
MUMBAI_LOCATIONS = CITIES_DATA['mumbai']['locations']

# Get Google Maps API Key from environment or placeholder
GMAPS_API_KEY = os.environ.get('GOOGLE_MAPS_API_KEY')
traffic_client = TrafficIntegration(api_key=GMAPS_API_KEY) if GMAPS_API_KEY else None

# ═══════════════════════════════════════════════════════════════════════
# CITY-SPECIFIC MODEL LOADING
# ═══════════════════════════════════════════════════════════════════════

city_models_cache = {}

def load_city_model(city_id):
    if city_id in city_models_cache:
        return city_models_cache[city_id]
    
    data_path = f'data/{city_id}'
    models_path = f'models/{city_id}'
    
    if not os.path.exists(data_path) or not os.path.exists(models_path):
        raise ValueError(f"No data/models available for city: {city_id}")
    
    with open(f'{models_path}/risk_model.pkl', 'rb') as f:
        model_data = pickle.load(f)
    
    segments_df = pd.read_csv(f'{data_path}/road_segments.csv')
    
    with open(f'{models_path}/segment_risk_scores.pkl', 'rb') as f:
        segment_risk_scores = pickle.load(f)
    
    history_mgr = RouteHistoryManager(storage_path=f'{data_path}/route_history.json')
    
    
    accident_rep = AccidentReporter(db_path=f'{data_path}/accidents.db')
    
    result = (model_data, segments_df, segment_risk_scores, history_mgr, accident_rep)
    city_models_cache[city_id] = result
    app.logger.info(f"✅ Loaded {city_id} model: {len(segments_df)} segments")
    return result

# ═══════════════════════════════════════════════════════════════════════
# VEHICLE & ROUTE LOGIC
# ═══════════════════════════════════════════════════════════════════════
VEHICLE_TYPES = {
    'car': {'name': 'Car', 'icon': '🚗', 'risk_multiplier': 1.0, 'speed_factor': 1.0},
    'bike': {'name': 'Motorcycle', 'icon': '🏍️', 'risk_multiplier': 1.8, 'speed_factor': 0.85},
    'auto': {'name': 'Auto Rickshaw', 'icon': '🛺', 'risk_multiplier': 1.5, 'speed_factor': 0.75},
    'bus': {'name': 'Bus', 'icon': '🚌', 'risk_multiplier': 1.2, 'speed_factor': 0.80},
    'truck': {'name': 'Truck', 'icon': '🚚', 'risk_multiplier': 1.3, 'speed_factor': 0.70}
}

def get_vehicle_multiplier(vehicle_type: str) -> dict:
    vehicle_type = vehicle_type.lower()
    if vehicle_type not in VEHICLE_TYPES: vehicle_type = 'car'
    vehicle = VEHICLE_TYPES[vehicle_type]
    return {'vehicle_type': vehicle_type, 'vehicle_name': vehicle['name'], 'vehicle_icon': vehicle['icon'], 'combined_multiplier': vehicle['risk_multiplier'], 'speed_factor': vehicle['speed_factor']}

# Default Mumbai data for backward compatibility or initial load
try:
    load_city_model('mumbai')
except Exception as e:
    app.logger.error(f"Failed to pre-load Mumbai model: {e}")

MUMBAI_LOCATIONS = {
    "Bandra": [19.0596, 72.8295], "Andheri": [19.1136, 72.8697], "Powai": [19.1197, 72.9067], "Worli": [19.0176, 72.8125],
    "Marine Drive": [18.9432, 72.8236], "BKC": [19.0653, 72.8684], "Goregaon": [19.1663, 72.8526], "Thane": [19.1972, 73.0032],
    "Navi Mumbai": [19.0330, 73.0297], "Malad": [19.1867, 72.8483], "Borivali": [19.2304, 72.8571], "Dadar": [19.0176, 72.8479],
    "Churchgate": [18.9322, 72.8264], "CST": [18.9398, 72.8355], "Lower Parel": [18.9968, 72.8265], "Kurla": [19.0728, 72.8987],
    "Ghatkopar": [19.0860, 72.9081], "Mulund": [19.1726, 72.9586], "Juhu": [19.0969, 72.8265], "Nariman Point": [18.9256, 72.8235]
}

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))



def generate_route_waypoints(start, end, route_type='direct'):
    start_lat, start_lon = start
    end_lat, end_lon = end
    waypoints = [[start_lat, start_lon]]
    if route_type == 'direct':
        for i in range(1, 5): waypoints.append([start_lat+(end_lat-start_lat)*(i/5), start_lon+(end_lon-start_lon)*(i/5)])
    elif route_type == 'highway':
        mid_lat, mid_lon = (start_lat+end_lat)/2 + random.uniform(-0.01, 0.01), (start_lon+end_lon)/2 + random.uniform(-0.01, 0.01)
        for i in range(1, 3): waypoints.append([start_lat+(mid_lat-start_lat)*(i/3), start_lon+(mid_lon-start_lon)*(i/3)])
        waypoints.append([mid_lat, mid_lon])
        for i in range(1, 3): waypoints.append([mid_lat+(end_lat-mid_lat)*(i/3), mid_lon+(end_lon-mid_lon)*(i/3)])
    elif route_type == 'scenic':
        offset = 0.015
        mid_lat, mid_lon = (start_lat+end_lat)/2 + offset, (start_lon+end_lon)/2 - offset
        for i in range(1, 4): waypoints.append([start_lat+(mid_lat-start_lat)*(i/4), start_lon+(mid_lon-start_lon)*(i/4)])
        waypoints.append([mid_lat, mid_lon])
        for i in range(1, 4): waypoints.append([mid_lat+(end_lat-mid_lat)*(i/4), mid_lon+(end_lon-mid_lon)*(i/4)])
    waypoints.append([end_lat, end_lon])
    return waypoints

def calculate_route_risk(waypoints, vehicle_type="car", city_id='mumbai'):
    """Calculate route risk using city-specific data."""
    try:
        model_data, segments_df, segment_risk_scores, history_mgr, accident_reporter = load_city_model(city_id)
    except Exception as e:
        app.logger.error(f"Error loading city model for {city_id}: {e}")
        return {'error': str(e)}

    accident_mult = accident_reporter.get_accident_impact_multiplier(waypoints)
    vehicle_info = get_vehicle_multiplier(vehicle_type)
    vehicle_mult = vehicle_info['combined_multiplier']
    
    # Weather multiplier
    weather_data = weather_service.get_current_weather()
    weather_weights = {'Clear': 1.0, 'Rain': 1.25, 'Fog': 1.35, 'Heavy Rain': 1.6}
    weather_mult = weather_weights.get(weather_data['weather_category'], 1.0)
    
    combined_mult = accident_mult * vehicle_mult * weather_mult
    total_risk, total_dist, risk_details = 0.0, 0.0, []

    for i in range(len(waypoints) - 1):
        lat1, lon1 = waypoints[i]
        lat2, lon2 = waypoints[i+1]
        leg_mid_lat, leg_mid_lon = (lat1+lat2)/2, (lon1+lon2)/2
        leg_dist = haversine_distance(lat1, lon1, lat2, lon2) or 0.001
        min_d, nearest = float('inf'), None
        
        for _, seg in segments_df.iterrows():
            sm_lat, sm_lon = (seg['start_lat']+seg['end_lat'])/2, (seg['start_lon']+seg['end_lon'])/2
            d = haversine_distance(leg_mid_lat, leg_mid_lon, sm_lat, sm_lon)
            if d < min_d: min_d, nearest = d, seg

        if nearest is not None:
            base_risk = segment_risk_scores.get(nearest['segment_id'], {}).get('risk_score', 40)
            adjusted_risk = min(100, base_risk * combined_mult)
            total_risk += adjusted_risk * leg_dist
            risk_details.append({'road': nearest['road_name'], 'risk': round(adjusted_risk, 2)})
        else:
            total_risk += 40 * combined_mult * leg_dist
        total_dist += leg_dist

    avg_risk = total_risk / max(total_dist, 0.001)
    return {
        'risk_score': round(avg_risk, 2), 
        'accident_multiplier': accident_mult, 
        'vehicle_multiplier': vehicle_mult, 
        'weather_multiplier': weather_mult,
        'weather_data': weather_data,
        'vehicle_info': vehicle_info, 
        'combined_multiplier': round(combined_mult, 2), 
        'risk_details': risk_details
    }

def predict_risk_for_hour(base_risk_score, hour_offset, vehicle_type, road_risk_encoded, city_id='mumbai'):
    """Predicts a risk score for a future hour using the city-specific ML model."""
    try:
        model_data, segments_df, segment_risk_scores, history_mgr, accident_reporter = load_city_model(city_id)
    except Exception as e:
        return base_risk_score
    
    if not model_data:
        return base_risk_score
    
    now = datetime.now()
    future_time = now + timedelta(hours=hour_offset)
    h = future_time.hour
    dow = future_time.weekday()
    month = future_time.month
    
    is_rush = 1 if (7<=h<=10) or (17<=h<=21) else 0
    is_night = 1 if h>=22 or h<=5 else 0
    is_weekend = 1 if dow>=5 else 0
    
    weather_data = weather_service.get_current_weather()
    w_sev = model_data['weather_severity_score'].get(weather_data['weather_category'], 3)
    w_rain = weather_data.get('rain_mm', 0.0)
    w_hum = weather_data.get('humidity', 60.0)
    
    v_encoded = model_data['le_vehicle'].transform([vehicle_type])[0] if vehicle_type in model_data['le_vehicle'].classes_ else 0
    
    features = [[
        h, dow, month, is_rush, is_night, is_weekend,
        w_sev, w_rain, w_hum, road_risk_encoded, v_encoded
    ]]
    
    predicted_risk = model_data['model'].predict(features)[0]
    multiplier = predicted_risk / 40.0
    
    return round(min(100, base_risk_score * multiplier), 2)

def get_route_metadata(waypoints, risk_score, vehicle_type="car"):
    total_distance = sum(haversine_distance(waypoints[i][0], waypoints[i][1], waypoints[i+1][0], waypoints[i+1][1]) for i in range(len(waypoints)-1))
    base_time_minutes = int((total_distance / 30) * 60)
    speed_factor = VEHICLE_TYPES.get(vehicle_type.lower(), VEHICLE_TYPES['car'])['speed_factor']
    time_minutes = int(base_time_minutes / speed_factor)
    if risk_score > 60: time_minutes = int(time_minutes * 1.15)
    return {'distance_km': round(total_distance, 2), 'time_minutes': time_minutes}

# ═══════════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════
@app.route('/')
def index():
    return render_template('index.html', locations=MUMBAI_LOCATIONS, preloaded_route=None)

@app.route('/api/cities', methods=['GET'])
def get_cities():
    """Get list of available cities."""
    return jsonify({
        'success': True,
        'cities': [
            {
                'id': city_id,
                'name': data['name'],
                'center': data['center'],
                'zoom': data['zoom']
            }
            for city_id, data in CITIES_DATA.items()
        ]
    })

@app.route('/api/locations', methods=['GET'])
def get_locations():
    """Get locations for a specific city."""
    city_id = request.args.get('city', 'mumbai')
    if city_id not in CITIES_DATA:
        return jsonify({'error': 'City not found'}), 404
    city_data = CITIES_DATA[city_id]
    return jsonify({
        'success': True,
        'city_id': city_id,
        'city_name': city_data['name'],
        'center': city_data['center'],
        'zoom': city_data['zoom'],
        'locations': city_data['locations']
    })

def get_coords(location, city_id='mumbai'):
    """Extracts [lat, lng] from location name, dict, or list for a specific city."""
    if isinstance(location, dict):
        return [location.get('lat'), location.get('lng')]
    
    city_locations = CITIES_DATA.get(city_id, {}).get('locations', {})
    if isinstance(location, str) and location in city_locations:
        return city_locations[location]
        
    if isinstance(location, (list, tuple)) and len(location) == 2:
        return list(location)
    return None

@app.route('/api/routes', methods=['POST'])
def get_safe_routes():
    data = request.get_json()
    start_input = data.get('start')
    end_input = data.get('end')
    city_id = data.get('city', 'mumbai')
    vehicle_type = data.get('vehicle_type', 'car')
    
    # Load city data
    try:
        model_data, segments_df, segment_risk_scores, history_mgr, accident_reporter = load_city_model(city_id)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

    # Standardize locations
    start_coords = get_coords(start_input, city_id)
    end_coords = get_coords(end_input, city_id)
    
    
    start_loc = start_input if isinstance(start_input, str) else start_coords
    end_loc = end_input if isinstance(end_input, str) else end_coords

    routes = []
    
    
    if traffic_client and GMAPS_API_KEY and start_loc and end_loc:
        traffic_result = traffic_client.get_route_with_traffic(start_loc, end_loc)
        if traffic_result.get('success'):
            for idx, r in enumerate(traffic_result['routes']):
                
                sc = start_coords or [19.05, 72.82]
                ec = end_coords or [19.06, 72.86]
                wp = generate_route_waypoints(sc, ec)
                
                risk_result = calculate_route_risk(wp, vehicle_type, city_id)
                
                routes.append({
                    'id': idx + 1,
                    'name': f"Route {idx + 1}: {r['summary']}",
                    'waypoints': wp,
                    'risk_score': risk_result['risk_score'],
                    'risk_level': 'low' if risk_result['risk_score'] < 35 else ('medium' if risk_result['risk_score'] < 60 else 'high'),
                    'distance_km': round(r['distance_km'], 2),
                    'time_minutes': int(r['traffic_duration_min']),
                    'traffic_delay': round(r['traffic_delay_min'], 1),
                    'risk_details': risk_result['risk_details'][:5],
                    'weather_data': risk_result['weather_data']
                })

    # Fallback to simulator if no API key or API call failed
    if not routes:
        if not start_coords or not end_coords:
            missing = []
            if not start_coords: missing.append(f"'{start_input}'")
            if not end_coords: missing.append(f"'{end_input}'")
            return jsonify({'error': f"Location(s) not found in {city_id} database: {', '.join(missing)}."}), 400
            
        for route_type, route_name in [('direct','Direct Route'),('highway','Via Highway'),('scenic','Scenic Route')]:
            wp = generate_route_waypoints(start_coords, end_coords, route_type)
            risk_result = calculate_route_risk(wp, vehicle_type, city_id)
            meta = get_route_metadata(wp, risk_result['risk_score'], vehicle_type)
            route_accidents = accident_reporter.get_accidents_on_route(wp, buffer_km=0.5)
            
            traffic_delay = 0
            if risk_result['risk_score'] > 50:
                traffic_delay = random.randint(5, 15)
            elif risk_result['risk_score'] > 30:
                traffic_delay = random.randint(1, 4)
            
            routes.append({
                'id': len(routes)+1, 'name': route_name, 'waypoints': wp, 'risk_score': risk_result['risk_score'],
                'risk_level': 'low' if risk_result['risk_score']<35 else ('medium' if risk_result['risk_score']<60 else 'high'),
                'distance_km': meta['distance_km'], 'time_minutes': meta['time_minutes'] + traffic_delay, 
                'traffic_delay': traffic_delay,
                'risk_details': risk_result['risk_details'][:5],
                'vehicle_info': risk_result['vehicle_info'], 
                'accidents_on_route': len(route_accidents),
                'weather_data': risk_result['weather_data']
            })

    routes.sort(key=lambda x: x['risk_score'])
    if routes: routes[0]['recommended'] = True
    return jsonify({
        'start': start_input if isinstance(start_input, str) else "Custom Location", 
        'end': end_input if isinstance(end_input, str) else "Custom Location", 
        'city': city_id,
        'city_name': CITIES_DATA.get(city_id, {}).get('name', 'Unknown'),
        'vehicle_type': vehicle_type, 
        'routes': routes, 
        'active_accidents_count': len(accident_reporter.get_active_accidents())
    })

@app.route('/api/time-risk', methods=['POST'])
def get_time_risk_forecast():
    data = request.get_json()
    start_input, end_input = data.get('start'), data.get('end')
    city_id = data.get('city', 'mumbai')
    vehicle_type = data.get('vehicle_type', 'car')
    
    try:
        model_data, segments_df, segment_risk_scores, history_mgr, accident_reporter = load_city_model(city_id)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

    start_coords = get_coords(start_input, city_id)
    end_coords = get_coords(end_input, city_id)
    
    if not start_coords or not end_coords:
        return jsonify({'error': 'Invalid locations'}), 400
        
    # Get base risk for direct route as baseline
    wp = generate_route_waypoints(start_coords, end_coords, 'direct')
    base_result = calculate_route_risk(wp, vehicle_type, city_id)
    base_score = base_result.get('risk_score', 40)
    
    
    road_risk_encoded = 1 # Medium baseline
    
    predictions = []
    now = datetime.now()
    
    for i in range(13): # 0 to 12 hours
        future_time = now + timedelta(hours=i)
        pred_score = predict_risk_for_hour(base_score, i, vehicle_type, road_risk_encoded, city_id)
        predictions.append({
            'hour': future_time.strftime('%I %p'),
            'offset': i,
            'risk_score': pred_score
        })
        
    # Find optimal time
    optimal = min(predictions, key=lambda x: x['risk_score'])
    
    return jsonify({
        'predictions': predictions,
        'optimal_time': optimal,
        'current_risk': base_score
    })

@app.route('/api/heatmap-data')
def get_heatmap_data():
    """Returns all road segments with their coordinates and risk scores for a city."""
    city_id = request.args.get('city', 'mumbai')
    try:
        model_data, segments_df, segment_risk_scores, history_mgr, accident_reporter = load_city_model(city_id)
        data = []
        for _, row in segments_df.iterrows():
            sid = row['segment_id']
            risk_info = segment_risk_scores.get(sid, {})
            score = risk_info.get('risk_score', 30)
            data.append({
                'id': sid,
                'name': row['road_name'],
                'coords': [[row['start_lat'], row['start_lon']], [row['end_lat'], row['end_lon']]],
                'risk_score': score
            })
        return jsonify({'success': True, 'segments': data, 'city': city_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/accidents/report', methods=['POST'])
def report_accident():
    data = request.get_json()
    city_id = data.get('city', 'mumbai')
    if not data.get('latitude') or not data.get('longitude'): 
        return jsonify({'success': False, 'error': 'Location required'}), 400
    try:
        _, _, _, _, accident_reporter = load_city_model(city_id)
        return jsonify(accident_reporter.report_accident(data.get('latitude'), data.get('longitude'), data.get('severity', 'moderate'), data.get('description', '')))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/accidents/active', methods=['GET'])
def get_active_accidents():
    city_id = request.args.get('city', 'mumbai')
    try:
        _, _, _, _, accident_reporter = load_city_model(city_id)
        accs = accident_reporter.get_active_accidents()
        return jsonify({'success': True, 'accidents': accs, 'count': len(accs), 'city': city_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/accidents/vote', methods=['POST'])
def vote_accident():
    data = request.get_json()
    city_id = data.get('city', 'mumbai')
    if not data.get('accident_id') or data.get('vote_type') not in ['up', 'down']: 
        return jsonify({'success': False, 'error': 'Invalid vote'}), 400
    try:
        _, _, _, _, accident_reporter = load_city_model(city_id)
        return jsonify(accident_reporter.vote_accident(data.get('accident_id'), data.get('vote_type')))
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ═══════════════════════════════════════════════════════════════════════
# DATABASE HELPERS
# ═══════════════════════════════════════════════════════════════════════
DB_PATH = 'data/mumbai_safe_route.db'

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/api/favorites', methods=['GET', 'POST'])
def manage_favorites():
    conn = get_db_connection()
    if request.method == 'POST':
        favorites_data = request.json.get('favorites', [])
        cursor = conn.cursor()
        cursor.execute('DELETE FROM favorites')
        for fav in favorites_data:
            cursor.execute('INSERT INTO favorites (id, name, locationName) VALUES (?, ?, ?)',
                         (fav['id'], fav['name'], fav['locationName']))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "favorites": favorites_data})
    else:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM favorites')
        rows = cursor.fetchall()
        favorites = [dict(row) for row in rows]
        if not favorites:
            favorites = [{'id': 'home', 'name': '🏠 Home', 'locationName': 'Bandra'}, {'id': 'work', 'name': '💼 Work', 'locationName': 'BKC'}]
        conn.close()
        return jsonify({"success": True, "favorites": favorites})

@app.route('/api/share-route', methods=['POST'])
def save_shared_route():
    route_id = str(uuid.uuid4())[:6]
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO shared_routes (route_id, route_data, created_at) VALUES (?, ?, ?)',
                 (route_id, json.dumps(request.json), datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'route_id': route_id}), 200

@app.route('/route/<route_id>', methods=['GET'])
def view_shared_route(route_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT route_data FROM shared_routes WHERE route_id = ?', (route_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return render_template('index.html', locations=MUMBAI_LOCATIONS, preloaded_route=row['route_data'])
    return render_template('index.html', locations=MUMBAI_LOCATIONS, preloaded_route=None, error="Shared route not found.")

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)