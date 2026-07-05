"""Test that completely static frames FAIL all challenge types."""
import requests, base64, cv2, numpy as np, json, sys

BASE = "http://localhost:5001"

def make_identical_frames(n=15):
    """Create n identical face images (no movement)."""
    frames = []
    for _ in range(n):
        img = np.ones((480, 640, 3), dtype=np.uint8) * 200
        cv2.ellipse(img, (320, 260), (140, 180), 0, 0, 360, (180, 160, 140), -1)
        cv2.ellipse(img, (260, 230), (30, 18), 0, 0, 360, (40, 40, 40), -1)
        cv2.ellipse(img, (380, 230), (30, 18), 0, 0, 360, (40, 40, 40), -1)
        cv2.ellipse(img, (320, 330), (35, 6), 0, 0, 360, (80, 60, 60), -1)
        success, buf = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        frames.append(base64.b64encode(buf.tobytes()).decode())
    return frames

def make_moving_frames(ctype, n=15):
    """Create frames simulating the specified movement."""
    frames = []
    for i in range(n):
        progress = i / n
        img = np.ones((480, 640, 3), dtype=np.uint8) * 200
        turn = 0
        pitch = 0
        eye_open = 1.0
        mouth_open = 0.0
        
        if ctype == 'wink_left' or ctype == 'wink_right':
            pass
        elif ctype == 'look_up':
            pitch = 0.3 + progress * 0.7
        elif ctype == 'look_down':
            pitch = -0.3 - progress * 0.7
        elif ctype == 'open_mouth':
            mouth_open = 0.3 + progress * 0.7
        
        cx, cy = 320, 240
        turn_off = int(turn * 25)
        pitch_eye_off = int(pitch * 8)
        
        cv2.ellipse(img, (cx + turn_off, cy), (140, 180), 0, 0, 360, (180, 160, 140), -1)
        eye_h = max(4, int(18 * eye_open))
        cv2.ellipse(img, (cx - 60 + turn_off, cy - 30 - pitch_eye_off), (30, eye_h), 0, 0, 360, (40, 40, 40), -1)
        cv2.ellipse(img, (cx + 60 + turn_off, cy - 30 - pitch_eye_off), (30, eye_h), 0, 0, 360, (40, 40, 40), -1)
        mouth_h = max(3, int(4 + mouth_open * 30))
        cv2.ellipse(img, (cx + turn_off, cy + 80 - int(pitch * 10)), (35, mouth_h), 0, 0, 360, (80, 60, 60), -1)
        
        success, buf = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        frames.append(base64.b64encode(buf.tobytes()).decode())
    return frames

pass_count = 0
fail_count = 0

all_types = ['wink_left', 'wink_right', 'open_mouth', 'look_up', 'look_down']

print("=" * 60)
print("STATIC FRAME REJECTION TEST")
print("=" * 60)

# 1. Test static frames FAIL for all types
print("\n--- Test 1: Completely static frames (identical) ---")
for ctype in all_types:
    # Keep creating sessions until we get the desired type
    for attempt in range(20):
        r = requests.post(f"{BASE}/liveness/challenge", json={}, timeout=10)
        sid = r.json()['data']['session_id']
        challenge = r.json()['data']['challenge']
        actual_type = challenge['challenge_type']
        if actual_type == ctype:
            break
    
    if actual_type != ctype:
        print(f"  SKIP: {ctype} — could not get this type in 20 attempts")
        continue
    
    static_frames = make_identical_frames()
    r = requests.post(f"{BASE}/api/ai/liveness/verify-challenge", json={
        'session_id': sid, 'challenge': challenge, 'frames': static_frames
    }, timeout=30)
    result = r.json()
    
    if 'data' in result:
        passed = result['data'].get('passed', False)
        reason = result['data'].get('reason', 'N/A')
    else:
        passed = result.get('challenge_passed', False)
        reason = result.get('reason', 'N/A')
    
    if passed:
        print(f"  FAIL: {ctype} passed with static frames! reason={reason}")
        pass_count += 1
    else:
        print(f"  PASS: {ctype} correctly rejected. reason={reason}")
        fail_count += 1

# 2. Test that moving frames CAN pass (use actual server-assigned challenge types)
print("\n--- Test 2: Moving frames with correct challenge type ---")
for ctype in all_types:
    # Keep creating sessions until we get the desired type
    for attempt in range(10):
        r = requests.post(f"{BASE}/liveness/challenge", json={}, timeout=10)
        sid = r.json()['data']['session_id']
        challenge = r.json()['data']['challenge']
        actual_type = challenge['challenge_type']
        if actual_type == ctype:
            break
    
    if actual_type != ctype:
        print(f"  SKIP: {ctype} — could not get this type (server assigned {actual_type})")
        continue
    
    moving_frames = make_moving_frames(ctype)
    r = requests.post(f"{BASE}/api/ai/liveness/verify-challenge", json={
        'session_id': sid, 'challenge': challenge, 'frames': moving_frames
    }, timeout=30)
    result = r.json()
    
    if 'data' in result:
        passed = result['data'].get('passed', False)
        reason = result['data'].get('reason', 'N/A')
    else:
        passed = result.get('challenge_passed', False)
        reason = result.get('reason', 'N/A')
    
    status = "PASS" if passed else "FAIL"
    print(f"  {status}: {ctype} -> passed={passed} reason={reason}")

print(f"\n{'=' * 60}")
print(f"Static rejection: {fail_count}/{len(all_types)} correctly rejected")
print(f"False passes: {pass_count}/{len(all_types)}")
print(f"{'=' * 60}")

sys.exit(0 if fail_count == len(all_types) else 1)
