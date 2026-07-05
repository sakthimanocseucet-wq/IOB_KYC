"""Test Flask directly with real webcam frames - bypass Spring Boot proxy."""
import sys, os, time, base64, json, requests, cv2, numpy as np
sys.path.insert(0, os.path.dirname(__file__))

FLASK = "http://localhost:5001"

print("=" * 60)
print("  Direct Flask Test with Real Webcam")
print("=" * 60)

# 1. Open webcam
print("\n--- Opening webcam ---")
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
if not cap.isOpened():
    cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("ERROR: Cannot open webcam")
    sys.exit(1)

cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
cap.set(cv2.CAP_PROP_FPS, 30)
time.sleep(2)

# 2. Capture test frame
ret, test_frame = cap.read()
if not ret or test_frame is None:
    print("ERROR: Cannot read frame")
    cap.release()
    sys.exit(1)

brightness = np.mean(test_frame)
print(f"Webcam: {test_frame.shape}, brightness={brightness:.1f}")

if brightness < 5:
    print("WARNING: Camera produces dark frames!")
    print("Testing with synthetic frames instead...")
    cap.release()
    # Create synthetic frames with face-like features
    frames_b64 = []
    for i in range(15):
        img = np.ones((480, 640, 3), dtype=np.uint8) * 128
        cx, cy = 320, 240
        cv2.ellipse(img, (cx, cy), (120, 150), 0, 0, 360, (180, 160, 140), -1)
        eye_y = cy - 30 + (i % 3)
        cv2.ellipse(img, (cx-50, eye_y), (12, 6), 0, 0, 360, (50, 50, 50), -1)
        cv2.circle(img, (cx-48, eye_y-2), 3, (20, 20, 20), -1)
        cv2.ellipse(img, (cx+50, eye_y), (12, 6), 0, 0, 360, (50, 50, 50), -1)
        cv2.circle(img, (cx+52, eye_y-2), 3, (20, 20, 20), -1)
        cv2.ellipse(img, (cx, cy+50), (20, 5), 0, 0, 360, (100, 80, 80), 2)
        cv2.line(img, (cx, cy-10), (cx-5, cy+20), (140, 120, 120), 2)
        _, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        b64 = base64.b64encode(buf).decode('utf-8')
        frames_b64.append('data:image/jpeg;base64,' + b64)
    print(f"Created {len(frames_b64)} synthetic frames")
else:
    # Capture 15 real frames
    print("Capturing 15 real frames...")
    frames_b64 = []
    for i in range(15):
        ret, frame = cap.read()
        if ret and frame is not None:
            _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            b64 = base64.b64encode(buf).decode('utf-8')
            frames_b64.append('data:image/jpeg;base64,' + b64)
            br = np.mean(frame)
            print(f"  Frame {i}: {frame.shape} brightness={br:.1f} size={len(b64)//1024}KB")
        time.sleep(0.05)
    cap.release()
    print(f"Captured {len(frames_b64)} frames")

if len(frames_b64) < 6:
    print("ERROR: Not enough frames captured")
    sys.exit(1)

# 3. Check Flask health
print("\n--- Flask Health ---")
try:
    r = requests.get(f"{FLASK}/health", timeout=5)
    print(f"Status: {r.json().get('status')}")
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)

# 4. Generate challenge
print("\n--- Generate Challenge ---")
try:
    r = requests.post(f"{FLASK}/api/ai/liveness/challenge", json={}, timeout=10)
    data = r.json()
    session_id = data['data']['session_id']
    challenge = data['data']['challenge']
    print(f"Challenge: {challenge['challenge_type']}")
    print(f"Session: {session_id}")
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)

# 5. Send frames DIRECTLY to Flask (bypass Spring Boot)
print("\n--- Sending frames DIRECTLY to Flask ---")
payload = {
    "session_id": session_id,
    "challenge": challenge,
    "frames": frames_b64
}
total_kb = sum(len(f) for f in frames_b64) // 1024
print(f"Payload size: {total_kb}KB ({len(frames_b64)} frames)")

try:
    t0 = time.time()
    r = requests.post(f"{FLASK}/api/ai/liveness/verify-challenge",
                     json=payload, timeout=60)
    elapsed = time.time() - t0
    print(f"Response time: {elapsed:.1f}s")
    print(f"Status: {r.status_code}")
    result = r.json()
    print(f"Success: {result.get('success')}")
    if result.get('success'):
        d = result.get('data', {})
        print(f"Passed: {d.get('passed')}")
        print(f"Reason: {d.get('reason', 'none')}")
        print(f"Confidence: {d.get('confidence', 'N/A')}")
        if 'details' in d:
            det = d['details']
            if 'diag' in det:
                diag = det['diag']
                print(f"Primary detected: {diag.get('primary_detected')}")
                print(f"Primary conf: {diag.get('primary_conf')}")
            if 'ear_range' in det:
                print(f"EAR range: {det['ear_range']}")
            if 'mar_range' in det:
                print(f"MAR range: {det['mar_range']}")
            if 'pitch_range' in det:
                print(f"Pitch range: {det['pitch_range']}")
    else:
        print(f"Error: {result.get('error')}")
except Exception as e:
    print(f"ERROR: {e}")

# 6. Also test through Spring Boot proxy
print("\n--- Sending frames through Spring Boot proxy ---")
try:
    t0 = time.time()
    r = requests.post("http://localhost:8080/api/ai/liveness/verify-challenge",
                     json=payload, timeout=60)
    elapsed = time.time() - t0
    print(f"Response time: {elapsed:.1f}s")
    print(f"Status: {r.status_code}")
    result = r.json()
    print(f"Success: {result.get('success')}")
    if result.get('success'):
        d = result.get('data', {})
        print(f"Passed: {d.get('passed')}")
        print(f"Reason: {d.get('reason', 'none')}")
except Exception as e:
    print(f"ERROR: {e}")
