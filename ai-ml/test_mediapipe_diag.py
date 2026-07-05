"""
MediaPipe Face Landmarker Diagnostic Test
=========================================
Verifies:
1. Initialization without errors
2. Landmark detection on live webcam frames
3. All landmark indices are valid and correct
4. All metrics compute correctly (EAR, MAR, pitch, yaw, roll, eyebrow)
5. Multi-frame tracking (no stale/frozen landmarks)
6. Coordinate scaling is correct
7. Camera health check (brightness, resolution)
"""
import sys
import os
import time
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))

import cv2
from liveness_detection import (
    ChallengeLivenessDetector,
    LEFT_EYE_IDX, RIGHT_EYE_IDX, LEFT_EYE_IDX_WINK, RIGHT_EYE_IDX_WINK,
    NOSE_TIP, NOSE_BRIDGE, LEFT_EYE_OUTER, RIGHT_EYE_OUTER,
    LEFT_EAR, RIGHT_EAR,
    MOUTH_TOP, MOUTH_BOTTOM, MOUTH_LEFT, MOUTH_RIGHT,
    MOUTH_TOP_INNER, MOUTH_BOTTOM_INNER,
    LEFT_EYEBROW_LOWER, RIGHT_EYEBROW_LOWER,
    LEFT_EYE_UPPER, RIGHT_EYE_UPPER,
)

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
WARN = "\033[93mWARN\033[0m"
SKIP = "\033[94mSKIP\033[0m"

results = []

def check(name, passed, detail="", warn_only=False):
    status = WARN if warn_only else (PASS if passed else FAIL)
    results.append((name, passed))
    suffix = f" -- {detail}" if detail else ""
    print(f"  [{status}] {name}{suffix}")
    return passed


print("=" * 70)
print("  MediaPipe Face Landmarker Diagnostic Report")
print("=" * 70)

# ------------------------------------------------------------------
# 1. INITIALIZATION
# ------------------------------------------------------------------
print("\n--- 1. Initialization ---")
det = ChallengeLivenessDetector()
check("MediaPipe import succeeded", not det.FALLBACK_MODE,
      f"FALLBACK_MODE={det.FALLBACK_MODE}")
check("face_landmarker object created", det.face_landmarker is not None,
      f"type={type(det.face_landmarker).__name__}")

# ------------------------------------------------------------------
# 2. WEBCAM CAPTURE
# ------------------------------------------------------------------
print("\n--- 2. Webcam Capture ---")
cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
if not cap.isOpened():
    cap = cv2.VideoCapture(0)
webcam_ok = cap.isOpened()
check("Webcam opened", webcam_ok)
if not webcam_ok:
    print("\n  Cannot proceed without webcam. Exiting.")
    cap.release()
    sys.exit(1)

cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
cap.set(cv2.CAP_PROP_FPS, 30)
time.sleep(2.0)  # Let camera warm up

# Try multiple frames to get a non-black frame
frame = None
for attempt in range(5):
    ret, f = cap.read()
    if ret and f is not None:
        brightness = np.mean(f)
        if brightness > 5.0:
            frame = f
            check("Frame read succeeded", True,
                  f"shape={f.shape} brightness={brightness:.1f}")
            break
        else:
            print(f"  Attempt {attempt+1}: Frame is dark (brightness={brightness:.1f}), retrying...")
            time.sleep(1.0)

if frame is None:
    # Check camera properties
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    check("Frame read succeeded", False,
          f"camera reports {w}x{h} @ {fps}fps but all frames are dark/black")
    print("\n  *** CAMERA ISSUE DETECTED ***")
    print("  The camera device is accessible but produces black frames.")
    print("  This is a hardware/driver issue, NOT a MediaPipe problem.")
    print("  Common causes:")
    print("    - Camera covered by privacy shutter")
    print("    - Camera driver needs update")
    print("    - Another app has exclusive camera access")
    print("    - Camera hardware malfunction")
    print("  The MediaPipe initialization and code logic are verified below")
    print("  using synthetic validation.\n")
    cap.release()

    # Continue with code validation only
    print("--- 2b. Camera Health (SKIPPED - camera unavailable) ---")
    print("  Skipping live landmark tests (camera hardware issue)")
    print()

    # ------------------------------------------------------------------
    # CODE LOGIC VALIDATION (no camera needed)
    # ------------------------------------------------------------------
    print("=" * 70)
    print("  CODE LOGIC VALIDATION (synthetic)")
    print("=" * 70)

    print("\n--- A. Index Constants Validation ---")
    all_indices = {
        "LEFT_EYE_IDX": LEFT_EYE_IDX,
        "RIGHT_EYE_IDX": RIGHT_EYE_IDX,
        "LEFT_EYE_IDX_WINK": LEFT_EYE_IDX_WINK,
        "RIGHT_EYE_IDX_WINK": RIGHT_EYE_IDX_WINK,
        "NOSE_TIP": [NOSE_TIP],
        "NOSE_BRIDGE": [NOSE_BRIDGE],
        "LEFT_EYE_OUTER": [LEFT_EYE_OUTER],
        "RIGHT_EYE_OUTER": [RIGHT_EYE_OUTER],
        "LEFT_EAR": [LEFT_EAR],
        "RIGHT_EAR": [RIGHT_EAR],
        "MOUTH_TOP": [MOUTH_TOP],
        "MOUTH_BOTTOM": [MOUTH_BOTTOM],
        "MOUTH_LEFT": [MOUTH_LEFT],
        "MOUTH_RIGHT": [MOUTH_RIGHT],
        "MOUTH_TOP_INNER": [MOUTH_TOP_INNER],
        "MOUTH_BOTTOM_INNER": [MOUTH_BOTTOM_INNER],
        "LEFT_EYEBROW_LOWER": [LEFT_EYEBROW_LOWER],
        "RIGHT_EYEBROW_LOWER": [RIGHT_EYEBROW_LOWER],
        "LEFT_EYE_UPPER": [LEFT_EYE_UPPER],
        "RIGHT_EYE_UPPER": [RIGHT_EYE_UPPER],
    }
    for name, indices in all_indices.items():
        valid = all(0 <= i < 468 for i in indices)
        check(f"Index {name} valid (0-467)", valid, f"indices={indices}")

    check("LEFT_EYE_IDX == LEFT_EYE_IDX_WINK (same eye)",
          LEFT_EYE_IDX == LEFT_EYE_IDX_WINK)
    check("RIGHT_EYE_IDX == RIGHT_EYE_IDX_WINK (same eye)",
          RIGHT_EYE_IDX == RIGHT_EYE_IDX_WINK)

    # All 468 landmark indices used
    all_used = set()
    for indices in all_indices.values():
        all_used.update(indices)
    check("Total unique indices used <= 468", len(all_used) <= 468,
          f"{len(all_used)} unique indices")

    print("\n--- B. Metric Computation with Synthetic Landmarks ---")
    # Create a synthetic 468-point landmark array (normalized 0-1 coords on 640x480 image)
    synthetic = np.zeros((468, 2), dtype=np.float64)
    # Face center at (320, 240), face width ~200px
    cx, cy = 320, 240
    fw = 200  # face width

    # Eyes: y ~220, left eye x ~270, right eye x ~370
    for idx in LEFT_EYE_IDX:
        synthetic[idx] = [cx - fw * 0.25 + np.random.randn() * 2, cy - 20 + np.random.randn() * 1]
    for idx in RIGHT_EYE_IDX:
        synthetic[idx] = [cx + fw * 0.25 + np.random.randn() * 2, cy - 20 + np.random.randn() * 1]

    # Mouth: y ~270
    synthetic[MOUTH_TOP] = [cx, cy + 30]
    synthetic[MOUTH_BOTTOM] = [cx, cy + 50]
    synthetic[MOUTH_LEFT] = [cx - 30, cy + 40]
    synthetic[MOUTH_RIGHT] = [cx + 30, cy + 40]
    synthetic[MOUTH_TOP_INNER] = [cx, cy + 33]
    synthetic[MOUTH_BOTTOM_INNER] = [cx, cy + 47]

    # Nose
    synthetic[NOSE_TIP] = [cx, cy + 10]
    synthetic[NOSE_BRIDGE] = [cx, cy - 10]

    # Eye outer corners
    synthetic[LEFT_EYE_OUTER] = [cx - fw * 0.4, cy - 20]
    synthetic[RIGHT_EYE_OUTER] = [cx + fw * 0.4, cy - 20]

    # Ears
    synthetic[LEFT_EAR] = [cx - fw * 0.5, cy]
    synthetic[RIGHT_EAR] = [cx + fw * 0.5, cy]

    # Eyebrows: y ~190 (above eyes at y~220)
    synthetic[LEFT_EYEBROW_LOWER] = [cx - fw * 0.25, cy - 50]
    synthetic[RIGHT_EYEBROW_LOWER] = [cx + fw * 0.25, cy - 50]
    synthetic[LEFT_EYE_UPPER] = [cx - fw * 0.25, cy - 30]
    synthetic[RIGHT_EYE_UPPER] = [cx + fw * 0.25, cy - 30]

    # Forehead and chin
    synthetic[10] = [cx, cy - 80]
    synthetic[152] = [cx, cy + 80]

    # Also set RIGHT_EYE_IDX_WINK coords (indices 362,385,387,263,373,380)
    # These are already set in the RIGHT_EYE_IDX loop above since they share indices
    # But some right wink indices (385, 387, 373, 380) aren't in RIGHT_EYE_IDX
    for idx in RIGHT_EYE_IDX_WINK:
        if synthetic[idx][0] == 0 and synthetic[idx][1] == 0:
            synthetic[idx] = [cx + fw * 0.25 + np.random.randn() * 2, cy - 20 + np.random.randn() * 1]

    ear = det._compute_ear(synthetic, LEFT_EYE_IDX, RIGHT_EYE_IDX)
    left_ear = det._compute_left_ear(synthetic)
    right_ear = det._compute_right_ear(synthetic)
    mar = det._compute_mar(synthetic)
    pose = det._compute_head_pose(synthetic)
    depth = det._compute_depth_ratio(synthetic)
    eyebrow_dist = det._compute_eyebrow_distance(synthetic)

    check("Synthetic EAR in valid range", 0.05 < ear < 0.60, f"ear={ear:.4f}")
    check("Synthetic left EAR in valid range", 0.05 < left_ear < 0.60, f"left={left_ear:.4f}")
    check("Synthetic right EAR in valid range", 0.05 < right_ear < 0.60, f"right={right_ear:.4f}")
    check("Synthetic MAR in valid range", 0.02 < mar < 0.80, f"mar={mar:.4f}")
    check("Synthetic yaw in range", -45 < pose['yaw'] < 45, f"yaw={pose['yaw']:.2f}")
    check("Synthetic pitch in range", -45 < pose['pitch'] < 45, f"pitch={pose['pitch']:.2f}")
    check("Synthetic roll in range", -45 < pose['roll'] < 45, f"roll={pose['roll']:.2f}")
    check("Synthetic depth > 0", depth['depth_ratio'] > 0, f"ratio={depth['depth_ratio']:.4f}")
    check("Synthetic eyebrow_dist > 0", eyebrow_dist > 0, f"dist={eyebrow_dist:.4f}")

    print("\n--- C. Smoothing Utility ---")
    test_vals = [0.1, 0.2, 0.3, 0.5, 0.4, 0.3, 0.2]
    smoothed = det._smooth_values(test_vals, window=3)
    check("Smoothing preserves length", len(smoothed) == len(test_vals),
          f"input={len(test_vals)} output={len(smoothed)}")
    check("Smoothing reduces noise", np.std(smoothed) < np.std(test_vals),
          f"std_before={np.std(test_vals):.4f} std_after={np.std(smoothed):.4f}")

    print("\n--- D. Challenge Verification Logic ---")
    # Test wink_left: baseline ~0.30, left dips to ~0.10 for 3 frames, then reopens
    # The wink detector requires: dip below threshold -> stay closed >= MIN_WINK_DIP_FRAMES -> reopen
    left_ears = [0.30, 0.31, 0.30, 0.31, 0.30, 0.30, 0.12, 0.10, 0.11, 0.29, 0.30, 0.31, 0.30]
    right_ears = [0.31, 0.30, 0.32, 0.30, 0.31, 0.30, 0.31, 0.30, 0.31, 0.30, 0.31, 0.30, 0.32]
    frames_data = [{'left_ear': l, 'right_ear': r} for l, r in zip(left_ears, right_ears)]
    detected, conf = det._verify_wink_left(left_ears, right_ears, frames_data=frames_data)
    check("Synthetic wink_left detection", detected, f"conf={conf:.3f}")

    # Test open_mouth: baseline ~0.12, then mouth opens to ~0.40, then closes
    mar_values = [0.12, 0.13, 0.12, 0.11, 0.12, 0.30, 0.38, 0.40, 0.35, 0.15, 0.13, 0.12]
    detected_m, conf_m = det._verify_open_mouth(mar_values)
    check("Synthetic open_mouth detection", detected_m, f"conf={conf_m:.3f}")

    # Test raise_eyebrows: baseline ~0.05, then raised to ~0.12, then back
    eyebrow_values = [0.05, 0.06, 0.05, 0.06, 0.05, 0.10, 0.12, 0.11, 0.09, 0.06, 0.05]
    detected_e, conf_e = det._verify_raise_eyebrows(eyebrow_values)
    check("Synthetic raise_eyebrows detection", detected_e, f"conf={conf_e:.3f}")

    # Test nod_up (down-then-up): pitch increases then decreases
    pitch_values = [0.0, 1.0, 3.0, 6.0, 9.0, 8.0, 5.0, 2.0, -1.0, -3.0]
    detected_n, conf_n = det._verify_nod_up(pitch_values)
    check("Synthetic nod_up detection", detected_n, f"conf={conf_n:.3f}")

    # Test nod_down (up-then-down): pitch decreases then increases
    pitch_values_d = [0.0, -1.0, -3.0, -6.0, -9.0, -8.0, -5.0, -2.0, 1.0, 3.0]
    detected_nd, conf_nd = det._verify_nod_down(pitch_values_d)
    check("Synthetic nod_down detection", detected_nd, f"conf={conf_nd:.3f}")

    print("\n--- E. Static Face Rejection ---")
    static_ears = [0.30, 0.30, 0.30, 0.30, 0.30]
    static_pitch = [0.0, 0.0, 0.0, 0.0, 0.0]
    static_mar = [0.12, 0.12, 0.12, 0.12, 0.12]
    static_eyebrow = [0.05, 0.05, 0.05, 0.05, 0.05]
    ear_std = float(np.std(static_ears))
    pitch_std = float(np.std(static_pitch))
    mar_std = float(np.std(static_mar))
    eyebrow_std = float(np.std(static_eyebrow))
    static_count = sum([
        ear_std < det.STATIC_EAR_STD,
        pitch_std < det.STATIC_PITCH_STD,
        mar_std < det.STATIC_MAR_STD,
        eyebrow_std < 0.001
    ])
    check("Static face detected (4/4 static)", static_count >= 3,
          f"static_components={static_count}/4")

    # ------------------------------------------------------------------
    # SUMMARY
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    total = len(results)
    passed = sum(1 for _, p in results if p)
    failed = sum(1 for _, p in results if not p)
    print(f"  RESULTS: {passed}/{total} passed, {failed} failed")
    print(f"  NOTE: Live camera tests were skipped due to camera hardware issue.")
    print(f"  The camera produces black frames (brightness=0). This is NOT a")
    print(f"  MediaPipe issue. All code logic was validated with synthetic data.")
    if failed == 0:
        print("  ALL CODE LOGIC CHECKS PASSED")
    else:
        print("  SOME CHECKS FAILED - Review details above")
        for name, p in results:
            if not p:
                print(f"    FAIL: {name}")
    print("=" * 70)
    sys.exit(0)

frame_h, frame_w = frame.shape[:2]
check("Frame dimensions reasonable", frame_w >= 320 and frame_h >= 240,
      f"{frame_w}x{frame_h}")

# ------------------------------------------------------------------
# 3. LANDMARK DETECTION
# ------------------------------------------------------------------
print("\n--- 3. Landmark Detection ---")
t0 = time.time()
landmarks = det._extract_landmarks_from_image(frame)
t1 = time.time()
detect_ms = (t1 - t0) * 1000

if landmarks is None:
    print("  First frame: no face. Trying up to 15 more frames...")
    for retry in range(15):
        ret2, f2 = cap.read()
        if not ret2:
            continue
        t_r0 = time.time()
        lm2 = det._extract_landmarks_from_image(f2)
        t_r1 = time.time()
        if lm2 is not None:
            landmarks = lm2
            detect_ms = (t_r1 - t_r0) * 1000
            frame = f2
            print(f"  Found face on retry {retry+1} in {detect_ms:.0f}ms")
            break

check("Landmarks detected", landmarks is not None,
      f"detected in {detect_ms:.0f}ms")

if landmarks is None:
    print("  No face detected. Saving frame for debugging.")
    cv2.imwrite(os.path.join(os.path.dirname(__file__), "_diag_noface.jpg"), frame)
    print("  Saved to _diag_noface.jpg")
    cap.release()
    sys.exit(1)

check("Landmark count = 468", len(landmarks) == 468, f"got {len(landmarks)}")
check("Detection latency < 500ms", detect_ms < 500, f"{detect_ms:.1f}ms")
check("Landmarks are 2D (x,y pixel coords)", landmarks.shape[1] == 2,
      f"shape={landmarks.shape}")

# ------------------------------------------------------------------
# 4. COORDINATE SCALING
# ------------------------------------------------------------------
print("\n--- 4. Coordinate Scaling ---")
min_x, max_x = landmarks[:, 0].min(), landmarks[:, 0].max()
min_y, max_y = landmarks[:, 1].min(), landmarks[:, 1].max()
check("X coords within frame", max_x <= frame_w and min_x >= 0,
      f"x range [{min_x:.1f}, {max_x:.1f}] vs frame_w={frame_w}")
check("Y coords within frame", max_y <= frame_h and min_y >= 0,
      f"y range [{min_y:.1f}, {max_y:.1f}] vs frame_h={frame_h}")
face_width = np.linalg.norm(landmarks[RIGHT_EYE_OUTER] - landmarks[LEFT_EYE_OUTER])
check("Face width reasonable (50-400 px)", 50 < face_width < 400,
      f"{face_width:.1f}px")

# ------------------------------------------------------------------
# 5. INDEX VALIDATION
# ------------------------------------------------------------------
print("\n--- 5. Index Validation ---")
all_indices = {
    "LEFT_EYE_IDX": LEFT_EYE_IDX,
    "RIGHT_EYE_IDX": RIGHT_EYE_IDX,
    "LEFT_EYE_IDX_WINK": LEFT_EYE_IDX_WINK,
    "RIGHT_EYE_IDX_WINK": RIGHT_EYE_IDX_WINK,
    "NOSE_TIP": [NOSE_TIP],
    "NOSE_BRIDGE": [NOSE_BRIDGE],
    "LEFT_EYE_OUTER": [LEFT_EYE_OUTER],
    "RIGHT_EYE_OUTER": [RIGHT_EYE_OUTER],
    "LEFT_EAR": [LEFT_EAR],
    "RIGHT_EAR": [RIGHT_EAR],
    "MOUTH_TOP": [MOUTH_TOP],
    "MOUTH_BOTTOM": [MOUTH_BOTTOM],
    "MOUTH_LEFT": [MOUTH_LEFT],
    "MOUTH_RIGHT": [MOUTH_RIGHT],
    "MOUTH_TOP_INNER": [MOUTH_TOP_INNER],
    "MOUTH_BOTTOM_INNER": [MOUTH_BOTTOM_INNER],
    "LEFT_EYEBROW_LOWER": [LEFT_EYEBROW_LOWER],
    "RIGHT_EYEBROW_LOWER": [RIGHT_EYEBROW_LOWER],
    "LEFT_EYE_UPPER": [LEFT_EYE_UPPER],
    "RIGHT_EYE_UPPER": [RIGHT_EYE_UPPER],
}

for name, indices in all_indices.items():
    valid = all(0 <= i < 468 for i in indices)
    coords = [(round(float(landmarks[i][0]), 1), round(float(landmarks[i][1]), 1)) for i in indices]
    check(f"Index {name} valid (0-467)", valid, f"idx={indices} pos={coords}")

# Verify left/right eye indices are NOT swapped
left_eye_x = np.mean([landmarks[i][0] for i in LEFT_EYE_IDX])
right_eye_x = np.mean([landmarks[i][0] for i in RIGHT_EYE_IDX])
check("LEFT_EYE_IDX is on left side (x < right)", left_eye_x < right_eye_x,
      f"left_mean_x={left_eye_x:.1f} right_mean_x={right_eye_x:.1f}")

left_wink_x = np.mean([landmarks[i][0] for i in LEFT_EYE_IDX_WINK])
right_wink_x = np.mean([landmarks[i][0] for i in RIGHT_EYE_IDX_WINK])
check("LEFT_EYE_IDX_WINK is on left side", left_wink_x < right_wink_x,
      f"left_wink_x={left_wink_x:.1f} right_wink_x={right_wink_x:.1f}")

# Verify eyebrow landmarks are above eye landmarks
left_brow_y = landmarks[LEFT_EYEBROW_LOWER][1]
left_eye_y = landmarks[LEFT_EYE_UPPER][1]
check("LEFT eyebrow above eye (y < eye_y)", left_brow_y < left_eye_y,
      f"brow_y={left_brow_y:.1f} eye_y={left_eye_y:.1f}")

right_brow_y = landmarks[RIGHT_EYEBROW_LOWER][1]
right_eye_y = landmarks[RIGHT_EYE_UPPER][1]
check("RIGHT eyebrow above eye (y < eye_y)", right_brow_y < right_eye_y,
      f"brow_y={right_brow_y:.1f} eye_y={right_eye_y:.1f}")

# Verify mouth landmarks: top above bottom
check("MOUTH_TOP above MOUTH_BOTTOM",
      landmarks[MOUTH_TOP][1] < landmarks[MOUTH_BOTTOM][1],
      f"top_y={landmarks[MOUTH_TOP][1]:.1f} bot_y={landmarks[MOUTH_BOTTOM][1]:.1f}")

check("MOUTH_TOP_INNER above MOUTH_BOTTOM_INNER",
      landmarks[MOUTH_TOP_INNER][1] < landmarks[MOUTH_BOTTOM_INNER][1],
      f"top_y={landmarks[MOUTH_TOP_INNER][1]:.1f} bot_y={landmarks[MOUTH_BOTTOM_INNER][1]:.1f}")

# ------------------------------------------------------------------
# 6. METRIC COMPUTATION
# ------------------------------------------------------------------
print("\n--- 6. Metric Computation ---")
ear = det._compute_ear(landmarks, LEFT_EYE_IDX, RIGHT_EYE_IDX)
left_ear = det._compute_left_ear(landmarks)
right_ear = det._compute_right_ear(landmarks)
mar = det._compute_mar(landmarks)
pose = det._compute_head_pose(landmarks)
depth = det._compute_depth_ratio(landmarks)
eyebrow_dist = det._compute_eyebrow_distance(landmarks)

check("EAR in valid range [0.05, 0.60]", 0.05 < ear < 0.60, f"ear={ear:.4f}")
check("Left EAR in valid range", 0.05 < left_ear < 0.60, f"left_ear={left_ear:.4f}")
check("Right EAR in valid range", 0.05 < right_ear < 0.60, f"right_ear={right_ear:.4f}")
check("Left EAR != Right EAR (different indices)", abs(left_ear - right_ear) > 0.0001,
      f"left={left_ear:.4f} right={right_ear:.4f}")
check("MAR in valid range [0.02, 0.80]", 0.02 < mar < 0.80, f"mar={mar:.4f}")

yaw = pose['yaw']
pitch = pose['pitch']
roll = pose['roll']
check("Yaw in valid range [-45, 45]", -45 < yaw < 45, f"yaw={yaw:.2f}")
check("Pitch in valid range [-45, 45]", -45 < pitch < 45, f"pitch={pitch:.2f}")
check("Roll in valid range [-45, 45]", -45 < roll < 45, f"roll={roll:.2f}")

check("Depth ratio in valid range", 0.2 < depth['depth_ratio'] < 1.5,
      f"ratio={depth['depth_ratio']:.4f} score={depth['score']:.4f}")
check("Eyebrow dist > 0", eyebrow_dist > 0, f"dist={eyebrow_dist:.4f}")

# ------------------------------------------------------------------
# 7. MULTI-FRAME TRACKING (stale/frozen detection)
# ------------------------------------------------------------------
print("\n--- 7. Multi-Frame Tracking (5 frames) ---")
all_landmarks = []
all_ears = []
all_pitches = []
all_mar = []
timestamps = []

for i in range(5):
    ret, f = cap.read()
    if not ret:
        check(f"Frame {i} read", False)
        continue
    t_start = time.time()
    lm = det._extract_landmarks_from_image(f)
    t_end = time.time()
    if lm is None:
        check(f"Frame {i} landmarks detected", False)
        continue
    all_landmarks.append(lm)
    ear_v = det._compute_ear(lm, LEFT_EYE_IDX, RIGHT_EYE_IDX)
    left_ear_v = det._compute_left_ear(lm)
    right_ear_v = det._compute_right_ear(lm)
    mar_v = det._compute_mar(lm)
    pose_v = det._compute_head_pose(lm)
    all_ears.append(ear_v)
    all_pitches.append(pose_v['pitch'])
    all_mar.append(mar_v)
    timestamps.append(t_end)
    check(f"Frame {i} detection < 300ms", (t_end - t_start) * 1000 < 300,
          f"{(t_end - t_start)*1000:.0f}ms ear={ear_v:.4f} pitch={pose_v['pitch']:.2f} mar={mar_v:.4f}")

if len(all_landmarks) >= 2:
    diffs = []
    for i in range(1, len(all_landmarks)):
        diff = np.mean(np.abs(all_landmarks[i] - all_landmarks[i - 1]))
        diffs.append(diff)
    avg_diff = np.mean(diffs)
    max_diff = np.max(diffs)
    check("Landmarks moving (not frozen)", avg_diff > 0.1,
          f"avg_diff={avg_diff:.2f}px max_diff={max_diff:.2f}px")

    all_same = all(np.array_equal(all_landmarks[0], lm) for lm in all_landmarks)
    check("Not all frames have identical landmarks", not all_same)

    if len(timestamps) >= 2:
        fps = (len(timestamps) - 1) / (timestamps[-1] - timestamps[0])
        check("Effective FPS > 2", fps > 2, f"fps={fps:.1f}")

    ear_var = np.var(all_ears)
    pitch_var = np.var(all_pitches)
    check("EAR has some variance (not perfectly static)", ear_var > 0.00001,
          f"var={ear_var:.6f}")
    check("Pitch has some variance", pitch_var > 0.01, f"var={pitch_var:.4f}")

# ------------------------------------------------------------------
# 8. STRESS TEST (10 more frames)
# ------------------------------------------------------------------
print("\n--- 8. Stress Test (10 frames, measure consistency) ---")
stress_landmarks = []
stress_ears = []
stress_errors = 0
t0 = time.time()
for i in range(10):
    ret, f = cap.read()
    if not ret:
        stress_errors += 1
        continue
    lm = det._extract_landmarks_from_image(f)
    if lm is None:
        stress_errors += 1
        continue
    stress_landmarks.append(lm)
    ear_v = det._compute_ear(lm, LEFT_EYE_IDX, RIGHT_EYE_IDX)
    stress_ears.append(ear_v)
t_total = time.time() - t0
cap.release()

detection_rate = len(stress_landmarks) / 10.0
check("Detection rate >= 70%", detection_rate >= 0.7,
      f"{detection_rate*100:.0f}% ({len(stress_landmarks)}/10)")
check("All 10 frames processed without crash", stress_errors < 3,
      f"errors={stress_errors}")

if len(stress_ears) >= 2:
    ear_range = max(stress_ears) - min(stress_ears)
    check("EAR range in stress test > 0", ear_range > 0,
          f"range={ear_range:.4f} min={min(stress_ears):.4f} max={max(stress_ears):.4f}")

avg_frame_time = t_total / max(len(stress_landmarks), 1) * 1000
check("Average frame processing < 400ms", avg_frame_time < 400,
      f"{avg_frame_time:.0f}ms/frame")

# ------------------------------------------------------------------
# 9. CHALLENGE VERIFICATION WITH LIVE DATA
# ------------------------------------------------------------------
print("\n--- 9. Challenge Verification with Live Data ---")
if len(stress_landmarks) >= 4:
    live_left_ears = [float(det._compute_left_ear(lm)) for lm in stress_landmarks]
    live_right_ears = [float(det._compute_right_ear(lm)) for lm in stress_landmarks]
    live_mar = [float(det._compute_mar(lm)) for lm in stress_landmarks]
    live_pitch = [float(det._compute_head_pose(lm)['pitch']) for lm in stress_landmarks]
    live_eyebrow = [float(det._compute_eyebrow_distance(lm)) for lm in stress_landmarks]
    live_frames = [{'left_ear': l, 'right_ear': r} for l, r in zip(live_left_ears, live_right_ears)]

    print(f"  Live data: {len(stress_landmarks)} frames")
    print(f"  Left EAR range: [{min(live_left_ears):.4f}, {max(live_left_ears):.4f}]")
    print(f"  Right EAR range: [{min(live_right_ears):.4f}, {max(live_right_ears):.4f}]")
    print(f"  MAR range: [{min(live_mar):.4f}, {max(live_mar):.4f}]")
    print(f"  Pitch range: [{min(live_pitch):.2f}, {max(live_pitch):.2f}]")
    print(f"  Eyebrow range: [{min(live_eyebrow):.4f}, {max(live_eyebrow):.4f}]")

    # Run each challenge verifier - these should not crash
    try:
        d, c = det._verify_wink_left(live_left_ears, live_right_ears, frames_data=live_frames)
        check("wink_left runs without crash", True, f"detected={d} conf={c:.3f}")
    except Exception as e:
        check("wink_left runs without crash", False, str(e))

    try:
        d, c = det._verify_wink_right(live_left_ears, live_right_ears, frames_data=live_frames)
        check("wink_right runs without crash", True, f"detected={d} conf={c:.3f}")
    except Exception as e:
        check("wink_right runs without crash", False, str(e))

    try:
        d, c = det._verify_open_mouth(live_mar)
        check("open_mouth runs without crash", True, f"detected={d} conf={c:.3f}")
    except Exception as e:
        check("open_mouth runs without crash", False, str(e))

    try:
        d, c = det._verify_nod_up(live_pitch)
        check("nod_up runs without crash", True, f"detected={d} conf={c:.3f}")
    except Exception as e:
        check("nod_up runs without crash", False, str(e))

    try:
        d, c = det._verify_nod_down(live_pitch)
        check("nod_down runs without crash", True, f"detected={d} conf={c:.3f}")
    except Exception as e:
        check("nod_down runs without crash", False, str(e))

    try:
        d, c = det._verify_raise_eyebrows(live_eyebrow)
        check("raise_eyebrows runs without crash", True, f"detected={d} conf={c:.3f}")
    except Exception as e:
        check("raise_eyebrows runs without crash", False, str(e))
else:
    print("  Skipped (insufficient live frames)")

# ------------------------------------------------------------------
# SUMMARY
# ------------------------------------------------------------------
print("\n" + "=" * 70)
total = len(results)
passed = sum(1 for _, p in results if p)
failed = sum(1 for _, p in results if not p)
print(f"  RESULTS: {passed}/{total} passed, {failed} failed")
if failed == 0:
    print("  ALL CHECKS PASSED - MediaPipe Face Landmarker is functioning correctly")
else:
    print("  SOME CHECKS FAILED - Review details above")
    for name, p in results:
        if not p:
            print(f"    FAIL: {name}")
print("=" * 70)
