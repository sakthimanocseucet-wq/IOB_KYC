"""
Test that every challenge type produces correct uppercase log tags.
"""
import requests, base64, cv2, numpy as np, json, sys, time

BASE = "http://localhost:5001"

def moving_frames(ctype, n=15):
    frames = []
    for i in range(n):
        progress = i / n
        img = np.ones((480, 640, 3), dtype=np.uint8) * 200
        mouth_open = 0.3 + progress*0.7 if ctype == 'open_mouth' else 0.0
        pitch = 0.3 + progress*0.7 if ctype == 'look_up' else -0.3 - progress*0.7 if ctype == 'look_down' else 0.0
        cx, cy, turn_off = 320, 260, int(turn * 25)
        cv2.ellipse(img, (cx + turn_off, cy), (140, 180), 0, 0, 360, (180, 160, 140), -1)
        eye_h = max(4, int(18 * eye_open))
        cv2.ellipse(img, (cx - 60 + turn_off, cy - 30), (30, eye_h), 0, 0, 360, (40, 40, 40), -1)
        cv2.ellipse(img, (cx + 60 + turn_off, cy - 30), (30, eye_h), 0, 0, 360, (40, 40, 40), -1)
        mouth_h = max(3, int(4 + mouth_open * 30))
        cv2.ellipse(img, (cx + turn_off, cy + 80), (35, mouth_h), 0, 0, 360, (80, 60, 60), -1)
        success, buf = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        frames.append(base64.b64encode(buf.tobytes()).decode())
    return frames

def get_challenge_of_type(target_type, max_attempts=20):
    for _ in range(max_attempts):
        r = requests.post(f"{BASE}/liveness/challenge", json={}, timeout=10)
        d = r.json()['data']
        if d['challenge']['challenge_type'] == target_type:
            return d['session_id'], d['challenge']
    return None, None

RESULTS = []
all_types = ['wink_left', 'wink_right', 'open_mouth', 'look_up', 'look_down', 'raise_eyebrows']
expected_tags = {
    'wink_left': ['[WINK_LEFT] entry', '[CHALLENGE_PASS] [WINK_LEFT]', '[WINK_LEFT] exit'],
    'wink_right': ['[WINK_RIGHT] entry', '[CHALLENGE_PASS] [WINK_RIGHT]', '[WINK_RIGHT] exit'],
    'open_mouth': ['[OPEN_MOUTH] entry', '[CHALLENGE_PASS] [OPEN_MOUTH]', '[OPEN_MOUTH] exit'],
    'look_up': ['[LOOK_UP] entry', '[CHALLENGE_PASS] [LOOK_UP]', '[LOOK_UP] exit'],
    'look_down': ['[LOOK_DOWN] entry', '[CHALLENGE_PASS] [LOOK_DOWN]', '[LOOK_DOWN] exit'],
    'raise_eyebrows': ['[RAISE_EYEBROWS] entry', '[CHALLENGE_PASS] [RAISE_EYEBROWS]', '[RAISE_EYEBROWS] exit'],
}

print(f"{'Type':<15} {'Function':<20} {'Entry Log':<14} {'Pass/Fail':<10} {'Result'}")
print("-" * 75)

import io
old_stderr = sys.stderr
sys.stderr = io.StringIO()

for ctype in all_types:
    sid, challenge = get_challenge_of_type(ctype)
    if not sid:
        tag_list = ', '.join(expected_tags[ctype])
        print(f"{ctype:<15} {'N/A (skipped)':<20} {'N/A':<14} {'N/A':<10} Could not get this challenge type")
        RESULTS.append({'type': ctype, 'called': False, 'entry_log': False, 'passed': False, 'log_emitted': False})
        continue
    
    frames = moving_frames(ctype)
    r = requests.post(f"{BASE}/api/ai/liveness/verify-challenge", json={
        'session_id': sid, 'challenge': challenge, 'frames': frames
    }, timeout=30)
    
    result = r.json()
    passed = result.get('data', {}).get('passed', False)
    reason = result.get('data', {}).get('reason', 'N/A')
    
    sys.stderr.seek(0)
    stderr_content = sys.stderr.read()
    
    entry_found = any(tag in stderr_content for tag in expected_tags[ctype][:2])
    exit_found = expected_tags[ctype][-1] in stderr_content
    
    called = entry_found or exit_found
    
    status = "PASS" if passed else "FAIL"
    entry_status = "FOUND" if entry_found else "MISSING"
    func_name = f"_verify_{ctype}"
    
    print(f"{ctype:<15} {func_name:<20} {entry_status:<14} {status:<10} {reason[:50]}")
    RESULTS.append({'type': ctype, 'called': called, 'entry_log': entry_found, 'exit_log': exit_found, 'passed': passed, 'reason': reason})

sys.stderr = old_stderr

print("\n--- Tag Audit Summary ---")
all_found = True
for r in RESULTS:
    ok = r['called'] and r['entry_log']
    if not ok:
        all_found = False
        print(f"  MISSING: {r['type']} — entry_log={r['entry_log']} called={r['called']}")
    else:
        print(f"  OK: {r['type']} — entry=FOUND exit={'FOUND' if r['exit_log'] else 'MISSING'} passed={r['passed']}")

print(f"\nAll tags found: {all_found}")
sys.exit(0 if all_found else 1)
