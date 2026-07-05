import cv2
import numpy as np
import base64
import json
import requests

img = np.zeros((300, 300, 3), dtype=np.uint8)
cv2.circle(img, (150, 130), 80, (180, 150, 130), -1)
cv2.circle(img, (120, 115), 12, (50, 30, 20), -1)
cv2.circle(img, (180, 115), 12, (50, 30, 20), -1)
cv2.ellipse(img, (150, 155), (25, 12), 0, 0, 180, (80, 40, 40), 2)
_, buf = cv2.imencode('.jpg', img)
b64 = base64.b64encode(buf).decode()

payload = {"id_face": "data:image/jpeg;base64," + b64, "selfie": "data:image/jpeg;base64," + b64}

print("Testing /detailed-verify through Spring Boot proxy...")
r = requests.post("http://localhost:8080/api/ai/detailed-verify", json=payload, timeout=60)
data = r.json()
print(f"Status: {r.status_code}")
print(f"Success: {data.get('success')}")
if data.get("data"):
    d = data["data"]
    print(f"verified: {d.get('verified')}")
    print(f"face_match: {d.get('face_match_score')}")
    print(f"liveness: {d.get('liveness_score')}")
    print(f"overall: {d.get('final_score')}")
    print(f"status: {d.get('status')}")
    print(f"livenessPassed: {d.get('livenessPassed')}")
    print(f"screenReplayDetected: {d.get('screenReplayDetected')}")
    print(f"printAttackDetected: {d.get('printAttackDetected')}")
    print(f"deepfakeDetected: {d.get('deepfakeDetected')}")
    print(f"antiSpoofingPassed: {d.get('antiSpoofingPassed')}")
    print(f"challengePassed: {d.get('challengePassed')}")
else:
    print(f"Error: {data.get('error', 'unknown')}")
    print(f"Full response: {json.dumps(data, indent=2)[:500]}")
