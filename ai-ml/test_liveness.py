"""Diagnostic test for liveness detection values."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

import cv2
import numpy as np
import time
from liveness_detection import ChallengeLivenessDetector

det = ChallengeLivenessDetector()
print('FaceLandmarker available:', det.face_landmarker is not None)
print('Fallback mode:', det.FALLBACK_MODE)
print('PITCH_MOVE_THRESHOLD:', det.PITCH_MOVE_THRESHOLD)
print('MAR_OPEN_MOUTH_THRESHOLD:', det.MAR_OPEN_MOUTH_THRESHOLD)
print('EAR_THRESHOLD:', det.EAR_THRESHOLD)

cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print('Cannot open webcam')
    sys.exit(1)

print('Webcam opened. Capturing 15 frames (4.5s)...')
print('Please turn your head LEFT and RIGHT and SMILE during capture.')
frames = []
for i in range(15):
    ret, frame = cap.read()
    if ret:
        _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        frames.append(buf.tobytes())
    time.sleep(0.3)
cap.release()

ear_vals = []
mar_vals = []
yaw_vals = []
pitch_vals = []

for i, f in enumerate(frames):
    img = cv2.imdecode(np.frombuffer(f, np.uint8), cv2.IMREAD_COLOR)
    landmarks = det._extract_landmarks_from_image(img)
    if landmarks is not None:
        left_eye_idx = [33, 160, 158, 133, 153, 144]
        right_eye_idx = [362, 385, 387, 263, 373, 380]
        ear = det._compute_ear(landmarks, left_eye_idx, right_eye_idx)
        mar = det._compute_mar(landmarks)
        pose = det._compute_head_pose(landmarks)
        ear_vals.append(ear)
        mar_vals.append(mar)
        yaw_vals.append(pose['yaw'])
        pitch_vals.append(pose['pitch'])
        print('Frame %d: EAR=%.4f MAR=%.4f yaw=%.2f pitch=%.2f' % (i, ear, mar, pose['yaw'], pose['pitch']))
    else:
        print('Frame %d: No face detected' % i)

if ear_vals:
    print('')
    print('EAR range: %.4f - %.4f (std=%.4f)' % (min(ear_vals), max(ear_vals), np.std(ear_vals)))
    print('MAR range: %.4f - %.4f (std=%.4f)' % (min(mar_vals), max(mar_vals), np.std(mar_vals)))
    print('Yaw range: %.2f - %.2f (range=%.2f)' % (min(yaw_vals), max(yaw_vals), max(yaw_vals) - min(yaw_vals)))
    print('Pitch range: %.2f - %.2f (range=%.2f)' % (min(pitch_vals), max(pitch_vals), max(pitch_vals) - min(pitch_vals)))
    wink_left_ok, wink_left_conf = det._verify_wink_left(ear_vals)
    wink_right_ok, wink_right_conf = det._verify_wink_right(ear_vals)
    pass
    open_mouth_ok, open_mouth_conf = det._verify_open_mouth(mar_vals)
    nod_up_ok, nod_up_conf = det._verify_nod_up(pitch_vals) if hasattr(det, '_verify_nod_up') else (False, 0.0)
    nod_down_ok, nod_down_conf = det._verify_nod_down(pitch_vals) if hasattr(det, '_verify_nod_down') else (False, 0.0)
    print('')
    print('Wink left: %s (conf=%.3f)' % (wink_left_ok, wink_left_conf))
    print('Wink right: %s (conf=%.3f)' % (wink_right_ok, wink_right_conf))
    print('Open mouth: %s (conf=%.3f)' % (open_mouth_ok, open_mouth_conf))
    if hasattr(det, '_verify_nod_up'):
        print('Nod up: %s (conf=%.3f)' % (nod_up_ok, nod_up_conf))
    if hasattr(det, '_verify_nod_down'):
        print('Nod down: %s (conf=%.3f)' % (nod_down_ok, nod_down_conf))
else:
    print('No valid frames analyzed')
