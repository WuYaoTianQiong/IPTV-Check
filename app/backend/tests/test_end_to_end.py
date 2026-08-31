import requests
import json
import time

# Get source IDs
sources = requests.get("http://127.0.0.1:9529/api/sources").json()
ids = [s["id"] for s in sources]
print(f"Sources: {len(ids)} sources, IDs: {ids}")

# Start check
r = requests.post("http://127.0.0.1:9529/api/check/start", json={
    "online_source_ids": ids,
    "timeout_connect": 3,
    "timeout_read": 8,
    "max_threads": 80,
    "run_speed_test": True,
    "use_cache": True,
})
print(f"Start result: {r.status_code}")
if r.status_code != 200:
    print(f"Error: {r.text}")
    exit(1)

# Monitor progress
for i in range(20):
    time.sleep(5)
    state = requests.get("http://127.0.0.1:9529/api/check/state").json()
    print(f"  [{i*5+5}s] total={state['total']}, checked={state['checked']}, valid={state['valid']}, invalid={state['invalid']}, phase={state['phase']}")
    if state["phase"] == "idle" and state["total"] > 0:
        print("Check completed!")
        break

print("Done.")
