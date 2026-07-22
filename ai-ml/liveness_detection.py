"""
Liveness Detection Module for Digital KYC System

Challenge-response liveness detection using MediaPipe FaceLandmarker.
Verifies real human presence through 6 simple interactive challenges:
- Blink: both eyes close and reopen (EAR-based)
- Open Mouth: mouth opens (MAR-based)
- Smile: mouth corners widen (mouth width / face width)
- Head Turn Left: yaw changes left and returns
- Head Turn Right: yaw changes right and returns
- Look Up: pitch changes upward and returns

Each challenge uses:
- Baseline initialization from neutral face
- Movement detection relative to baseline
- Sustained movement over multiple frames (no single-frame spikes)
- Frame averaging for stability
"""

import cv2
import numpy as np
import base64
import os
import logging
import time
import random
import hashlib
from datetime import datetime, timedelta
from collections import deque

logger = logging.getLogger(__name__)

try:
    import mediapipe as mp
    HAS_MEDIAPIPE = True
    from mediapipe.tasks import python as mp_tasks
    from mediapipe.tasks.python import vision as mp_vision
except ImportError:
    HAS_MEDIAPIPE = False
    mp_tasks = None
    mp_vision = None

FACE_LANDMARKER_MODEL_PATH = None
POSE_LANDMARKER_MODEL_PATH = None


def _ensure_face_landmarker_model():
    """Download face_landmarker.task from MediaPipe hub if not present."""
    global FACE_LANDMARKER_MODEL_PATH
    if FACE_LANDMARKER_MODEL_PATH and os.path.exists(FACE_LANDMARKER_MODEL_PATH):
        return FACE_LANDMARKER_MODEL_PATH

    import tempfile
    possible_paths = [
        os.path.join(os.path.dirname(__file__), 'models', 'face_landmarker.task'),
        os.path.join(tempfile.gettempdir(), 'mediapipe_models', 'face_landmarker.task'),
    ]

    for p in possible_paths:
        expanded = os.path.expanduser(os.path.expandvars(p))
        if os.path.exists(expanded):
            FACE_LANDMARKER_MODEL_PATH = expanded
            return expanded

    model_url = (
        'https://storage.googleapis.com/mediapipe-models/face_landmarker/'
        'face_landmarker/float16/latest/face_landmarker.task'
    )
    dest_dir = os.path.join(tempfile.gettempdir(), 'mediapipe_models')
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, 'face_landmarker.task')

    try:
        import urllib.request
        logger.info("[MediaPipe] Downloading face_landmarker.task model...")
        urllib.request.urlretrieve(model_url, dest_path)
        logger.info("[MediaPipe] Model downloaded to %s", dest_path)
        FACE_LANDMARKER_MODEL_PATH = dest_path
        return dest_path
    except Exception as e:
        logger.error("[MediaPipe] Failed to download model: %s", e)
        return None


def _ensure_pose_landmarker_model():
    """Download pose_landmarker.task from MediaPipe hub if not present."""
    global POSE_LANDMARKER_MODEL_PATH
    if POSE_LANDMARKER_MODEL_PATH and os.path.exists(POSE_LANDMARKER_MODEL_PATH):
        return POSE_LANDMARKER_MODEL_PATH

    import tempfile
    possible_paths = [
        os.path.join(os.path.dirname(__file__), 'models', 'pose_landmarker.task'),
        os.path.join(tempfile.gettempdir(), 'mediapipe_models', 'pose_landmarker.task'),
    ]

    for p in possible_paths:
        expanded = os.path.expanduser(os.path.expandvars(p))
        if os.path.exists(expanded):
            POSE_LANDMARKER_MODEL_PATH = expanded
            return expanded

    model_url = (
        'https://storage.googleapis.com/mediapipe-models/pose_landmarker/'
        'pose_landmarker_lite/float16/latest/pose_landmarker_lite.task'
    )
    dest_dir = os.path.join(tempfile.gettempdir(), 'mediapipe_models')
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, 'pose_landmarker.task')

    try:
        import urllib.request
        logger.info("[MediaPipe] Downloading pose_landmarker.task model...")
        urllib.request.urlretrieve(model_url, dest_path)
        logger.info("[MediaPipe] Pose model downloaded to %s", dest_path)
        POSE_LANDMARKER_MODEL_PATH = dest_path
        return dest_path
    except Exception as e:
        logger.error("[MediaPipe] Failed to download pose model: %s", e)
        return None


# ============================================================
# CHALLENGE TYPES — 8 challenges (6 face + 2 hand)
# ============================================================
CHALLENGE_TYPES = ['blink', 'open_mouth', 'shake_head', 'look_left', 'look_right', 'look_up', 'raise_one_hand', 'raise_both_hands']
CHALLENGE_PROMPTS = {
    'blink':             'Blink both eyes',
    'open_mouth':        'Open your mouth',
    'shake_head':        'Shake your head no',
    'look_left':         'Look to your left',
    'look_right':        'Look to your right',
    'look_up':           'Look up',
    'raise_one_hand':    'Raise one hand above your shoulder',
    'raise_both_hands':  'Raise both hands above your shoulders',
}
CHALLENGE_TIMEOUT_SECONDS = 180
MIN_FRAMES_FOR_CHALLENGE = 8
HAND_SHOULDER_Y_THRESHOLD = 0.45  # wrist y < shoulder y means hand is raised (y increases downward)
HAND_HOLD_FRAMES = 12             # frames hand must be held above shoulder (~2 seconds at 6fps)

# ============================================================
# MediaPipe face landmark indices
# ============================================================
LEFT_EYE_IDX  = [33, 160, 158, 133, 153, 144]
RIGHT_EYE_IDX = [362, 385, 387, 263, 373, 380]

NOSE_TIP = 4
LEFT_EYE_OUTER = 33
RIGHT_EYE_OUTER = 263

MOUTH_TOP = 13
MOUTH_BOTTOM = 14
MOUTH_LEFT = 78
MOUTH_RIGHT = 308
MOUTH_TOP_INNER = 82
MOUTH_BOTTOM_INNER = 87


class ChallengeLivenessDetector:
    """Interactive challenge-response liveness detection using MediaPipe FaceMesh + Pose."""

    # --- Thresholds (tuned for real-world webcam 640x480 @ 6-10 fps) ---
    EAR_CLOSED_THRESHOLD = 0.12   # EAR below this = eye closed (stricter)
    MAR_OPEN_THRESHOLD = 0.18     # MAR above this = mouth open (stricter)
    SHAKE_YAW_DEGREES = 10.0      # min yaw deviation for shake (stricter)
    LOOK_YAW_DEGREES = 10.0       # min yaw change for gaze look left/right (stricter)
    PITCH_UP_DEGREES = 10.0       # min pitch change for look up (stricter)

    # --- Shake head state machine ---
    SHAKE_MIN_PHASES = 2          # need at least 2 transitions (LEFT->RIGHT or RIGHT->LEFT)
    SHAKE_MIN_FRAMES_PER_PHASE = 2 # min frames in each phase to count

    # --- Sustained movement ---
    MIN_SUSTAINED_FRAMES = 5      # require 5 frames meeting criteria (stricter)
    BASELINE_FRAMES = 8           # frames to average for baseline (stricter)
    RECOVERY_FRAMES = 3           # frames to confirm return to neutral

    # --- Hand detection thresholds ---
    HAND_SHOULDER_Y_THRESHOLD = HAND_SHOULDER_Y_THRESHOLD
    HAND_HOLD_FRAMES = HAND_HOLD_FRAMES

    def __init__(self):
        self.face_landmarker = None
        self.pose_landmarker = None
        self.FALLBACK_MODE = False

        try:
            if not HAS_MEDIAPIPE or mp_vision is None:
                logger.info("[INFO] MediaPipe unavailable -- fallback mode enabled")
                self.FALLBACK_MODE = True
                return

            model_path = _ensure_face_landmarker_model()
            if not model_path:
                logger.warning("[MediaPipe] Face landmarker model not available -- fallback mode")
                self.FALLBACK_MODE = True
                return

            base = mp_tasks.BaseOptions(model_asset_path=model_path)
            options = mp_vision.FaceLandmarkerOptions(
                base_options=base, num_faces=1,
                min_face_detection_confidence=0.3,
                min_face_presence_confidence=0.3,
                min_tracking_confidence=0.3,
            )
            self.face_landmarker = mp_vision.FaceLandmarker.create_from_options(options)
            logger.info("ChallengeLivenessDetector initialized with FaceLandmarker")

            # Initialize Pose landmarker for hand challenges
            try:
                pose_model_path = _ensure_pose_landmarker_model()
                if pose_model_path:
                    pose_base = mp_tasks.BaseOptions(model_asset_path=pose_model_path)
                    pose_options = mp_vision.PoseLandmarkerOptions(
                        base_options=pose_base, num_poses=1,
                        min_pose_detection_confidence=0.3,
                        min_pose_presence_confidence=0.3,
                        min_tracking_confidence=0.3,
                    )
                    self.pose_landmarker = mp_vision.PoseLandmarker.create_from_options(pose_options)
                    logger.info("PoseLandmarker initialized for hand challenges")
                else:
                    logger.warning("Pose landmarker model not available -- hand challenges disabled")
            except Exception as e:
                logger.warning("PoseLandmarker init failed: %s -- hand challenges disabled", e)

        except Exception as e:
            logger.warning("ChallengeLivenessDetector init failed (%s) -- fallback mode", e)
            self.FALLBACK_MODE = True

    # ============================================================
    # CHALLENGE GENERATION
    # ============================================================

    def _make_challenge_dict(self, action_type, nonce=None):
        if nonce is None:
            nonce = hashlib.sha256(
                f"{datetime.utcnow().isoformat()}-{random.random()}".encode()
            ).hexdigest()[:16]
        token_source = f"{action_type}-{nonce}-{datetime.utcnow().isoformat()}"
        token = hashlib.sha256(token_source.encode()).hexdigest()[:32]
        return {
            'challenge_type': action_type,
            'challenge_sequence': [action_type],
            'prompt': CHALLENGE_PROMPTS[action_type],
            'token': token,
            'nonce': nonce,
            'created_at': datetime.utcnow().isoformat(),
            'expires_at': (datetime.utcnow() + timedelta(seconds=CHALLENGE_TIMEOUT_SECONDS)).isoformat(),
            'min_frames': MIN_FRAMES_FOR_CHALLENGE * 2,
            'timeout_seconds': CHALLENGE_TIMEOUT_SECONDS,
            'sequence_length': 1,
        }

    def generate_challenge(self):
        action = random.choice(CHALLENGE_TYPES)
        return self._make_challenge_dict(action)

    def generate_challenge_session(self):
        actions = random.sample(CHALLENGE_TYPES, k=4)
        nonce = hashlib.sha256(
            f"{datetime.utcnow().isoformat()}-{random.random()}".encode()
        ).hexdigest()[:16]
        return [self._make_challenge_dict(a, nonce) for a in actions]

    def evaluate_session(self, session_results):
        completed = sum(1 for r in session_results if r.get('challenge_passed', False))
        total = len(session_results)
        all_passed = (completed == total)
        passed_results = [r for r in session_results if r.get('challenge_passed', False)]
        confidences = [r.get('confidence', 0) for r in session_results]
        avg_confidence = float(np.mean(confidences)) if confidences else 0.0
        if passed_results:
            passed_confidences = [r.get('confidence', 0) for r in passed_results]
            avg_passed_confidence = float(np.mean(passed_confidences))
        else:
            avg_passed_confidence = 0.0
        reasons = []
        for r in session_results:
            if not r.get('challenge_passed', False):
                reason = r.get('reason', 'Challenge failed')
                if reason not in reasons:
                    reasons.append(reason)
        details = [
            {
                'challenge': r.get('challenge_type', 'unknown'),
                'passed': bool(r.get('challenge_passed', False)),
                'confidence': round(r.get('confidence', 0), 3),
            }
            for r in session_results
        ]
        if all_passed:
            liveness_score = round(avg_confidence * 0.7 + 1.0 * 0.3, 4)
        elif passed_results:
            liveness_score = round(avg_passed_confidence * 0.7 + 0.0 * 0.3, 4)
        else:
            liveness_score = 0.0
        return {
            'passed': bool(all_passed),
            'challengeCount': total,
            'completedChallenges': completed,
            'challengePassed': bool(all_passed),
            'livenessScore': liveness_score,
            'verified': bool(all_passed),
            'verdict': 'APPROVED' if all_passed else 'REJECTED',
            'reasons': reasons if reasons else None,
            'details': details,
        }

    # ============================================================
    # LANDMARK EXTRACTION
    # ============================================================

    def _extract_landmarks_from_image(self, img):
        if self.FALLBACK_MODE or self.face_landmarker is None:
            return None
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        results = self.face_landmarker.detect(mp_image)
        if not results or not results.face_landmarks:
            return None
        landmarks = results.face_landmarks[0]
        h, w = img.shape[:2]
        return np.array([(lm.x * w, lm.y * h) for lm in landmarks])

    # ============================================================
    # METRIC COMPUTATION
    # ============================================================

    def _compute_left_ear(self, points):
        eye = points[LEFT_EYE_IDX]
        v1 = np.linalg.norm(eye[1] - eye[5])
        v2 = np.linalg.norm(eye[2] - eye[4])
        h1 = np.linalg.norm(eye[0] - eye[3])
        return (v1 + v2) / (2.0 * h1 + 1e-6)

    def _compute_right_ear(self, points):
        eye = points[RIGHT_EYE_IDX]
        v1 = np.linalg.norm(eye[1] - eye[5])
        v2 = np.linalg.norm(eye[2] - eye[4])
        h1 = np.linalg.norm(eye[0] - eye[3])
        return (v1 + v2) / (2.0 * h1 + 1e-6)

    def _compute_avg_ear(self, points):
        return (self._compute_left_ear(points) + self._compute_right_ear(points)) / 2.0

    def _compute_mar(self, points):
        top    = points[MOUTH_TOP]
        bottom = points[MOUTH_BOTTOM]
        left   = points[MOUTH_LEFT]
        right  = points[MOUTH_RIGHT]
        top_in = points[MOUTH_TOP_INNER]
        bot_in = points[MOUTH_BOTTOM_INNER]
        vert = np.linalg.norm(top - bottom) + np.linalg.norm(top_in - bot_in)
        horiz = np.linalg.norm(left - right) + 1e-6
        return (vert / 2.0) / horiz

    def _compute_mouth_width_ratio(self, points):
        """Mouth corner distance normalized by face width."""
        face_width = np.linalg.norm(points[RIGHT_EYE_OUTER] - points[LEFT_EYE_OUTER])
        if face_width < 1e-6:
            return 0.0
        mouth_width = np.linalg.norm(points[MOUTH_RIGHT] - points[MOUTH_LEFT])
        return mouth_width / face_width

    def _compute_head_pose(self, points):
        """Compute yaw and pitch using eye center as stable reference."""
        nose_tip = points[NOSE_TIP]
        left_eye = points[LEFT_EYE_OUTER]
        right_eye = points[RIGHT_EYE_OUTER]

        face_width = np.linalg.norm(right_eye - left_eye)
        if face_width < 1e-6:
            return 0.0, 0.0

        eye_center = (left_eye + right_eye) / 2.0
        eye_vec = right_eye - left_eye
        eye_len = np.linalg.norm(eye_vec)
        if eye_len < 1e-6:
            return 0.0, 0.0

        horiz_axis = eye_vec / eye_len
        vert_axis = np.array([-horiz_axis[1], horiz_axis[0]])

        nose_offset = nose_tip - eye_center
        yaw_proj = float(np.dot(nose_offset, horiz_axis) / face_width)
        pitch_proj = float(np.dot(nose_offset, vert_axis) / face_width)

        yaw = float(np.degrees(np.arctan2(yaw_proj, 0.5)))
        pitch = float(np.degrees(np.arctan2(pitch_proj, 0.5)))
        return yaw, pitch

    def _smooth_values(self, values, window=3):
        arr = np.asarray(values, dtype=np.float64)
        n = len(arr)
        if n < window:
            return arr
        kernel = np.ones(window) / window
        smoothed = np.convolve(arr, kernel, mode='valid')
        pad = window // 2
        if pad > 0:
            left = np.full(pad, arr[0])
            right = np.full(window - 1 - pad, arr[-1])
            return np.concatenate([left, smoothed, right])
        return smoothed

    @staticmethod
    def _to_native(obj):
        if isinstance(obj, dict):
            return {k: ChallengeLivenessDetector._to_native(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [ChallengeLivenessDetector._to_native(v) for v in obj]
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return obj

    # ============================================================
    # MAIN VERIFY ENTRY POINT
    # ============================================================

    def verify_challenge(self, challenge_data, frames_base64):
        """Verify a single challenge from captured frames."""
        result = {
            'challenge_passed': False,
            'challenge_type': challenge_data.get('challenge_type', 'unknown'),
            'action_detected': False,
            'confidence': 0.0,
            'details': {},
            'frames_analyzed': len(frames_base64) if frames_base64 is not None else 0,
            'reason': ''
        }

        frames_base64 = frames_base64 or []

        if self.FALLBACK_MODE or not self.face_landmarker:
            return self._verify_fallback(challenge_data, frames_base64, result)

        challenge_type = challenge_data.get('challenge_type')
        is_hand_challenge = challenge_type in ('raise_one_hand', 'raise_both_hands')

        if is_hand_challenge:
            return self._verify_hand_challenge(challenge_data, frames_base64, result)

        frames_data = []
        total_frames = len(frames_base64)
        lost_landmark_frames = 0
        dark_frame_count = 0

        for idx, frame_b64 in enumerate(frames_base64):
            try:
                if isinstance(frame_b64, str) and ',' in frame_b64:
                    frame_b64 = frame_b64.split(',')[1]
                img_bytes = base64.b64decode(frame_b64)
                nparr = np.frombuffer(img_bytes, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is None:
                    lost_landmark_frames += 1
                    continue

                brightness = float(np.mean(img))
                if brightness < 5.0:
                    dark_frame_count += 1

                landmarks = self._extract_landmarks_from_image(img)
                if landmarks is None:
                    lost_landmark_frames += 1
                    continue

                left_ear = self._compute_left_ear(landmarks)
                right_ear = self._compute_right_ear(landmarks)
                avg_ear = (left_ear + right_ear) / 2.0
                mar = self._compute_mar(landmarks)
                mouth_width_ratio = self._compute_mouth_width_ratio(landmarks)
                yaw, pitch = self._compute_head_pose(landmarks)

                frames_data.append({
                    'left_ear': left_ear,
                    'right_ear': right_ear,
                    'avg_ear': avg_ear,
                    'mar': mar,
                    'mouth_width_ratio': mouth_width_ratio,
                    'yaw': yaw,
                    'pitch': pitch,
                })

                if idx < 3 or idx % 5 == 0:
                    logger.info(
                        "[FRAME] idx=%d challenge=%s L_EAR=%.4f R_EAR=%.4f MAR=%.4f "
                        "mouth_w=%.4f yaw=%.2f pitch=%.2f brightness=%.0f",
                        idx, challenge_type, left_ear, right_ear, mar,
                        mouth_width_ratio, yaw, pitch, brightness
                    )
            except Exception as e:
                lost_landmark_frames += 1
                continue

        if dark_frame_count > total_frames * 0.5:
            result['reason'] = (
                f'Camera producing dark frames ({dark_frame_count}/{total_frames}). '
                f'Please ensure your camera is not covered.'
            )
            result['details'] = {'verdict': 'DARK_FRAMES'}
            return self._to_native(result)

        if len(frames_data) < MIN_FRAMES_FOR_CHALLENGE:
            result['reason'] = (
                f'Insufficient valid frames ({len(frames_data)}/{MIN_FRAMES_FOR_CHALLENGE}) '
                f'- lost landmarks in {lost_landmark_frames}/{total_frames} frames'
            )
            result['details'] = {
                'valid_frames': len(frames_data),
                'total_frames': total_frames,
            }
            return self._to_native(result)

        result['details']['valid_frames'] = len(frames_data)
        result['details']['total_frames'] = total_frames

        detected, confidence, reason = self._verify_action(challenge_type, frames_data)

        result['action_detected'] = detected
        result['challenge_passed'] = detected
        result['confidence'] = round(confidence, 3)
        result['reason'] = reason
        result['details']['challenge_type'] = challenge_type
        result['details']['decision'] = 'passed' if detected else 'rejected'

        if detected:
            logger.info("[CHALLENGE_PASS] type=%s conf=%.3f reason=%s", challenge_type, confidence, reason)
        else:
            logger.warning("[CHALLENGE_FAIL] type=%s reason=%s", challenge_type, reason)

        return self._to_native(result)

    # ============================================================
    # ACTION DISPATCH
    # ============================================================

    def _verify_action(self, action, frames_data):
        dispatch = {
            'blink':             self._verify_blink,
            'open_mouth':        self._verify_open_mouth,
            'shake_head':        self._verify_shake_head,
            'look_left':         self._verify_look_left,
            'look_right':        self._verify_look_right,
            'look_up':           self._verify_look_up,
            'raise_one_hand':    self._verify_raise_one_hand,
            'raise_both_hands':  self._verify_raise_both_hands,
        }
        fn = dispatch.get(action)
        if fn is None:
            return False, 0.0, f'Unknown challenge type: {action}'
        return fn(frames_data)

    # ============================================================
    # CHALLENGE: BLINK (event-based, 3 blinks required)
    # ============================================================

    def _verify_blink(self, frames_data):
        """Detect 3 valid blink events using EAR-based state machine.

        Event = OPEN -> CLOSED -> OPEN transition.
        Each blink is tracked independently with timing.
        Challenge passes after 3 valid blinks.
        """
        tag = "[BLINK]"
        n = len(frames_data)
        if n < MIN_FRAMES_FOR_CHALLENGE:
            return False, 0.0, f'Insufficient frames ({n}/{MIN_FRAMES_FOR_CHALLENGE})'

        REQUIRED_BLINKS = 2
        MIN_BLINK_FRAMES = 1  # each blink must last at least 1 frame

        ear_values = [f['avg_ear'] for f in frames_data]
        left_ears = [f['left_ear'] for f in frames_data]
        right_ears = [f['right_ear'] for f in frames_data]

        # Baseline from first few frames
        baseline_end = min(self.BASELINE_FRAMES, n)
        baseline_ear = float(np.mean(ear_values[:baseline_end]))
        baseline_left = float(np.mean(left_ears[:baseline_end]))
        baseline_right = float(np.mean(right_ears[:baseline_end]))

        # Threshold: eye closed when EAR drops below 60% of baseline or absolute threshold
        closed_threshold = min(self.EAR_CLOSED_THRESHOLD, baseline_ear * 0.60)
        # Reopen threshold: slightly higher than close threshold to avoid noise
        open_threshold = closed_threshold * 1.15

        logger.info("%s frames=%d baseline_ear=%.4f closed_thresh=%.4f open_thresh=%.4f required_blinks=%d",
                     tag, n, baseline_ear, closed_threshold, open_threshold, REQUIRED_BLINKS)

        # State machine: track open/closed transitions
        blink_count = 0
        is_closed = False
        closed_start_frame = -1
        blink_events = []  # list of (start_frame, end_frame, min_ear, duration_frames)

        for i in range(baseline_end, n):
            # Use average of left and right EAR for robustness
            ear = ear_values[i]
            left_closed = left_ears[i] < closed_threshold
            right_closed = right_ears[i] < closed_threshold
            either_closed = left_closed or right_closed
            either_open = (left_ears[i] > open_threshold) or (right_ears[i] > open_threshold)

            if not is_closed and either_closed:
                # Transition: OPEN -> CLOSED
                is_closed = True
                closed_start_frame = i

            elif is_closed and either_open:
                # Transition: CLOSED -> OPEN — one blink event complete
                is_closed = False
                duration = i - closed_start_frame
                if duration < MIN_BLINK_FRAMES:
                    # Too short — noise, not a real blink
                    continue
                # Get minimum EAR during this blink
                blink_ears = ear_values[closed_start_frame:i+1]
                min_ear = float(np.min(blink_ears)) if blink_ears else ear

                blink_count += 1
                blink_events.append({
                    'blink': blink_count,
                    'start_frame': closed_start_frame,
                    'end_frame': i,
                    'duration_frames': duration,
                    'min_ear': min_ear,
                })

                logger.info("%s BLINK #%d detected: frames %d->%d (%d frames) min_ear=%.4f",
                             tag, blink_count, closed_start_frame, i, duration, min_ear)

                # Check if we have enough blinks
                if blink_count >= REQUIRED_BLINKS:
                    # Calculate confidence based on blink quality
                    avg_min_ear = float(np.mean([e['min_ear'] for e in blink_events]))
                    avg_duration = float(np.mean([e['duration_frames'] for e in blink_events]))
                    dip_ratio = (baseline_ear - avg_min_ear) / (baseline_ear + 1e-6)
                    confidence = min(1.0, 0.4 + dip_ratio * 0.3 + min(avg_duration / 5.0, 1.0) * 0.3)

                    logger.info("%s PASS: %d blinks detected, avg_min_ear=%.4f avg_duration=%.1f conf=%.3f",
                                 tag, blink_count, avg_min_ear, avg_duration, confidence)

                    return True, round(confidence, 3), (
                        f'{REQUIRED_BLINKS} blinks detected '
                        f'(avg EAR {baseline_ear:.3f}->{avg_min_ear:.3f}, '
                        f'avg duration {avg_duration:.1f} frames)'
                    )

        # Did not complete required blinks
        if blink_count > 0:
            avg_ear_during_blinks = float(np.mean([e['min_ear'] for e in blink_events]))
            logger.info("%s FAIL: only %d/%d blinks detected, still %s",
                         tag, blink_count, REQUIRED_BLINKS,
                         "CLOSED" if is_closed else "OPEN")
            return False, 0.0, (
                f'Only {blink_count}/{REQUIRED_BLINKS} blinks detected '
                f'(last state: {"closed" if is_closed else "open"})'
            )
        else:
            logger.info("%s FAIL: no blinks detected (min EAR=%.4f, closed_thresh=%.4f)",
                         tag, float(np.min(ear_values[baseline_end:])), closed_threshold)
            return False, 0.0, (
                f'No blinks detected '
                f'(EAR range {float(np.min(ear_values[baseline_end:])):.4f} to '
                f'{float(np.max(ear_values[baseline_end:])):.4f}, '
                f'threshold={closed_threshold:.4f})'
            )

    # ============================================================
    # CHALLENGE: OPEN MOUTH
    # ============================================================

    def _verify_open_mouth(self, frames_data):
        """Detect mouth opening using MAR increase from baseline."""
        tag = "[OPEN_MOUTH]"
        n = len(frames_data)
        if n < MIN_FRAMES_FOR_CHALLENGE:
            return False, 0.0, f'Insufficient frames ({n}/{MIN_FRAMES_FOR_CHALLENGE})'

        mar_values = [f['mar'] for f in frames_data]
        baseline_end = min(self.BASELINE_FRAMES, n)
        baseline_mar = float(np.mean(mar_values[:baseline_end]))

        logger.info("%s frames=%d baseline_mar=%.4f", tag, n, baseline_mar)

        open_threshold = max(self.MAR_OPEN_THRESHOLD, baseline_mar * 1.3)
        open_count = 0
        max_mar = 0.0

        for i in range(baseline_end, n):
            if mar_values[i] > open_threshold:
                open_count += 1
            max_mar = max(max_mar, mar_values[i])

        mar_change = max_mar - baseline_mar
        logger.info("%s open_thresh=%.4f max_mar=%.4f change=%.4f open_frames=%d",
                     tag, open_threshold, max_mar, mar_change, open_count)

        if open_count >= self.MIN_SUSTAINED_FRAMES:
            confidence = min(1.0, 0.3 + min(mar_change / 0.15, 1.0) * 0.7)
            return True, round(confidence, 3), f'Mouth opened (MAR {baseline_mar:.3f}->{max_mar:.3f})'

        return False, 0.0, f'Mouth not opened enough (max MAR={max_mar:.4f}, need>{open_threshold:.4f}, open_frames={open_count})'

    # ============================================================
    # CHALLENGE: SHAKE HEAD
    # ============================================================

    def _verify_shake_head(self, frames_data):
        """Detect head shake (left-right oscillation) using yaw tracking.

        State machine: CENTER -> LEFT -> RIGHT -> CENTER (or reversed).
        Uses smoothed yaw values relative to baseline.
        Requires at least 3 phase transitions (full left-right-center cycle).
        """
        tag = "[SHAKE_HEAD]"
        n = len(frames_data)
        if n < MIN_FRAMES_FOR_CHALLENGE:
            return False, 0.0, f'Insufficient frames ({n}/{MIN_FRAMES_FOR_CHALLENGE})'

        yaw_values = [f['yaw'] for f in frames_data]
        baseline_end = min(self.BASELINE_FRAMES, n)
        baseline_yaw = float(np.mean(yaw_values[:baseline_end]))

        # Smooth yaw to reduce jitter
        smoothed = self._smooth_values(yaw_values, window=3)

        left_thresh  = baseline_yaw + self.SHAKE_YAW_DEGREES
        right_thresh = baseline_yaw - self.SHAKE_YAW_DEGREES

        yaw_str = ' '.join([f'{y:.1f}' for y in yaw_values])
        logger.info("%s frames=%d baseline=%.2f left_thresh=%.2f right_thresh=%.2f all_yaws=[%s]",
                     tag, n, baseline_yaw, left_thresh, right_thresh, yaw_str)

        # State machine tracking
        phases = []          # list of (phase_name, start_idx, end_idx)
        current_phase = 'CENTER'
        phase_start = baseline_yaw
        phase_frame_count = 0

        def classify(yaw_val):
            if yaw_val > left_thresh:
                return 'LEFT'
            elif yaw_val < right_thresh:
                return 'RIGHT'
            return 'CENTER'

        for i in range(baseline_end, n):
            detected_phase = classify(smoothed[i])

            if detected_phase == current_phase:
                phase_frame_count += 1
            else:
                # Phase transition
                if phase_frame_count >= self.SHAKE_MIN_FRAMES_PER_PHASE:
                    phases.append((current_phase, i - phase_frame_count, i - 1))
                current_phase = detected_phase
                phase_frame_count = 1

        # Record final phase
        if phase_frame_count >= self.SHAKE_MIN_FRAMES_PER_PHASE:
            phases.append((current_phase, n - phase_frame_count, n - 1))

        # Count unique directional phases
        phase_names = [p[0] for p in phases]
        has_left = 'LEFT' in phase_names
        has_right = 'RIGHT' in phase_names
        has_center = 'CENTER' in phase_names

        # Count transitions
        transitions = 0
        for i in range(1, len(phase_names)):
            if phase_names[i] != phase_names[i-1]:
                transitions += 1

        logger.info("%s phases=%s transitions=%d has_left=%s has_right=%s",
                     tag, phase_names, transitions, has_left, has_right)

        # Require: CENTER -> LEFT -> RIGHT -> CENTER (or reversed)
        # Minimum 3 transitions with both LEFT and RIGHT visited
        min_transitions_needed = self.SHAKE_MIN_PHASES

        if transitions >= min_transitions_needed and has_left and has_right:
            confidence = min(1.0, 0.3 + min(transitions / 5.0, 1.0) * 0.7)
            return True, round(confidence, 3), (
                f'Head shake detected ({transitions} transitions, '
                f'yaw range {min(yaw_values[baseline_end:]):.1f} to {max(yaw_values[baseline_end:]):.1f})'
            )

        return False, 0.0, (
            f'Insufficient head shake (transitions={transitions}/{min_transitions_needed}, '
            f'has_left={has_left}, has_right={has_right}, '
            f'yaw range={min(yaw_values[baseline_end:]):.1f} to {max(yaw_values[baseline_end:]):.1f})'
        )

    # ============================================================
    # CHALLENGE: LOOK LEFT (gaze-based)
    # ============================================================

    def _verify_look_left(self, frames_data):
        """Detect gaze shift to the left using yaw change from baseline.

        NOTE: Browser mirrors the video preview (CSS scaleX(-1)) but canvas.drawImage
        captures the raw non-mirrored frame. This means when the user turns LEFT on the
        mirrored screen, the raw frame shows the nose moving RIGHT (positive yaw).
        So look_left must check for POSITIVE yaw change.
        """
        tag = "[LOOK_LEFT]"
        n = len(frames_data)
        if n < MIN_FRAMES_FOR_CHALLENGE:
            return False, 0.0, f'Insufficient frames ({n}/{MIN_FRAMES_FOR_CHALLENGE})'

        yaw_values = [f['yaw'] for f in frames_data]
        baseline_end = min(self.BASELINE_FRAMES, n)
        baseline_yaw = float(np.mean(yaw_values[:baseline_end]))

        look_threshold = baseline_yaw + self.LOOK_YAW_DEGREES
        post_baseline = yaw_values[baseline_end:]
        min_yaw = float(np.min(post_baseline))
        max_yaw = float(np.max(post_baseline))
        yaw_range = max_yaw - min_yaw

        yaw_str = ' '.join([f'{y:.1f}' for y in yaw_values])
        logger.info("%s frames=%d baseline=%.2f threshold=%.2f min=%.2f max=%.2f range=%.1f all_yaws=[%s]",
                     tag, n, baseline_yaw, look_threshold, min_yaw, max_yaw, yaw_range, yaw_str)

        sustained_count = sum(1 for y in post_baseline if y > look_threshold)
        if sustained_count >= self.MIN_SUSTAINED_FRAMES:
            yaw_change = max_yaw - baseline_yaw
            confidence = min(1.0, 0.3 + min(yaw_change / 15.0, 1.0) * 0.7)
            return True, round(confidence, 3), f'Look left detected (yaw {baseline_yaw:.1f}->{max_yaw:.1f}, sustained={sustained_count} frames)'

        return False, 0.0, f'No left gaze (max_yaw={max_yaw:.2f}, need>{look_threshold:.2f}, sustained={sustained_count}/{self.MIN_SUSTAINED_FRAMES})'

    # ============================================================
    # CHALLENGE: LOOK RIGHT (gaze-based)
    # ============================================================

    def _verify_look_right(self, frames_data):
        """Detect gaze shift to the right using yaw change from baseline.

        NOTE: Browser mirrors the video preview (CSS scaleX(-1)) but canvas.drawImage
        captures the raw non-mirrored frame. This means when the user turns RIGHT on the
        mirrored screen, the raw frame shows the nose moving LEFT (negative yaw).
        So look_right must check for NEGATIVE yaw change.
        """
        tag = "[LOOK_RIGHT]"
        n = len(frames_data)
        if n < MIN_FRAMES_FOR_CHALLENGE:
            return False, 0.0, f'Insufficient frames ({n}/{MIN_FRAMES_FOR_CHALLENGE})'

        yaw_values = [f['yaw'] for f in frames_data]
        baseline_end = min(self.BASELINE_FRAMES, n)
        baseline_yaw = float(np.mean(yaw_values[:baseline_end]))

        look_threshold = baseline_yaw - self.LOOK_YAW_DEGREES
        post_baseline = yaw_values[baseline_end:]
        min_yaw = float(np.min(post_baseline))
        max_yaw = float(np.max(post_baseline))
        yaw_range = max_yaw - min_yaw

        yaw_str = ' '.join([f'{y:.1f}' for y in yaw_values])
        logger.info("%s frames=%d baseline=%.2f threshold=%.2f min=%.2f max=%.2f range=%.1f all_yaws=[%s]",
                     tag, n, baseline_yaw, look_threshold, min_yaw, max_yaw, yaw_range, yaw_str)

        sustained_count = sum(1 for y in post_baseline if y < look_threshold)
        if sustained_count >= self.MIN_SUSTAINED_FRAMES:
            yaw_change = baseline_yaw - min_yaw
            confidence = min(1.0, 0.3 + min(yaw_change / 15.0, 1.0) * 0.7)
            return True, round(confidence, 3), f'Look right detected (yaw {baseline_yaw:.1f}->{min_yaw:.1f}, sustained={sustained_count} frames)'

        return False, 0.0, f'No right gaze (min_yaw={min_yaw:.2f}, need<{look_threshold:.2f}, sustained={sustained_count}/{self.MIN_SUSTAINED_FRAMES})'

    # ============================================================
    # CHALLENGE: LOOK UP
    # ============================================================

    def _verify_look_up(self, frames_data):
        """Detect upward pitch movement."""
        tag = "[LOOK_UP]"
        n = len(frames_data)
        if n < MIN_FRAMES_FOR_CHALLENGE:
            return False, 0.0, f'Insufficient frames ({n}/{MIN_FRAMES_FOR_CHALLENGE})'

        pitch_values = [f['pitch'] for f in frames_data]
        baseline_end = min(self.BASELINE_FRAMES, n)
        baseline_pitch = float(np.mean(pitch_values[:baseline_end]))

        look_up_threshold = baseline_pitch - self.PITCH_UP_DEGREES
        min_pitch = float(np.min(pitch_values[baseline_end:]))

        logger.info("%s frames=%d baseline=%.2f threshold=%.2f min_pitch=%.2f",
                     tag, n, baseline_pitch, look_up_threshold, min_pitch)

        post_baseline_pitch = pitch_values[baseline_end:]
        sustained_count = sum(1 for p in post_baseline_pitch if p < look_up_threshold)
        if sustained_count >= self.MIN_SUSTAINED_FRAMES:
            pitch_change = baseline_pitch - min_pitch
            confidence = min(1.0, 0.3 + min(pitch_change / 15.0, 1.0) * 0.7)
            return True, round(confidence, 3), f'Look up detected (pitch {baseline_pitch:.1f}->{min_pitch:.1f}, sustained={sustained_count} frames)'

        return False, 0.0, f'No look up (min_pitch={min_pitch:.2f}, need<{look_up_threshold:.2f}, sustained={sustained_count}/{self.MIN_SUSTAINED_FRAMES})'

    # ============================================================
    # HAND CHALLENGE VERIFICATION (using MediaPipe Pose)
    # ============================================================

    def _extract_pose_landmarks(self, img):
        """Extract pose landmarks from image using MediaPipe Pose."""
        if self.pose_landmarker is None:
            return None
        try:
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            results = self.pose_landmarker.detect(mp_image)
            if not results or not results.pose_landmarks:
                return None
            landmarks = results.pose_landmarks[0]
            h, w = img.shape[:2]
            return {
                'left_wrist': (landmarks[15].x * w, landmarks[15].y * h),
                'right_wrist': (landmarks[16].x * w, landmarks[16].y * h),
                'left_shoulder': (landmarks[11].x * w, landmarks[11].y * h),
                'right_shoulder': (landmarks[12].x * w, landmarks[12].y * h),
                'nose': (landmarks[0].x * w, landmarks[0].y * h),
            }
        except Exception as e:
            logger.warning("[POSE] Landmark extraction failed: %s", e)
            return None

    def _is_hand_raised(self, pose_data):
        """Check if a hand is raised above shoulder level."""
        if pose_data is None:
            return False, False
        left_wrist_y = pose_data['left_wrist'][1]
        right_wrist_y = pose_data['right_wrist'][1]
        left_shoulder_y = pose_data['left_shoulder'][1]
        right_shoulder_y = pose_data['right_shoulder'][1]
        avg_shoulder_y = (left_shoulder_y + right_shoulder_y) / 2.0
        left_raised = left_wrist_y < avg_shoulder_y * self.HAND_SHOULDER_Y_THRESHOLD + avg_shoulder_y * (1 - self.HAND_SHOULDER_Y_THRESHOLD)
        right_raised = right_wrist_y < avg_shoulder_y * self.HAND_SHOULDER_Y_THRESHOLD + avg_shoulder_y * (1 - self.HAND_SHOULDER_Y_THRESHOLD)
        return left_raised, right_raised

    def _verify_hand_challenge(self, challenge_data, frames_base64, result):
        """Verify hand raise challenges using MediaPipe Pose."""
        tag = "[HAND_CHALLENGE]"
        challenge_type = challenge_data.get('challenge_type', 'unknown')
        frames_base64 = frames_base64 or []

        if self.pose_landmarker is None:
            result['reason'] = 'Pose landmarker not available -- hand challenges require MediaPipe Pose'
            result['details'] = {'verdict': 'POSE_UNAVAILABLE'}
            return self._to_native(result)

        if len(frames_base64) < MIN_FRAMES_FOR_CHALLENGE:
            result['reason'] = f'Insufficient frames ({len(frames_base64)}/{MIN_FRAMES_FOR_CHALLENGE})'
            return self._to_native(result)

        left_raised_frames = 0
        right_raised_frames = 0
        valid_frames = 0

        for frame_b64 in frames_base64:
            try:
                if isinstance(frame_b64, str) and ',' in frame_b64:
                    frame_b64 = frame_b64.split(',')[1]
                img_bytes = base64.b64decode(frame_b64)
                nparr = np.frombuffer(img_bytes, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is None:
                    continue

                pose_data = self._extract_pose_landmarks(img)
                if pose_data is None:
                    continue

                valid_frames += 1
                left_raised, right_raised = self._is_hand_raised(pose_data)
                if left_raised:
                    left_raised_frames += 1
                if right_raised:
                    right_raised_frames += 1

            except Exception:
                continue

        if valid_frames < MIN_FRAMES_FOR_CHALLENGE:
            result['reason'] = f'Insufficient valid pose frames ({valid_frames}/{MIN_FRAMES_FOR_CHALLENGE})'
            return self._to_native(result)

        logger.info("%s type=%s valid_frames=%d left_raised=%d right_raised=%d",
                     tag, challenge_type, valid_frames, left_raised_frames, right_raised_frames)

        if challenge_type == 'raise_one_hand':
            either_hand = left_raised_frames >= self.HAND_HOLD_FRAMES or right_raised_frames >= self.HAND_HOLD_FRAMES
            if either_hand:
                held_frames = max(left_raised_frames, right_raised_frames)
                confidence = min(1.0, 0.4 + (held_frames / valid_frames) * 0.6)
                hand = 'left' if left_raised_frames >= self.HAND_HOLD_FRAMES else 'right'
                return True, round(confidence, 3), f'One hand raised ({hand}, held {held_frames}/{valid_frames} frames)'
            else:
                return False, 0.0, f'No hand raised long enough (left={left_raised_frames}, right={right_raised_frames}, need>={self.HAND_HOLD_FRAMES})'

        elif challenge_type == 'raise_both_hands':
            both_hands = left_raised_frames >= self.HAND_HOLD_FRAMES and right_raised_frames >= self.HAND_HOLD_FRAMES
            if both_hands:
                held_frames = min(left_raised_frames, right_raised_frames)
                confidence = min(1.0, 0.4 + (held_frames / valid_frames) * 0.6)
                return True, round(confidence, 3), f'Both hands raised (held {held_frames}/{valid_frames} frames)'
            else:
                return False, 0.0, f'Both hands not raised long enough (left={left_raised_frames}, right={right_raised_frames}, need>={self.HAND_HOLD_FRAMES})'

        return False, 0.0, f'Unknown hand challenge: {challenge_type}'

    # ============================================================
    # FALLBACK (no MediaPipe)
    # ============================================================

    def _verify_fallback(self, challenge_data, frames_base64, result):
        decoded_frames = []
        for frame_b64 in frames_base64:
            try:
                if isinstance(frame_b64, str) and ',' in frame_b64:
                    frame_b64 = frame_b64.split(',')[1]
                img_bytes = base64.b64decode(frame_b64)
                nparr = np.frombuffer(img_bytes, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is not None:
                    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
                    decoded_frames.append(cv2.resize(gray, (320, 240)))
            except Exception:
                continue

        if len(decoded_frames) < MIN_FRAMES_FOR_CHALLENGE:
            result['challenge_passed'] = False
            result['confidence'] = 0.1
            result['details'] = {'mode': 'fallback', 'valid_frames': len(decoded_frames)}
            result['reason'] = f'Insufficient valid frames ({len(decoded_frames)}/{MIN_FRAMES_FOR_CHALLENGE})'
            return self._to_native(result)

        frame_diffs = []
        for i in range(1, len(decoded_frames)):
            diff = cv2.absdiff(decoded_frames[i - 1], decoded_frames[i])
            frame_diffs.append(float(np.mean(diff)))

        mean_diff = float(np.mean(frame_diffs)) if frame_diffs else 0.0
        has_movement = mean_diff > 8.0

        if has_movement:
            result['challenge_passed'] = True
            result['confidence'] = 0.25
            result['reason'] = 'Movement detected (fallback mode -- MediaPipe unavailable)'
        else:
            result['challenge_passed'] = False
            result['confidence'] = 0.05
            result['reason'] = f'Insufficient movement (diff={mean_diff:.3f}, need>8.0)'

        return self._to_native(result)
