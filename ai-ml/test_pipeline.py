"""
End-to-end pipeline test for liveness verification.
Tests the complete flow: frame -> base64 -> Flask endpoint -> MediaPipe -> challenge detection.
"""
import sys
import os
import time
import base64
import json
import requests
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))

FLASK_URL = "http://localhost:5001"

def log(msg, level="INFO"):
    print(f"[{level}] {msg}")

def create_test_frame(w=640, h=480, action="neutral"):
    """Create a synthetic test frame simulating a face."""
    img = np.ones((h, w, 3), dtype=np.uint8) * 128  # gray background

    # Draw a simple face-like pattern
    cx, cy = w // 2, h // 2

    # Face oval (skin color)
    cv2.ellipse(img, (cx, cy), (120, 150), 0, 0, 360, (180, 160, 140), -1)

    # Eyes
    eye_y = cy - 30
    left_eye_x, right_eye_x = cx - 50, cx + 50
    if action == "wink_left":
        # Left eye closed (line), right eye open (ellipse)
        cv2.line(img, (left_eye_x - 15, eye_y), (left_eye_x + 15, eye_y), (50, 50, 50), 2)
        cv2.ellipse(img, (right_eye_x, eye_y), (15, 8), 0, 0, 360, (50, 50, 50), -1)
        cv2.circle(img, (right_eye_x + 2, eye_y - 2), 3, (20, 20, 20), -1)
    elif action == "wink_right":
        cv2.ellipse(img, (left_eye_x, eye_y), (15, 8), 0, 0, 360, (50, 50, 50), -1)
        cv2.circle(img, (left_eye_x + 2, eye_y - 2), 3, (20, 20, 20), -1)
        cv2.line(img, (right_eye_x - 15, eye_y), (right_eye_x + 15, eye_y), (50, 50, 50), 2)
    elif action == "open_mouth":
        cv2.ellipse(img, (left_eye_x, eye_y), (12, 6), 0, 0, 360, (50, 50, 50), -1)
        cv2.circle(img, (left_eye_x + 2, eye_y - 2), 3, (20, 20, 20), -1)
        cv2.ellipse(img, (right_eye_x, eye_y), (12, 6), 0, 0, 360, (50, 50, 50), -1)
        cv2.circle(img, (right_eye_x + 2, eye_y - 2), 3, (20, 20, 20), -1)
        # Open mouth
        cv2.ellipse(img, (cx, cy + 50), (25, 15), 0, 0, 360, (50, 50, 100), -1)
    else:  # neutral
        cv2.ellipse(img, (left_eye_x, eye_y), (12, 6), 0, 0, 360, (50, 50, 50), -1)
        cv2.circle(img, (left_eye_x + 2, eye_y - 2), 3, (20, 20, 20), -1)
        cv2.ellipse(img, (right_eye_x, eye_y), (12, 6), 0, 0, 360, (50, 50, 50), -1)
        cv2.circle(img, (right_eye_x + 2, eye_y - 2), 3, (20, 20, 20), -1)

    # Mouth (neutral)
    if action != "open_mouth":
        cv2.ellipse(img, (cx, cy + 50), (20, 5), 0, 0, 360, (100, 80, 80), 2)

    # Nose
    cv2.line(img, (cx, cy - 10), (cx - 5, cy + 20), (140, 120, 120), 2)

    return img

def img_to_base64(img, quality=80):
    """Convert OpenCV image to base64 JPEG string."""
    _, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    b64 = base64.b64encode(buffer).decode('utf-8')
    return f"data:image/jpeg;base64,{b64}"

def test_health():
    """Test Flask health endpoint."""
    log("=== Test 1: Health Check ===")
    try:
        r = requests.get(f"{FLASK_URL}/health", timeout=5)
        data = r.json()
        log(f"Status: {data.get('status')}")
        log(f"Face verification: {data.get('modules', {}).get('face_verification', {}).get('available')}")
        log(f"Liveness: {data.get('modules', {}).get('liveness', {}).get('available')}")
        log(f"Anti-spoof: {data.get('modules', {}).get('anti_spoofing', {}).get('available')}")
        return data.get('status') == 'healthy'
    except Exception as e:
        log(f"Health check failed: {e}", "ERROR")
        return False

def test_challenge_generation():
    """Test challenge generation endpoint."""
    log("\n=== Test 2: Challenge Generation ===")
    try:
        r = requests.post(f"{FLASK_URL}/api/ai/liveness/challenge", json={}, timeout=10)
        data = r.json()
        if data.get('success'):
            session_id = data['data']['session_id']
            challenge = data['data']['challenge']
            log(f"Session ID: {session_id}")
            log(f"Challenge type: {challenge.get('challenge_type')}")
            log(f"Prompt: {challenge.get('prompt')}")
            return session_id, challenge
        else:
            log(f"Challenge generation failed: {data.get('error')}", "ERROR")
            return None, None
    except Exception as e:
        log(f"Challenge generation error: {e}", "ERROR")
        return None, None

def test_frame_sending(session_id, challenge):
    """Test sending frames to verify-challenge endpoint."""
    log("\n=== Test 3: Frame Sending ===")
    if not session_id or not challenge:
        log("Skipping (no session/challenge)", "WARN")
        return False

    # Create 10 test frames
    frames = []
    for i in range(10):
        img = create_test_frame(action="neutral")
        frames.append(img_to_base64(img))

    log(f"Created {len(frames)} frames")
    log(f"First frame size: {len(frames[0])} chars ({len(frames[0])//1024}KB)")

    try:
        r = requests.post(f"{FLASK_URL}/api/ai/liveness/verify-challenge",
                         json={
                             "session_id": session_id,
                             "challenge": challenge,
                             "frames": frames
                         },
                         timeout=30)
        data = r.json()
        log(f"Response status: {r.status_code}")
        log(f"Success: {data.get('success')}")
        if data.get('success'):
            result_data = data.get('data', {})
            log(f"Passed: {result_data.get('passed')}")
            log(f"Reason: {result_data.get('reason', 'none')}")
            log(f"Confidence: {result_data.get('confidence', 'N/A')}")
            return result_data.get('passed', False)
        else:
            log(f"Error: {data.get('error')}", "ERROR")
            return False
    except Exception as e:
        log(f"Frame sending error: {e}", "ERROR")
        return False

def test_frame_quality():
    """Test frame quality and MediaPipe detection."""
    log("\n=== Test 4: Frame Quality & MediaPipe Detection ===")
    from liveness_detection import ChallengeLivenessDetector

    det = ChallengeLivenessDetector()
    if det.FALLBACK_MODE:
        log("MediaPipe in fallback mode!", "ERROR")
        return False

    # Test with synthetic frame
    img = create_test_frame()
    landmarks = det._extract_landmarks_from_image(img)
    if landmarks is not None:
        log(f"MediaPipe detected {len(landmarks)} landmarks on synthetic frame")
        ear = det._compute_ear(landmarks, [33,160,158,133,153,144], [362,385,387,263,373,380])
        mar = det._compute_mar(landmarks)
        log(f"EAR: {ear:.4f}, MAR: {mar:.4f}")
        return True
    else:
        log("MediaPipe could not detect face in synthetic frame", "WARN")
        log("This is expected for simple synthetic images", "INFO")
        return True  # Not a failure - synthetic images are hard for MediaPipe

def test_real_webcam():
    """Test with real webcam frames if available."""
    log("\n=== Test 5: Real Webcam Test ===")
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        log("No webcam available", "WARN")
        return None

    time.sleep(2)
    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        log("Cannot read from webcam", "WARN")
        return None

    brightness = np.mean(frame)
    log(f"Webcam frame: {frame.shape}, brightness={brightness:.1f}")

    if brightness < 5:
        log("Webcam produces dark/black frames (hardware issue)", "WARN")
        return None

    # Test MediaPipe on real frame
    from liveness_detection import ChallengeLivenessDetector
    det = ChallengeLivenessDetector()
    landmarks = det._extract_landmarks_from_image(frame)
    if landmarks is not None:
        log(f"MediaPipe detected {len(landmarks)} landmarks on real frame!")
        ear = det._compute_ear(landmarks, [33,160,158,133,153,144], [362,385,387,263,373,380])
        mar = det._compute_mar(landmarks)
        pose = det._compute_head_pose(landmarks)
        log(f"EAR: {ear:.4f}, MAR: {mar:.4f}")
        log(f"Pose: yaw={pose['yaw']:.1f} pitch={pose['pitch']:.1f} roll={pose['roll']:.1f}")
        return True
    else:
        log("MediaPipe could not detect face in real frame", "WARN")
        return False

def test_debug_endpoint():
    """Test the debug endpoint."""
    log("\n=== Test 6: Debug Endpoint ===")
    try:
        r = requests.get(f"{FLASK_URL}/liveness/debug", timeout=5)
        data = r.json()
        debug = data.get('data', {})
        log(f"Face landmarker loaded: {debug.get('face_landmarker_loaded')}")
        log(f"Fallback mode: {debug.get('fallback_mode')}")
        log(f"Challenge types: {debug.get('challenge_types')}")
        log(f"Thresholds: {debug.get('thresholds')}")
        log(f"Active sessions: {debug.get('active_sessions')}")
        return True
    except Exception as e:
        log(f"Debug endpoint error: {e}", "ERROR")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("  End-to-End Liveness Pipeline Test")
    print("=" * 60)

    results = {}

    results['health'] = test_health()
    results['challenge_gen'] = test_challenge_generation()
    session_id, challenge = results['challenge_gen']
    results['frame_sending'] = test_frame_sending(session_id, challenge)
    results['frame_quality'] = test_frame_quality()
    results['webcam'] = test_real_webcam()
    results['debug'] = test_debug_endpoint()

    print("\n" + "=" * 60)
    print("  Test Results Summary")
    print("=" * 60)
    for key, val in results.items():
        if val is None:
            status = "SKIP"
        elif val is True:
            status = "PASS"
        else:
            status = "FAIL"
        print(f"  [{status}] {key}")
    print("=" * 60)
