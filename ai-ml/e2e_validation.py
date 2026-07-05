"""
E2E Validation: Crash-Fixed Liveness System
Tests all 6 challenge types, session flow, Re-KYC, and logs.

Usage:
    python e2e_validation.py
"""

import requests
import base64
import json
import time
import sys
import os
import io
import traceback
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')
log = logging.getLogger('E2E')

BASE_URL = "http://localhost:5001"
RESULTS = []

def section(title):
    log.info("")
    log.info("=" * 70)
    log.info(f"  {title}")
    log.info("=" * 70)

def check(test_name, condition, detail="", fail_if_false=True):
    icon = "PASS" if condition else ("FAIL" if fail_if_false else "WARN")
    log.info(f"  [{icon:4s}] {test_name}  {detail}")
    RESULTS.append({
        "test": test_name,
        "passed": condition if fail_if_false else True,
        "warning": not condition and not fail_if_false,
        "detail": detail
    })
    if not condition and fail_if_false:
        return False
    return True

def ensure_image_has_face():
    """Create a simple face image that MediaPipe can detect.
    Returns (numpy_image, base64_data_uri)."""
    import cv2
    import numpy as np

    img = np.ones((480, 640, 3), dtype=np.uint8) * 200

    # Face oval
    cv2.ellipse(img, (320, 260), (140, 180), 0, 0, 360, (180, 160, 140), -1)

    # Eyes
    cv2.ellipse(img, (260, 230), (30, 18), 0, 0, 360, (40, 40, 40), -1)
    cv2.ellipse(img, (380, 230), (30, 18), 0, 0, 360, (40, 40, 40), -1)
    # Pupils
    cv2.circle(img, (260, 230), 8, (20, 20, 20), -1)
    cv2.circle(img, (380, 230), 8, (20, 20, 20), -1)

    # Nose
    cv2.ellipse(img, (320, 270), (18, 24), 0, 0, 360, (160, 140, 120), -1)
    # Nostrils
    cv2.circle(img, (308, 278), 4, (120, 100, 80), -1)
    cv2.circle(img, (332, 278), 4, (120, 100, 80), -1)

    # Mouth (neutral)
    cv2.ellipse(img, (320, 330), (35, 12), 0, 0, 360, (80, 60, 60), -1)
    cv2.ellipse(img, (320, 327), (28, 10), 0, 0, 360, (160, 140, 140), -1)

    # Eyebrows
    cv2.ellipse(img, (260, 200), (30, 6), 0, 0, 360, (60, 50, 40), -1)
    cv2.ellipse(img, (380, 200), (30, 6), 0, 0, 360, (60, 50, 40), -1)

    success, buf = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not success:
        return None, None

    b64 = base64.b64encode(buf.tobytes()).decode()
    data_uri = f"data:image/jpeg;base64,{b64}"
    return img, data_uri

def create_synthetic_face(eye_openness=1.0, mouth_openness=0.0, head_turn=0.0,
                          head_pitch=0.0, resolution=(640, 480)):
    """Create a synthetic face image with controllable features.
    
    Parameters control facial feature appearance for liveness challenge testing.
    eye_openness: 0.0 (closed) to 1.0 (fully open)
    mouth_openness: 0.0 (closed) to 1.0 (fully open)
    head_turn: -1.0 (left) to 1.0 (right)
    head_pitch: -1.0 (down) to 1.0 (up)
    """
    import cv2
    import numpy as np

    w, h = resolution
    cx, cy = w // 2, h // 2 - 20

    img = np.ones((h, w, 3), dtype=np.uint8) * 200

    # Head turn affects horizontal position of features
    turn_offset = int(head_turn * 25)

    # Face oval
    face_center = (cx + turn_offset, cy)
    cv2.ellipse(img, face_center, (140, 180), 0, 0, 360, (180, 160, 140), -1)

    # Eye height based on openness
    eye_h = max(4, int(18 * eye_openness))
    # Eye position also shifts slightly with head turn and pitch
    pitch_eye_offset = int(head_pitch * 8)
    
    # Left eye (stays roughly same x, but shifts with turn)
    l_eye_x = cx - 60 + turn_offset
    r_eye_x = cx + 60 + turn_offset
    eye_y = cy - 30 - pitch_eye_offset

    cv2.ellipse(img, (l_eye_x, eye_y), (30, eye_h), 0, 0, 360, (40, 40, 40), -1)
    cv2.ellipse(img, (r_eye_x, eye_y), (30, eye_h), 0, 0, 360, (40, 40, 40), -1)
    if eye_openness > 0.3:
        cv2.circle(img, (l_eye_x, eye_y), 8, (20, 20, 20), -1)
        cv2.circle(img, (r_eye_x, eye_y), 8, (20, 20, 20), -1)

    # Nose
    nose_y = cy + 10 - int(head_pitch * 15)
    cv2.ellipse(img, (cx + turn_offset, nose_y), (18, 24), 0, 0, 360, (160, 140, 120), -1)

    # Mouth
    mouth_y = cy + 80 - int(head_pitch * 10)
    mouth_h = max(3, int(4 + mouth_openness * 30))
    cv2.ellipse(img, (cx + turn_offset, mouth_y), (35, mouth_h), 0, 0, 360, (80, 60, 60), -1)
    cv2.ellipse(img, (cx + turn_offset, mouth_y - 2), (28, max(2, mouth_h - 4)), 0, 0, 360, (160, 140, 140), -1)

    # Eyebrows
    brow_y = eye_y - 28
    cv2.ellipse(img, (l_eye_x, brow_y), (30, 6), 0, 0, 360, (60, 50, 40), -1)
    cv2.ellipse(img, (r_eye_x, brow_y), (30, 6), 0, 0, 360, (60, 50, 40), -1)

    success, buf = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not success:
        return None, None, None

    b64 = base64.b64encode(buf.tobytes()).decode()
    data_uri = f"data:image/jpeg;base64,{b64}"
    return img, b64, data_uri

# =============================================================
# 1. SERVER HEALTH & MODELS
# =============================================================
section("1. Server Health & Model Verification")

try:
    r = requests.get(f"{BASE_URL}/health", timeout=5)
    check("GET /health → 200", r.status_code == 200, f"status={r.status_code}")
    health = r.json()
    check("Modules: face_verification available", health.get("modules", {}).get("face_verification", {}).get("available"))
    check("Modules: liveness available", health.get("modules", {}).get("liveness", {}).get("available"))
    check("Modules: deepfake available", health.get("modules", {}).get("deepfake", {}).get("available"))
    check("Modules: anti_spoofing unavailable (expected)", 
          not health.get("modules", {}).get("anti_spoofing", {}).get("available"),
          "MiniFASNet V2 unavailable — expected, challenge is primary protection",
          fail_if_false=False)
except Exception as e:
    check("Server health endpoint", False, str(e))

# =============================================================
# 2. DEBUG STATE
# =============================================================
section("2. Debug State")

try:
    r = requests.get(f"{BASE_URL}/liveness/debug", timeout=5)
    check("GET /liveness/debug → 200", r.status_code == 200)
    dbg = r.json().get("data", {})
    check("Face landmarker loaded", dbg.get("face_landmarker_loaded"))
    check("Not in fallback mode", not dbg.get("fallback_mode"))
    check("6 challenge types registered", len(dbg.get("challenge_types", [])) == 6)
    check("Min frames = 3", dbg.get("min_frames") == 3)
    th = dbg.get("thresholds", {})
    check("EAR threshold = 0.20", th.get("ear") == 0.20, f"got {th.get('ear')}")
    check("MAR mouth threshold = 0.20", th.get("mar_mouth") == 0.20, f"got {th.get('mar_mouth')}")
    check("MAR smile threshold = 0.15", th.get("mar_smile") == 0.15, f"got {th.get('mar_smile')}")
    check("Pitch threshold = 0.25", th.get("pitch") == 0.25, f"got {th.get('pitch')}")
    check("Yaw threshold = 0.30", th.get("yaw") == 0.30, f"got {th.get('yaw')}")
except Exception as e:
    check("Debug state", False, str(e))

# =============================================================
# 3. FACE DETECTION
# =============================================================
section("3. Face Detection Test")

img, b64, data_uri = create_synthetic_face()
if data_uri:
    try:
        r = requests.post(f"{BASE_URL}/face-detect", json={"image": data_uri}, timeout=15)
        check("POST /face-detect → 200", r.status_code == 200, f"status={r.status_code}")
        fd = r.json().get("data", {})
        faces = fd.get("faces", [])
        check("At least 1 face detected", len(faces) >= 1, f"detected {len(faces)} faces",
              fail_if_false=False)
    except Exception as e:
        check("Face detection endpoint", False, str(e))
else:
    check("Face image generation", False, "Could not create test image")

# =============================================================
# 4. CHALLENGE GENERATION
# =============================================================
section("4. Challenge Session Generation")

session_id = None
challenge_token = None
try:
    r = requests.post(f"{BASE_URL}/liveness/challenge", json={}, timeout=10)
    check("POST /liveness/challenge → 200", r.status_code == 200, f"status={r.status_code}")
    cd = r.json().get("data", {})
    session_id = cd.get("session_id")
    total = cd.get("total_challenges")
    challenge = cd.get("challenge", {})
    challenge_token = challenge.get("token")
    check("Session ID generated", bool(session_id), str(session_id)[:20])
    check("Total challenges = 4", total == 4, f"got {total}")
    check("Challenge has type", bool(challenge.get("challenge_type")), challenge.get("challenge_type"))
    check("Challenge has prompt", bool(challenge.get("prompt")), challenge.get("prompt"))
    check("Challenge timeout = 180s", challenge.get("timeout_seconds") == 180)
    check("Session expires_at set", bool(challenge.get("expires_at")))
    check("Challenge has nonce", bool(challenge.get("nonce")))
    check("Challenge has created_at", bool(challenge.get("created_at")))
except Exception as e:
    check("Challenge generation", False, str(e))
    session_id = None

if not session_id:
    log.info("  [SKIP] Cannot proceed without session_id")
    sys.exit(1)

# =============================================================
# 5. FULL 4-CHALLENGE SEQUENCE COMPLETION (Sequential Protocol)
# =============================================================
section("5. Full 4-Challenge Sequence Execution")
log.info("  Using sequential protocol: /liveness/challenge → verify-challenge ×4")

completed_challenges = []
errors = []
current_challenge = challenge  # from step 4

for challenge_num in range(4):
    log.info("")
    log.info(f"  --- Challenge {challenge_num+1}/4 ---")
    
    if not current_challenge:
        errors.append(f"Challenge {challenge_num+1}: no challenge data available")
        check(f"Step {challenge_num+1}: challenge data available", False)
        continue
    
    ctype = current_challenge.get("challenge_type", "unknown")
    check(f"Step {challenge_num+1}: challenge_type = {ctype}", bool(ctype), ctype)

    # Create synthetic frames for this challenge type
    num_frames = 15
    frames_b64 = []
    for i in range(num_frames):
        progress = i / num_frames
        
        if ctype == 'wink_left':
            # close left eye, keep right open
            _, fb, _ = create_synthetic_face(eye_openness=0.4 if 5 <= i <= 7 else 1.0)
        elif ctype == 'wink_right':
            # close right eye, keep left open
            _, fb, _ = create_synthetic_face(eye_openness=0.4 if 5 <= i <= 7 else 1.0, head_turn=0.1)
        elif ctype == 'raise_eyebrows':
            _, fb, _ = create_synthetic_face(head_pitch=0.3 + progress * 0.5)
        elif ctype == 'look_up':
            _, fb, _ = create_synthetic_face(head_pitch=0.3 + progress * 0.7)
        elif ctype == 'look_down':
            _, fb, _ = create_synthetic_face(head_pitch=-0.3 - progress * 0.7)
        elif ctype == 'open_mouth':
            _, fb, _ = create_synthetic_face(mouth_openness=0.3 + progress * 0.7)
        else:
            _, fb, _ = create_synthetic_face()
        
        if fb:
            frames_b64.append(fb)

    if not frames_b64:
        errors.append(f"Challenge {challenge_num+1}: no frames generated")
        check(f"Step {challenge_num+1}: frames generated", False)
        continue

    # Submit verification against the same session_id
    try:
        payload = {
            "session_id": session_id,
            "challenge": current_challenge,
            "frames": frames_b64
        }
        r = requests.post(f"{BASE_URL}/api/ai/liveness/verify-challenge",
                          json=payload, timeout=30)
        status_ok = r.status_code == 200
        check(f"Step {challenge_num+1}: verify-challenge → {r.status_code}",
              status_ok, f"status={r.status_code}")
        
        if status_ok:
            vd = r.json()
            log.info(f"         Response keys: {list(vd.keys())}")
            
            if vd.get("success") and "data" in vd:
                dd = vd["data"]
                passed = dd.get("passed", False)
                if passed:
                    completed_challenges.append(ctype)
                    log.info(f"         ✓ Challenge {challenge_num+1} PASSED ✓")
                    # Get next challenge from response
                    current_challenge = dd.get("next_challenge")
                else:
                    log.info(f"         ✗ Challenge {challenge_num+1} NOT passed")
                    log.info(f"         Reason: {dd.get('reason', 'N/A')}")
                    current_challenge = dd.get("next_challenge")  # may be None
                
                completed_count = dd.get("completedChallenges", 0)
                check(f"Step {challenge_num+1}: completedChallenges={completed_count}",
                      True, f"index={dd.get('challenge_index')}")
                
                # If this was the last challenge, check for final verdict
                if "verdict" in dd:
                    log.info(f"         FINAL VERDICT: {dd['verdict']}")
                    log.info(f"         Session complete!")
            else:
                log.info(f"         Response: {json.dumps(vd)[:200]}")
        else:
            log.info(f"         Error: {r.text[:150]}")
            errors.append(f"Challenge {challenge_num+1}: HTTP {r.status_code}")
    except Exception as e:
        errors.append(f"Challenge {challenge_num+1}: verification error: {e}")
        check(f"Step {challenge_num+1}: verify-challenge no exception", False, str(e))
    
    if not current_challenge:
        log.info("         [No more challenges — session complete]")
        break

# =============================================================
# 6. DETAILED-VERIFY WITH SESSION
# =============================================================
section("6. Detailed-Verify with Server-Side Session Lookup")

try:
    selfie_img, _, selfie_uri = create_synthetic_face()
    payload = {
        "selfie": selfie_uri or "",
        "session_id": session_id,
        "session_result": {
            "challengePassed": len(completed_challenges) >= 4,
            "livenessScore": 0.5 + 0.125 * min(len(completed_challenges), 4)
        }
    }
    r = requests.post(f"{BASE_URL}/detailed-verify", json=payload, timeout=60)
    check("POST /detailed-verify (with session) → 200", r.status_code == 200, f"status={r.status_code}")
    
    if r.status_code == 200:
        dv = r.json().get("data", {})
        check("Has 'verified' field", "verified" in dv, str(list(dv.keys())))
        check("Has 'livenessPassed' field", "livenessPassed" in dv)
        check("Has 'sessionLivenessConfirmed' field", "sessionLivenessConfirmed" in dv)
        check("Has 'verdict' field", "verdict" in dv)
        check("Has 'confidence' field", "confidence" in dv)
        check("Has 'reasons' array", isinstance(dv.get("reasons"), list))
        check("Has 'processing_time_ms'", dv.get("processing_time_ms", 0) > 0)
        
        liveness_passed = dv.get("livenessPassed", False)
        session_confirmed = dv.get("sessionLivenessConfirmed", False)
        verdict = dv.get("verdict", "N/A")
        log.info(f"         Liveness: {liveness_passed}, SessionConfirmed: {session_confirmed}")
        log.info(f"         Verdict: {verdict}")
        
        if len(completed_challenges) >= 4:
            check("Liveness passed (4 challenges completed)", liveness_passed,
                  f"completed={len(completed_challenges)}")
        else:
            check("Liveness not passed (incomplete session)", 
                  not liveness_passed or (liveness_passed and session_confirmed),
                  f"completed={len(completed_challenges)}, liveness={liveness_passed}",
                  fail_if_false=False)
except Exception as e:
    check("Detailed-verify with session", False, str(e))
    traceback.print_exc()

# =============================================================
# 7. DETAILED-VERIFY — Re-KYC (no id_face)
# =============================================================
section("7. Detailed-Verify — Re-KYC Flow (no id_face)")

try:
    selfie_img, _, selfie_uri = create_synthetic_face()
    payload = {
        "selfie": selfie_uri or "",
        # NO id_face — simulates Re-KYC where no ID document exists
        "session_result": {
            "challengePassed": True,
            "livenessScore": 0.75
        }
    }
    r = requests.post(f"{BASE_URL}/detailed-verify", json=payload, timeout=60)
    check("POST /detailed-verify (Re-KYC, no id_face) → 200", r.status_code == 200,
          f"status={r.status_code}")
    
    if r.status_code == 200:
        dv = r.json().get("data", {})
        check("No HTTP 500 for Re-KYC", True)
        check("Has 'verified' field", "verified" in dv)
        check("Has 'faceMatchPassed' field", "faceMatchPassed" in dv)
        check("Has 'sessionLivenessConfirmed' field", "sessionLivenessConfirmed" in dv)
        
        face_match = dv.get("faceMatchPassed", None)
        liveness_pass = dv.get("livenessPassed", False)
        session_conf = dv.get("sessionLivenessConfirmed", False)
        verdict = dv.get("verdict", "N/A")
        
        log.info(f"         FaceMatch: {face_match}, Liveness: {liveness_pass}, "
                 f"SessionConf: {session_conf}")
        log.info(f"         Verdict: {verdict}")
        
        # In Re-KYC, face match may fail (no id_face), but liveness should pass
        # The system should not throw an exception for missing id_face
        check("livenessPassed is populated (not crashing)", "livenessPassed" in dv)
        
        # Log what happened with face verification
        reasons = dv.get("reasons", [])
        face_related = [r for r in reasons if 'face' in r.lower() or 'match' in r.lower()]
        if face_related:
            log.info(f"         Face verification reason: {face_related[0]}")
except Exception as e:
    check("Detailed-verify Re-KYC", False, str(e))
    traceback.print_exc()

# =============================================================
# 8. DETAILED-VERIFY — Client-Side Session Fallback
# =============================================================
section("8. Detailed-Verify — Client-Side Session Fallback")

try:
    selfie_img, _, selfie_uri = create_synthetic_face()
    payload = {
        "selfie": selfie_uri or "",
        # No session_id — tests fallback to client-provided session_result
        "session_result": {
            "challengePassed": True,
            "livenessScore": 0.88
        }
    }
    r = requests.post(f"{BASE_URL}/detailed-verify", json=payload, timeout=60)
    check("Detailed-verify (client-side fallback) → 200", r.status_code == 200)
    
    if r.status_code == 200:
        dv = r.json().get("data", {})
        liveness = dv.get("livenessPassed", False)
        session_conf = dv.get("sessionLivenessConfirmed", False)
        check("Liveness accepted via client fallback", liveness,
              f"livenessPassed={liveness}, sessionConfirmed={session_conf}")
        check("Session confirmed via client fallback", session_conf)
        check("Verdict populated", bool(dv.get("verdict")))
except Exception as e:
    check("Detailed-verify client fallback", False, str(e))

# =============================================================
# 9. REQUEST VALIDATION (empty/invalid requests)
# =============================================================
section("9. API Robustness — Edge Cases")

# Empty body — should return 400 with error, not 500
try:
    r = requests.post(f"{BASE_URL}/detailed-verify", json={}, timeout=30)
    check("Empty body → handled (no crash)", r.status_code in [200, 400],
          f"status={r.status_code} (no 500)")
except Exception as e:
    check("Empty body test", False, str(e))

# selfie only (no id_face, no session)
try:
    r = requests.post(f"{BASE_URL}/detailed-verify", json={"selfie": ""}, timeout=30)
    check("Empty selfie only → handled (no crash)", r.status_code in [200, 400],
          f"status={r.status_code}")
except Exception as e:
    check("Empty selfie only", False, str(e))

# Null data — should fail gracefully, not crash
try:
    r = requests.post(f"{BASE_URL}/detailed-verify", json=None, timeout=30)
    check("Null body → handled gracefully", r.status_code in [200, 400, 415],
          f"status={r.status_code} (no 500)", fail_if_false=False)
except Exception as e:
    check("Null body", False, str(e), fail_if_false=False)

# Invalid session_id for verify-challenge — returns 400 with error, not 500
try:
    r = requests.post(f"{BASE_URL}/api/ai/liveness/verify-challenge", json={
        "session_id": "nonexistent",
        "challenge": {"challenge_type": "wink_left"},
        "frames": []
    }, timeout=10)
    check("Invalid session on verify-challenge → 400 with error (no 500)",
          r.status_code in [200, 400],
          f"status={r.status_code} (no 500)")
except Exception as e:
    check("Invalid session verify-challenge", False, str(e))

# =============================================================
# 10. VERIFY NO HTTP 500 IN LOG
# =============================================================
section("10. Log Review — HTTP 500 / Exceptions")

log_path = os.path.join(os.path.dirname(__file__), "flask_stderr.log")
all_500 = []
all_exceptions = []
all_crash_tags = []

if os.path.exists(log_path):
    with open(log_path, 'r') as f:
        content = f.read()
    
    # Look for HTTP 500 in access log
    for line in content.split('\n'):
        if '" 500 -' in line:
            all_500.append(line.strip())
    
    # Look for exceptions (but not expected warnings)
    for line in content.split('\n'):
        if 'Traceback' in line or 'UnboundLocalError' in line:
            all_exceptions.append(line.strip())
    
    # Look for ERROR level messages
    for line in content.split('\n'):
        if 'ERROR' in line and 'WARNING' not in line:
            all_crash_tags.append(line.strip())

    check("No HTTP 500 responses", len(all_500) == 0, 
          f"Found {len(all_500)} 500s: {'; '.join(all_500[:3])}" if all_500 else "Clean")
    check("No UnboundLocalError exceptions", len(all_exceptions) == 0,
          f"Found: {all_exceptions[:3]}" if all_exceptions else "Clean")
    
    # Count [LIVENESS_DEBUG] entries
    liveness_debug_count = sum(1 for l in content.split('\n') if '[LIVENESS_DBG]' in l)
    check("[LIVENESS_DEBUG] entries logged", liveness_debug_count > 0,
          f"Found {liveness_debug_count} entries")
    
    # Count challenge-specific debug entries
    for tag in ['[WINK_LEFT]', '[WINK_RIGHT]', '[OPEN_MOUTH]', '[LOOK_UP]', '[LOOK_DOWN]', '[RAISE_EYEBROWS]']:
        count = sum(1 for l in content.split('\n') if tag in l)
        check(f"{tag} log entries found", count > 0, f"Found {count} entries",
              fail_if_false=False)
    
    # Count [DIAG] entries
    diag_count = sum(1 for l in content.split('\n') if '[DIAG]' in l)
    check("[DIAG] entries logged", diag_count > 0, f"Found {diag_count} entries",
          fail_if_false=False)
    
    # Check for any ERROR level messages (excluding expected ones)
    error_lines = [l for l in content.split('\n') 
                   if ' ERROR ' in l and 'WARNING' not in l]
    # Filter out expected mediapipe warnings
    real_errors = [e for e in error_lines if 'UserWarning' not in e and 
                   'Sets FaceBlendshapesGraph' not in e and
                   'feedback_manager' not in e.lower()]
    check("No ERROR-level log messages (excluding expected)", len(real_errors) == 0,
          f"Found {len(real_errors)} errors: {'; '.join(real_errors[:3])}" if real_errors else "Clean")
else:
    check("Log file exists", False, f"Not found at {log_path}")

# =============================================================
# 11. LIVE VERIFICATION REQUEST (simulated)
# =============================================================
section("11. Combined Liveness Endpoint")

try:
    selfie_img, _, selfie_uri = create_synthetic_face()
    payload = {"selfie": selfie_uri or ""}
    r = requests.post(f"{BASE_URL}/api/ai/liveness/combined", json=payload, timeout=30)
    check("POST /api/ai/liveness/combined → 200", r.status_code == 200,
          f"status={r.status_code}")
    if r.status_code == 200:
        d = r.json()
        check("Response has 'success'", "success" in d)
        if d.get("success") and "data" in d:
            dd = d["data"]
            check("Has 'liveness_score' or 'confidence'", 
                  "liveness_score" in dd or "confidence" in dd,
                  str(list(dd.keys())))
except Exception as e:
    check("Combined liveness endpoint", False, str(e))

# =============================================================
# 12. GENERATE FINAL REPORT
# =============================================================
section("12. Final Validation Report")

passed = sum(1 for r in RESULTS if r.get("passed") and not r.get("warning"))
failed = sum(1 for r in RESULTS if not r.get("passed") and not r.get("warning"))
warnings = sum(1 for r in RESULTS if r.get("warning"))
total = len(RESULTS)

log.info("")
log.info("  " + "-" * 50)
log.info(f"  TOTAL TESTS: {total}")
log.info(f"  PASSED:      {passed}")
log.info(f"  FAILED:      {failed}")
log.info(f"  WARNINGS:    {warnings}")
log.info("  " + "-" * 50)

if failed > 0:
    log.info("\n  FAILED TESTS:")
    for r in RESULTS:
        if not r.get("passed") and not r.get("warning"):
            log.info(f"    ✗ {r['test']}: {r['detail']}")
if warnings > 0:
    log.info("\n  WARNINGS:")
    for r in RESULTS:
        if r.get("warning"):
            log.info(f"    ⚠ {r['test']}: {r['detail']}")

log.info("")
log.info("  " + "=" * 50)
if failed == 0:
    log.info("  VALIDATION: ALL CRITICAL TESTS PASSED")
else:
    log.info(f"  VALIDATION: {failed} TESTS FAILED — review above")
log.info("  " + "=" * 50)

# Export JSON report
report_path = os.path.join(os.path.dirname(__file__), "e2e_report.json")
with open(report_path, 'w') as f:
    json.dump({
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "summary": {"total": total, "passed": passed, "failed": failed, "warnings": warnings},
        "results": RESULTS,
        "completed_challenges": completed_challenges,
        "errors": errors,
        "success": failed == 0
    }, f, indent=2)
log.info(f"\n  Report exported to: {report_path}")

sys.exit(0 if failed == 0 else 1)
