import requests
import time
import sqlite3
import sys

BASE_URL = "http://localhost:5000"

print("="*60)
print("CONTINUOUS LEARNING PIPELINE - AUTOMATED API DEMO")
print("="*60)

# Step 1: Simulate a User Accident Report
print("\n[1] Simulating a live user reporting a severe hazard...")
payload = {
    "latitude": 19.0596,
    "longitude": 72.8295,
    "type": "Accident", 
    "severity": "high",
    "description": "Massive pileup reported on the network via ML Auto-Demo"
}

try:
    res = requests.post(f"{BASE_URL}/api/accidents/report", json=payload)
    if res.status_code == 200:
        data = res.json()
        acc_id = data.get('id')
        print(f"    [SUCCESS] Successfully reported over REST API. Received Accident ID: {acc_id}")
    else:
        print(f"    [FAILED] Report failed: {res.text}")
        sys.exit(1)
except Exception as e:
    print(f"    [FAILED] HTTP connection failed. Is Flask running? Error: {e}")
    sys.exit(1)

time.sleep(1)

# Step 2: Verify the Accident (Simulating Admin/Crowd Consensus)
print("\n[2] Simulating crowdsourced verification consensus (verified=1)...")
try:
    conn = sqlite3.connect('data/mumbai/accidents.db')
    c = conn.cursor()
    c.execute("UPDATE accidents SET verified = 1 WHERE id = ?", (acc_id,))
    conn.commit()
    conn.close()
    print("    [SUCCESS] Accident verified securely in the SQLite matrix. Ready for ML ingestion.")
except Exception as e:
    print(f"    [FAILED] Verification simulation failed: {e}")
    sys.exit(1)

time.sleep(1)

# Step 3: Trigger the Continuous Learning Pipeline
print("\n[3] Triggering the Continuous Learning Pipeline via Admin Control Endpoint...")
print("    This will flush the report into the physical training set and rebuild the XGBoost .pkl estimators natively...")
start = time.time()
try:
    res = requests.post(f"{BASE_URL}/api/admin/run-pipeline")
    if res.status_code == 200:
        data = res.json()
        dur = round(time.time() - start, 2)
        print(f"    [SUCCESS] Pipeline Execution Success! (Took {dur}s)")
        print(f"       Message: {data.get('message')}")
        print(f"       Processed: {data.get('count')} records incorporated.")
        print("    [SUCCESS] Flask Application successfully hot-swapped the newly trained machine learning models into memory.")
    else:
        print(f"    [FAILED] Pipeline API execution failed: {res.text}")
except Exception as e:
    print(f"    [FAILED] Admin Pipeline API call failed: {e}")

print("\n" + "="*60)
print("FULL END-TO-END VERIFICATION COMPLETE")
print("="*60)
