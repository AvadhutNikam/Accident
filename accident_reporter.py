import sqlite3
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import math


class AccidentReporter:
    """Manages real-time accident reports from users using SQLite."""
    
    def __init__(self, db_path: str = "data/mumbai_safe_route.db"):
        self.db_path = db_path
        self.expiry_hours = 2
        self._init_db()
        
    def _init_db(self):
        """Initialize the database table if it doesn't exist."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS accidents (
            id TEXT PRIMARY KEY,
            timestamp TEXT,
            latitude REAL,
            longitude REAL,
            severity TEXT,
            description TEXT,
            upvotes INTEGER DEFAULT 0,
            downvotes INTEGER DEFAULT 0,
            verified BOOLEAN DEFAULT 0,
            expires_at TEXT,
            processed BOOLEAN DEFAULT 0
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS accident_votes (
            user_id TEXT,
            accident_id TEXT,
            vote_type TEXT,
            PRIMARY KEY (user_id, accident_id)
        )
        ''')
        
        # Safe schema migration for existing databases
        try:
            cursor.execute("ALTER TABLE accidents ADD COLUMN processed BOOLEAN DEFAULT 0")
        except sqlite3.OperationalError:
            pass # Column already exists
        try:
            cursor.execute("ALTER TABLE accidents ADD COLUMN user_id TEXT")
        except sqlite3.OperationalError:
            pass
            
        conn.commit()
        conn.close()
    
    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def report_accident(self, latitude: float, longitude: float, 
                       severity: str, description: str = "",
                       user_id: Optional[str] = None) -> Dict:
        """Report a new accident and store in SQLite."""
        expires_at = (datetime.now() + timedelta(hours=self.expiry_hours)).isoformat()
        timestamp = datetime.now().isoformat()
        accident_id = f"acc_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO accidents (id, timestamp, latitude, longitude, severity, description, verified, expires_at, processed, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
        ''', (accident_id, timestamp, round(latitude, 6), round(longitude, 6), 
              severity.lower(), description, False, expires_at, user_id))
        conn.commit()
        conn.close()
        
        return {
            'id': accident_id,
            'timestamp': timestamp,
            'latitude': latitude,
            'longitude': longitude,
            'severity': severity.lower(),
            'description': description,
            'upvotes': 0,
            'downvotes': 0,
            'verified': False,
            'expires_at': expires_at,
            'user_id': user_id
        }
    
    def get_active_accidents(self) -> List[Dict]:
        """Get all active (non-expired) accidents from SQLite."""
        now = datetime.now().isoformat()
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Clean expired on read (optional, but keeps DB tidy)
        cursor.execute('DELETE FROM accidents WHERE expires_at < ?', (now,))
        conn.commit()
        
        cursor.execute('SELECT * FROM accidents WHERE expires_at >= ?', (now,))
        rows = cursor.fetchall()
        
        accidents = []
        for row in rows:
            acc = dict(row)
            acc['verified'] = bool(acc['verified'])
            accidents.append(acc)
            
        conn.close()
        return accidents
        
    def get_unprocessed_verified_accidents(self) -> List[Dict]:
        """Fetch verified accidents that haven't been fed to the ML model yet."""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Fetching strictly where verified=1 and processed=0
        cursor.execute('SELECT * FROM accidents WHERE verified = 1 AND processed = 0')
        rows = cursor.fetchall()
        
        accidents = [dict(row) for row in rows]
        conn.close()
        return accidents
        
    def mark_accidents_processed(self, accident_ids: List[str]):
        """Flag a list of accident IDs as completely processed."""
        if not accident_ids:
            return
            
        conn = self._get_connection()
        cursor = conn.cursor()
        
        placeholders = ','.join(['?'] * len(accident_ids))
        cursor.execute(f'UPDATE accidents SET processed = 1 WHERE id IN ({placeholders})', accident_ids)
        
        conn.commit()
        conn.close()
    
    def get_accidents_near_location(self, latitude: float, longitude: float, 
                                    radius_km: float = 2.0) -> List[Dict]:
        """Get accidents within radius_km of a location."""
        all_accidents = self.get_active_accidents()
        nearby = []
        
        for acc in all_accidents:
            distance = self._haversine_distance(
                latitude, longitude,
                acc['latitude'], acc['longitude']
            )
            if distance <= radius_km:
                acc['distance_km'] = round(distance, 2)
                nearby.append(acc)
        
        nearby.sort(key=lambda x: x['distance_km'])
        return nearby
    
    def get_accidents_on_route(self, waypoints: List[List[float]], 
                               buffer_km: float = 0.5) -> List[Dict]:
        """Get accidents along a route with buffer zone."""
        all_accidents = self.get_active_accidents()
        route_accidents = []
        
        for acc in all_accidents:
            for i in range(len(waypoints) - 1):
                distance = self._point_to_segment_distance(
                    acc['latitude'], acc['longitude'],
                    waypoints[i][0], waypoints[i][1],
                    waypoints[i+1][0], waypoints[i+1][1]
                )
                
                if distance <= buffer_km:
                    acc['distance_from_route_km'] = round(distance, 2)
                    route_accidents.append(acc)
                    break
        
        return route_accidents
    
    def vote_accident(self, accident_id: str, vote_type: str, user_id: str) -> bool:
        """Upvote or downvote an accident report in SQLite."""
        if not user_id: return False
        
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Check if user already voted
        cursor.execute('SELECT * FROM accident_votes WHERE user_id = ? AND accident_id = ?', (user_id, accident_id))
        if cursor.fetchone():
            conn.close()
            return False
            
        cursor.execute('SELECT * FROM accidents WHERE id = ?', (accident_id,))
        acc = cursor.fetchone()
        
        if not acc:
            conn.close()
            return False
            
        upvotes = acc['upvotes']
        downvotes = acc['downvotes']
        verified = acc['verified']
        
        if vote_type == 'up':
            upvotes += 1
            if upvotes >= 3:
                verified = True
        elif vote_type == 'down':
            downvotes += 1
            
        # Record the vote to prevent dupes
        cursor.execute('INSERT INTO accident_votes (user_id, accident_id, vote_type) VALUES (?, ?, ?)', (user_id, accident_id, vote_type))
            
        if downvotes >= 5:
            cursor.execute('DELETE FROM accidents WHERE id = ?', (accident_id,))
            cursor.execute('DELETE FROM accident_votes WHERE accident_id = ?', (accident_id,))
        else:
            cursor.execute('''
                UPDATE accidents 
                SET upvotes = ?, downvotes = ?, verified = ? 
                WHERE id = ?
            ''', (upvotes, downvotes, verified, accident_id))
            
        conn.commit()
        conn.close()
        return True
    
    def get_accident_impact_multiplier(self, waypoints: List[List[float]]) -> float:
        """Calculate risk multiplier based on accidents on route."""
        accidents = self.get_accidents_on_route(waypoints, buffer_km=0.5)
        
        if not accidents:
            return 1.0
        
        severity_weights = {
            'minor': 1.05,
            'moderate': 1.15,
            'severe': 1.30,
            'fatal': 1.50
        }
        
        total_impact = 1.0
        now = datetime.now()
        
        for acc in accidents:
            base_weight = severity_weights.get(acc['severity'], 1.10)
            accident_time = datetime.fromisoformat(acc['timestamp'])
            age_minutes = (now - accident_time).total_seconds() / 60
            
            if age_minutes <= 30:
                time_factor = 1.0
            elif age_minutes <= 60:
                time_factor = 0.8
            else:
                time_factor = 0.5
            
            verification_factor = 1.2 if acc.get('verified') else 1.0
            impact = (base_weight - 1.0) * time_factor * verification_factor
            total_impact += impact
        
        return min(2.0, total_impact)
    
    def _haversine_distance(self, lat1: float, lon1: float, 
                           lat2: float, lon2: float) -> float:
        """Calculate distance between two points in km."""
        R = 6371
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
        return R * 2 * math.asin(math.sqrt(a))
    
    def _point_to_segment_distance(self, px: float, py: float,
                                    x1: float, y1: float,
                                    x2: float, y2: float) -> float:
        """Calculate minimum distance from point to line segment in km."""
        dx, dy = px - x1, py - y1
        sx, sy = x2 - x1, y2 - y1
        
        if sx == 0 and sy == 0:
            return self._haversine_distance(px, py, x1, y1)
        
        t = max(0, min(1, (dx*sx + dy*sy) / (sx*sx + sy*sy)))
        return self._haversine_distance(px, py, x1 + t * sx, y1 + t * sy)

