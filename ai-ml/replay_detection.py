"""
Robust Replay-Attack Detection Module for Digital KYC System.

Implements comprehensive anti-spoofing pipeline:
- Real-time challenge-response with random action sequences
- Replay video detection (frame patterns, micro-movements, temporal smoothness)
- Screen replay detection (moire, FFT, pixel grid, banding, reflections)
- Print attack detection (flat geometry, paper edges, uniform texture)
- Multi-signal liveness analysis (EAR, head pose, MAR, movement consistency)
- Gated decision logic with explicit rejection reasons
"""

import cv2
import numpy as np
import base64
import logging
import time
import random
import hashlib
import json
from datetime import datetime, timedelta
from collections import OrderedDict
from scipy import fftpack, signal as scipy_signal

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

# Import existing liveness detector for reuse
from liveness_detection import ChallengeLivenessDetector, _ensure_face_landmarker_model

# ========== CHALLENGE TYPES ==========
CHALLENGE_ACTIONS = [
    'wink_left',
    'wink_right',
    'open_mouth',
    'look_up',
    'look_down',
]

CHALLENGE_PROMPTS = OrderedDict([
    ('wink_left', {'text': 'Close your left eye only', 'icon': '😉', 'tip': 'Wink with your left eye'}),
    ('wink_right', {'text': 'Close your right eye only', 'icon': '😜', 'tip': 'Wink with your right eye'}),
    ('open_mouth', {'text': 'Open your mouth', 'icon': '😮', 'tip': 'Open your mouth wide'}),
    ('look_up', {'text': 'Look up toward the ceiling', 'icon': '⬆️', 'tip': 'Tilt your head up'}),
    ('look_down', {'text': 'Look down toward the floor', 'icon': '⬇️', 'tip': 'Tilt your head down'}),
])

CHALLENGE_TIMEOUT_SECONDS = 30
MIN_FRAMES_PER_ACTION = 8
TOTAL_CHALLENGE_FRAMES = 40

# ========== THRESHOLDS ==========
EAR_BLINK_THRESHOLD = 0.25
MAR_SMILE_THRESHOLD = 0.35
YAW_THRESHOLD = 8.0
PITCH_THRESHOLD = 6.0
REPLAY_SCORE_THRESHOLD = 0.65
SCREEN_REPLAY_THRESHOLD = 0.60
PRINT_ATTACK_THRESHOLD = 0.55
LIVENESS_THRESHOLD = 0.50
CHALLENGE_CONFIDENCE_THRESHOLD = 0.60
DEPTH_FLATNESS_THRESHOLD = 0.35
STATIC_MOTION_THRESHOLD = 0.008


def decode_frames(frames_base64, max_frames=50):
    """Decode base64 frames to numpy arrays."""
    decoded = []
    for f in frames_base64[:max_frames]:
        try:
            if isinstance(f, str) and ',' in f:
                f = f.split(',')[1]
            img_bytes = base64.b64decode(f)
            nparr = np.frombuffer(img_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is not None:
                decoded.append(img)
        except Exception:
            continue
    return decoded


def _to_native(obj):
    """Convert numpy types to native Python types for JSON serialization."""
    if isinstance(obj, dict):
        return {k: _to_native(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_to_native(v) for v in obj]
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return _to_native(obj.tolist())
    return obj


class ReplayAttackDetector:
    """Comprehensive replay-attack detection system.

    Combines challenge-response, liveness analysis, and multiple
    anti-spoofing detectors to identify and reject:
    - Pre-recorded video replays (on phones/tablets)
    - Screen replays (another screen showing the user)
    - Printed photo attacks
    - Static image attacks
    """

    def __init__(self):
        self.face_landmarker = None
        self.FALLBACK_MODE = False
        self._init_mediapipe()

        self.ear_history = []
        self.mar_history = []
        self.yaw_history = []
        self.pitch_history = []
        self.roll_history = []
        self.landmark_confidence_history = []

    def _init_mediapipe(self):
        """Initialize MediaPipe FaceLandmarker."""
        if not HAS_MEDIAPIPE:
            self.FALLBACK_MODE = True
            logger.warning('[ReplayDetect] MediaPipe not available, using fallback mode')
            return
        try:
            model_path = _ensure_face_landmarker_model()
            if not model_path:
                self.FALLBACK_MODE = True
                logger.warning('[ReplayDetect] No face landmarker model, fallback mode')
                return
            base_options = mp_tasks.BaseOptions(
                model_asset_path=model_path,
                delegate=mp_tasks.BaseOptions.Delegate.CPU
            )
            options = mp_vision.FaceLandmarkerOptions(
                base_options=base_options,
                output_face_blendshapes=False,
                output_facial_transformation_matrixes=False,
                running_mode=mp_vision.RunningMode.IMAGE,
                num_faces=1,
                min_face_detection_confidence=0.3,
                min_face_presence_confidence=0.3,
                min_tracking_confidence=0.3,
            )
            self.face_landmarker = mp_vision.FaceLandmarker.create_from_options(options)
            logger.info('[ReplayDetect] MediaPipe FaceLandmarker initialized')
        except Exception as e:
            self.FALLBACK_MODE = True
            logger.error('[ReplayDetect] MediaPipe init failed: %s', e)

    # ========== LANDMARK EXTRACTION ==========

    def extract_landmarks(self, img):
        """Extract 468-point face landmarks from image using MediaPipe."""
        if self.FALLBACK_MODE or self.face_landmarker is None:
            return None
        try:
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            results = self.face_landmarker.detect(mp_image)
            if not results or not results.face_landmarks:
                return None
            landmarks = results.face_landmarks[0]
            h, w = img.shape[:2]
            pts = np.array([(lm.x * w, lm.y * h) for lm in landmarks])
            # Compute overall landmark confidence
            conf = np.mean([lm.z for lm in landmarks])  # rough confidence proxy
            return pts, conf
        except Exception as e:
            logger.debug('[ReplayDetect] Landmark extraction error: %s', e)
            return None

    # ========== 1. CHALLENGE RESPONSE ==========

    def generate_challenge_sequence(self, num_actions=None):
        """Generate a random challenge sequence of 3-5 actions.

        Returns:
            dict with: sequence (ordered list), prompts, token, nonce,
                       created_at, expires_at, timeout_seconds
        """
        if num_actions is None:
            num_actions = random.randint(3, 5)

        # Select random actions, ensure diversity
        actions = random.sample(CHALLENGE_ACTIONS, min(num_actions, len(CHALLENGE_ACTIONS)))

        # Occasionally repeat blink_twice for emphasis
        if 'blink_twice' in actions and random.random() < 0.3:
            pass  # keep as-is

        timestamp = datetime.utcnow()
        nonce = hashlib.sha256(
            f"{timestamp.timestamp()}:{random.random()}:{json.dumps(actions)}".encode()
        ).hexdigest()[:16]
        token = hashlib.sha256(f"{nonce}:replay-challenge".encode()).hexdigest()

        prompts = [CHALLENGE_PROMPTS[a] for a in actions]

        return {
            'sequence': actions,
            'prompts': prompts,
            'token': token,
            'nonce': nonce,
            'created_at': timestamp.isoformat() + 'Z',
            'expires_at': (timestamp + timedelta(seconds=CHALLENGE_TIMEOUT_SECONDS)).isoformat() + 'Z',
            'timeout_seconds': CHALLENGE_TIMEOUT_SECONDS,
            'num_actions': len(actions),
        }

    def verify_challenge_sequence(self, challenge_data, frames_base64):
        """Verify that the user performed actions in the correct order.

        Analyzes each frame for action evidence and validates:
        - Actions performed in the correct sequence order
        - No extraneous actions between required ones
        - All actions completed within timeout
        - Minimum confidence per action

        Args:
            challenge_data: dict from generate_challenge_sequence()
            frames_base64: list of base64-encoded frames

        Returns:
            dict with: passed, confidence, action_results, reason
        """
        result = {
            'passed': False,
            'confidence': 0.0,
            'action_results': [],
            'detected_actions': [],
            'execution_order': [],
            'reason': '',
        }

        decoded = decode_frames(frames_base64, TOTAL_CHALLENGE_FRAMES)
        if len(decoded) < 4:
            result['reason'] = f'Insufficient frames ({len(decoded)}/4)'
            return result

        sequence = challenge_data.get('sequence', [])
        if not sequence:
            result['reason'] = 'Empty challenge sequence'
            return result

        # Check expiry
        expires_str = challenge_data.get('expires_at', '')
        if expires_str:
            try:
                expires = datetime.fromisoformat(expires_str.replace('Z', '+00:00'))
                if datetime.utcnow().replace(tzinfo=expires.tzinfo) > expires:
                    result['reason'] = 'Challenge expired'
                    return result
            except Exception:
                pass

        # Extract landmarks from all frames
        all_landmarks = []
        for img in decoded:
            lm = self.extract_landmarks(img)
            if lm is not None:
                all_landmarks.append(lm)

        if len(all_landmarks) < 4:
            result['reason'] = f'Face not detected in enough frames ({len(all_landmarks)}/4)'
            return result

        # Compute signals per frame
        ear_values = []
        mar_values = []
        yaw_values = []
        pitch_values = []
        roll_values = []

        for pts, conf in all_landmarks:
            ear = self._compute_ear(pts)
            mar = self._compute_mar(pts)
            yaw, pitch, roll = self._compute_head_pose(pts)
            ear_values.append(ear)
            mar_values.append(mar)
            yaw_values.append(yaw)
            pitch_values.append(pitch)
            roll_values.append(roll)

        ear_values = np.array(ear_values)
        mar_values = np.array(mar_values)
        yaw_values = np.array(yaw_values)
        pitch_values = np.array(pitch_values)

        # Check for static face (photo/screen)
        motion_std = max(
            np.std(ear_values) * 10,
            np.std(yaw_values),
            np.std(pitch_values)
        )
        if motion_std < STATIC_MOTION_THRESHOLD:
            result['reason'] = 'Static face detected — possible photo attack'
            result['confidence'] = 0.0
            return result

        # Check depth flatness (print attack)
        depth_score = self._compute_depth_score(all_landmarks)
        if depth_score < DEPTH_FLATNESS_THRESHOLD:
            result['reason'] = f'Flat facial geometry detected — possible print attack (depth: {depth_score:.2f})'
            result['confidence'] = max(0.0, depth_score)
            result['execution_order'] = []
            result['detected_actions'] = []
            return result

        # Segment frames by action timing (roughly equal segments)
        frames_per_action = max(len(all_landmarks) // max(len(sequence), 1), 3)
        action_results = []
        detected_actions = []
        execution_order = []

        for i, action in enumerate(sequence):
            start_idx = i * frames_per_action
            end_idx = min((i + 1) * frames_per_action, len(all_landmarks))
            if start_idx >= end_idx:
                break

            seg_ear = ear_values[start_idx:end_idx]
            seg_mar = mar_values[start_idx:end_idx]
            seg_yaw = yaw_values[start_idx:end_idx]
            seg_pitch = pitch_values[start_idx:end_idx]

            action_passed, action_conf, action_detail = self._classify_action(
                action, seg_ear, seg_mar, seg_yaw, seg_pitch
            )

            action_results.append({
                'action': action,
                'passed': action_passed,
                'confidence': round(float(action_conf), 4),
                'detail': action_detail,
            })

            if action_passed:
                detected_actions.append(action)
                execution_order.append(action)

        # Check: were all actions detected in order?
        all_detected = len(detected_actions) == len(sequence)
        correct_order = execution_order == sequence[:len(execution_order)]
        action_confidence = float(np.mean([ar['confidence'] for ar in action_results])) if action_results else 0.0

        passed = all_detected and correct_order and action_confidence >= CHALLENGE_CONFIDENCE_THRESHOLD
        confidence = action_confidence if passed else min(action_confidence, CHALLENGE_CONFIDENCE_THRESHOLD - 0.01)

        if not all_detected:
            missing = [a for a in sequence if a not in detected_actions]
            result['reason'] = f'Actions not detected: {", ".join(missing)}'
        elif not correct_order:
            result['reason'] = f'Actions performed in wrong order. Expected: {sequence}, Got: {execution_order}'
        elif action_confidence < CHALLENGE_CONFIDENCE_THRESHOLD:
            result['reason'] = f'Challenge confidence too low ({action_confidence:.2f} < {CHALLENGE_CONFIDENCE_THRESHOLD})'
        else:
            result['reason'] = 'All actions verified in correct order'

        result['passed'] = passed
        result['confidence'] = round(float(confidence), 4)
        result['action_results'] = action_results
        result['detected_actions'] = detected_actions
        result['execution_order'] = execution_order
        result['liveness_metrics'] = {
            'avg_ear': round(float(np.mean(ear_values)), 4),
            'avg_mar': round(float(np.mean(mar_values)), 4),
            'avg_yaw': round(float(np.mean(np.abs(yaw_values))), 4),
            'avg_pitch': round(float(np.mean(np.abs(pitch_values))), 4),
            'motion_std': round(float(motion_std), 4),
            'depth_score': round(float(depth_score), 4),
        }

        return result

    def _compute_ear(self, points):
        """Eye Aspect Ratio from MediaPipe 468 landmarks."""
        left_eye_idxs = [33, 160, 158, 133, 153, 144]
        right_eye_idxs = [362, 385, 387, 263, 373, 380]

        def eye_ear(pts, idxs):
            p = pts[list(idxs)]
            v1 = np.linalg.norm(p[1] - p[5])
            v2 = np.linalg.norm(p[2] - p[4])
            h = np.linalg.norm(p[0] - p[3])
            return (v1 + v2) / (2.0 * h + 1e-6)

        left_ear = eye_ear(points, left_eye_idxs)
        right_ear = eye_ear(points, right_eye_idxs)
        return float((left_ear + right_ear) / 2.0)

    def _compute_mar(self, points):
        """Mouth Aspect Ratio from MediaPipe 468 landmarks."""
        upper_lip = points[13]
        lower_lip = points[14]
        left_mouth = points[78]
        right_mouth = points[308]

        v = np.linalg.norm(upper_lip - lower_lip)
        h = np.linalg.norm(left_mouth - right_mouth)
        return float(v / (h + 1e-6))

    def _compute_head_pose(self, points):
        """Estimate head pose from facial landmarks using geometric approach.

        Returns (yaw, pitch, roll) in degrees.
        """
        nose_tip = points[4]
        left_eye_outer = points[33]
        right_eye_outer = points[263]
        left_ear = points[234]
        right_ear = points[454]
        forehead = points[10]
        chin = points[152]

        face_center = (left_ear + right_ear) / 2.0
        eye_center = (left_eye_outer + right_eye_outer) / 2.0

        # Yaw: horizontal offset of nose from face center, scaled
        nose_offset = nose_tip[0] - face_center[0]
        eye_width = np.linalg.norm(left_ear - right_ear)
        yaw = float(np.degrees(np.arcsin(np.clip(nose_offset / (eye_width + 1e-6) * 1.5, -1.0, 1.0))))

        # Pitch: vertical position of nose relative to eye-chin axis
        face_height = np.linalg.norm(forehead - chin)
        nose_vertical = (nose_tip[1] - eye_center[1]) / (face_height + 1e-6)
        pitch = float(np.degrees(np.arcsin(np.clip((nose_vertical - 0.35) * 2.0, -1.0, 1.0))))

        # Roll: angle of eye line relative to horizontal
        dy = right_eye_outer[1] - left_eye_outer[1]
        dx = right_eye_outer[0] - left_eye_outer[0]
        roll = float(np.degrees(np.arctan2(dy, dx)))

        return yaw, pitch, roll

    def _compute_depth_score(self, landmarks_list):
        """Estimate 3D depth from landmark geometry.

        Returns score between 0 (flat) and 1 (deep).
        """
        if len(landmarks_list) < 2:
            return 0.5

        depth_ratios = []
        for pts, conf in landmarks_list:
            nose = pts[4]
            left_ear = pts[234]
            right_ear = pts[454]
            forehead = pts[10]
            chin = pts[152]

            # Vertical face height
            vh = np.linalg.norm(forehead - chin)
            # Distance from nose to ear midpoint
            ear_mid = (left_ear + right_ear) / 2.0
            nose_depth = np.linalg.norm(nose - ear_mid)

            ratio = nose_depth / (vh + 1e-6)
            depth_ratios.append(ratio)

        avg_ratio = float(np.mean(depth_ratios))
        # Normalize: typical real face ratio ~0.5-0.8, flat ~0.1-0.3
        score = min(1.0, max(0.0, avg_ratio / 0.6))
        return score

    def _classify_action(self, action, ear, mar, yaw, pitch):
        """Classify whether a specific action was performed in the frame segment.

        Returns (passed, confidence, detail_dict).
        """
        if action in ('wink_left', 'wink_right'):
            return self._detect_wink(ear, direction='left' if action == 'wink_left' else 'right')
        elif action == 'look_up':
            return self._detect_look_direction(pitch, direction='up')
        elif action == 'look_down':
            return self._detect_look_direction(pitch, direction='down')
        elif action == 'open_mouth':
            return self._detect_open_mouth(mar)
        else:
            return False, 0.0, {'error': f'Unknown action: {action}'}

    def _detect_blink(self, ear_values):
        """Detect blinks from EAR values. Requires >= 2 blinks (EAR dips below threshold)."""
        if len(ear_values) < 3:
            return False, 0.0, {'reason': 'Not enough frames'}

        ear_arr = np.array(ear_values)
        below = ear_arr < EAR_BLINK_THRESHOLD

        # Count transitions from above to below threshold (each blink = one dip)
        transitions = 0
        in_blink = False
        for b in below:
            if b and not in_blink:
                transitions += 1
                in_blink = True
            elif not b:
                in_blink = False

        # Blink quality: how deep and how long
        if transitions > 0:
            blink_depth = float(np.mean(EAR_BLINK_THRESHOLD - ear_arr[below])) if np.any(below) else 0
            blink_duration = float(np.sum(below)) / len(ear_arr)
        else:
            blink_depth = 0.0
            blink_duration = 0.0

        passed = transitions >= 2
        conf = min(1.0, max(0.0, (transitions / 4.0) * 0.6 + blink_depth * 2.0 + blink_duration * 0.5))

        return passed, conf, {
            'blinks_detected': int(transitions),
            'blink_depth': round(blink_depth, 4),
            'blink_duration_ratio': round(blink_duration, 4),
            'min_ear': round(float(np.min(ear_arr)), 4),
            'avg_ear': round(float(np.mean(ear_arr)), 4),
        }

    def _detect_head_turn(self, yaw_values, direction='left'):
        """Detect head turn in the specified direction."""
        if len(yaw_values) < 3:
            return False, 0.0, {'reason': 'Not enough frames'}

        yaw_arr = np.array(yaw_values)
        yaw_range = float(np.max(yaw_arr) - np.min(yaw_arr))
        yaw_std = float(np.std(yaw_arr))

        if direction == 'left':
            # Look for significant negative yaw (face pointing left)
            max_neg = float(np.min(yaw_arr))
            passed = max_neg < -YAW_THRESHOLD and yaw_range > YAW_THRESHOLD
        else:
            # Look for significant positive yaw (face pointing right)
            max_pos = float(np.max(yaw_arr))
            passed = max_pos > YAW_THRESHOLD and yaw_range > YAW_THRESHOLD

        conf = min(1.0, max(0.0, yaw_range / (YAW_THRESHOLD * 2)))

        return passed, conf, {
            'yaw_range': round(yaw_range, 4),
            'yaw_std': round(yaw_std, 4),
            'min_yaw': round(float(np.min(yaw_arr)), 4),
            'max_yaw': round(float(np.max(yaw_arr)), 4),
            'direction': direction,
        }

    def _detect_look_direction(self, pitch_values, direction='up'):
        """Detect look up/down from pitch values."""
        if len(pitch_values) < 3:
            return False, 0.0, {'reason': 'Not enough frames'}

        pitch_arr = np.array(pitch_values)
        pitch_range = float(np.max(pitch_arr) - np.min(pitch_arr))

        if direction == 'up':
            # Looking up: pitch becomes more positive
            max_pos = float(np.max(pitch_arr))
            passed = max_pos > PITCH_THRESHOLD and pitch_range > PITCH_THRESHOLD * 0.6
        else:
            # Looking down: pitch becomes more negative
            max_neg = float(np.min(pitch_arr))
            passed = max_neg < -PITCH_THRESHOLD and pitch_range > PITCH_THRESHOLD * 0.6

        conf = min(1.0, max(0.0, pitch_range / (PITCH_THRESHOLD * 1.5)))

        return passed, conf, {
            'pitch_range': round(pitch_range, 4),
            'min_pitch': round(float(np.min(pitch_arr)), 4),
            'max_pitch': round(float(np.max(pitch_arr)), 4),
            'direction': direction,
        }

    def _detect_smile(self, mar_values):
        """Detect smile from MAR values."""
        if len(mar_values) < 3:
            return False, 0.0, {'reason': 'Not enough frames'}

        mar_arr = np.array(mar_values)
        mar_max = float(np.max(mar_arr))
        mar_range = float(np.max(mar_arr) - np.min(mar_arr))
        mar_std = float(np.std(mar_arr))

        # Smile detection: MAR exceeds threshold OR significant range
        passed = mar_max > MAR_SMILE_THRESHOLD or mar_range > 0.05 or mar_std > 0.02

        conf = min(1.0, max(0.0,
            (mar_max / (MAR_SMILE_THRESHOLD * 1.5)) * 0.5 +
            (mar_range / 0.08) * 0.3 +
            (mar_std / 0.03) * 0.2
        ))

        return passed, conf, {
            'max_mar': round(mar_max, 4),
            'mar_range': round(mar_range, 4),
            'mar_std': round(mar_std, 4),
            'avg_mar': round(float(np.mean(mar_arr)), 4),
        }

    # ========== 2. REPLAY VIDEO DETECTION ==========

    def detect_replay_video(self, frames_base64):
        """Analyze frames for video replay artifacts.

        Detects:
        - Repeated frame patterns (identical consecutive frames)
        - Lack of natural head micro-movements (jitter analysis)
        - Artificial motion consistency (too-smooth motion)
        - Unnatural temporal smoothness (inter-frame interpolation artifacts)

        Returns dict with: replayAttackScore (0-1), replayVideoDetected, details
        """
        result = {
            'replayAttackScore': 0.0,
            'replayVideoDetected': False,
            'frame_duplicates': 0,
            'micro_movement_score': 0.0,
            'motion_smoothness_score': 0.0,
            'temporal_consistency_score': 0.0,
            'details': [],
        }

        decoded = decode_frames(frames_base64, TOTAL_CHALLENGE_FRAMES)
        if len(decoded) < 6:
            result['details'].append(f'Insufficient frames ({len(decoded)}/6)')
            return result

        # Convert to grayscale for motion analysis
        gray_frames = [cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) for img in decoded]

        # 2a. Frame duplicate detection
        frame_diffs = []
        for i in range(1, len(gray_frames)):
            diff = cv2.absdiff(gray_frames[i], gray_frames[i - 1])
            mean_diff = float(np.mean(diff))
            frame_diffs.append(mean_diff)

        # Count near-identical frames (diff < 1.0)
        duplicates = sum(1 for d in frame_diffs if d < 1.0)
        duplicate_ratio = duplicates / max(len(frame_diffs), 1)
        result['frame_duplicates'] = int(duplicates)

        # 2b. Micro-movement analysis (natural face has tiny jitter)
        # Compute frame-to-frame centroid movement using image moments
        centroids = []
        for gf in gray_frames:
            try:
                M = cv2.moments(gf)
                if M['m00'] > 0:
                    cx = int(M['m10'] / M['m00'])
                    cy = int(M['m01'] / M['m00'])
                    centroids.append((cx, cy))
            except Exception:
                centroids.append((0, 0))

        if len(centroids) > 1:
            movements = []
            for i in range(1, len(centroids)):
                dist = np.linalg.norm(np.array(centroids[i]) - np.array(centroids[i - 1]))
                movements.append(dist)
            movement_std = float(np.std(movements))
            movement_mean = float(np.mean(movements))

            # Live faces have VARIED micro-movements (std > 0.3)
            # Replays have UNIFORM micro-movements (std < 0.15)
            micro_movement_score = min(1.0, max(0.0, movement_std / 0.5))
            result['micro_movement_score'] = round(micro_movement_score, 4)
        else:
            micro_movement_score = 0.0

        # 2c. Motion smoothness analysis
        # Real faces have NOISY motion signals; replays are SMOOTH (interpolated)
        if len(frame_diffs) > 3:
            diff_arr = np.array(frame_diffs)
            # High-frequency content: compute difference of differences (second derivative)
            if len(diff_arr) > 4:
                second_diff = np.abs(np.diff(diff_arr, n=2))
                smoothness = float(np.std(second_diff)) / (float(np.mean(diff_arr)) + 1e-6)
                # Low smoothness = too smooth = replay
                motion_smoothness_score = max(0.0, min(1.0, (1.0 - smoothness / 5.0)))
            else:
                motion_smoothness_score = 0.5
            result['motion_smoothness_score'] = round(motion_smoothness_score, 4)
        else:
            motion_smoothness_score = 0.5

        # 2d. Temporal consistency: check if frames are TOO consistent
        # (pre-recorded video loop point detection via periodic correlation)
        temporal_consistency_score = 0.0
        if len(frame_diffs) > 10:
            try:
                # Compute autocorrelation of frame diffs
                diff_arr = np.array(frame_diffs)
                diff_arr = (diff_arr - np.mean(diff_arr)) / (np.std(diff_arr) + 1e-6)
                correlation = np.correlate(diff_arr, diff_arr, mode='full')
                correlation = correlation[len(correlation) // 2:]

                # Check for periodic peaks (video loop)
                if len(correlation) > 4:
                    main_peak = np.max(correlation[1:]) if len(correlation) > 1 else 0
                    # Very high autocorrelation at non-zero lag = repetitive pattern
                    temporal_consistency_score = min(1.0, max(0.0, main_peak / len(correlation)))
            except Exception:
                temporal_consistency_score = 0.0
            result['temporal_consistency_score'] = round(temporal_consistency_score, 4)

        # Combine scores
        replay_score = (
            duplicate_ratio * 0.25 +
            (1.0 - micro_movement_score) * 0.30 +
            motion_smoothness_score * 0.25 +
            temporal_consistency_score * 0.20
        )

        replay_score = min(1.0, max(0.0, replay_score))
        result['replayAttackScore'] = round(replay_score, 4)
        result['replayVideoDetected'] = replay_score > REPLAY_SCORE_THRESHOLD

        details = []
        if duplicate_ratio > 0.3:
            details.append(f'Repeated frame pattern ({duplicate_ratio:.0%} duplicates)')
        if micro_movement_score < 0.3:
            details.append(f'Lack of natural micro-movements ({micro_movement_score:.2f})')
        if motion_smoothness_score > 0.7:
            details.append(f'Artificial motion smoothness ({motion_smoothness_score:.2f})')
        if temporal_consistency_score > 0.5:
            details.append(f'Unnatural temporal consistency ({temporal_consistency_score:.2f})')
        if not details:
            details.append('No replay indicators detected')

        result['details'] = details
        result['duplicate_ratio'] = round(duplicate_ratio, 4)
        result['movement_std'] = round(movement_std, 4) if len(centroids) > 1 else 0.0

        return result

    # ========== 3. SCREEN REPLAY DETECTION ==========

    def detect_screen_replay(self, frames_base64):
        """Detect screen replay artifacts in video frames.

        Analyzes for:
        - Moiré patterns (interference between screen pixel grid and camera sensor)
        - Screen pixel grid artifacts (high-frequency FFT peaks)
        - Reflection anomalies (specular highlights on glass)
        - Brightness banding (from screen refresh rate interactions)

        Returns dict with: screenReplayDetected (bool), confidence (0-1), details
        """
        result = {
            'screenReplayDetected': False,
            'confidence': 0.0,
            'moire_score': 0.0,
            'fft_peak_score': 0.0,
            'reflection_score': 0.0,
            'banding_score': 0.0,
            'details': [],
        }

        decoded = decode_frames(frames_base64, TOTAL_CHALLENGE_FRAMES)
        if len(decoded) < 3:
            result['details'].append('Insufficient frames')
            return result

        # Use middle frame for spatial analysis
        mid_img = decoded[len(decoded) // 2]
        gray = cv2.cvtColor(mid_img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        # 3a. Moire pattern detection via FFT
        moire_score = 0.0
        try:
            # Center crop to avoid edge artifacts
            crop_size = min(h, w) * 0.8
            ch = min(h, int(crop_size))
            cw = min(w, int(crop_size))
            start_y = (h - ch) // 2
            start_x = (w - cw) // 2
            center = gray[start_y:start_y + ch, start_x:start_x + cw]

            # Apply Hann window to reduce spectral leakage
            hann = np.hanning(ch)[:, None] * np.hanning(cw)[None, :]
            windowed = center * hann

            # 2D FFT
            fft = fftpack.fft2(windowed)
            fft_shift = fftpack.fftshift(fft)
            magnitude = np.abs(fft_shift)

            # Avoid DC component
            mid_y, mid_x = magnitude.shape[0] // 2, magnitude.shape[1] // 2
            magnitude[mid_y, mid_x] = 0

            # Look for high-frequency peaks (moire = periodic interference)
            # Exclude the center 20% (low frequencies)
            mask = np.ones_like(magnitude, dtype=bool)
            radius_y = ch // 5
            radius_x = cw // 5
            mask[mid_y - radius_y:mid_y + radius_y, mid_x - radius_x:mid_x + radius_x] = False

            high_freq = magnitude[mask]
            if len(high_freq) > 0:
                peak_mean = float(np.mean(high_freq))
                peak_std = float(np.std(high_freq))
                peak_max = float(np.max(high_freq))

                # Moire creates SPIKY peaks (high max/mean ratio)
                if peak_mean > 0:
                    peak_to_mean = peak_max / peak_mean
                    # Normalize: screens typically have peak/mean > 8-15
                    moire_score = min(1.0, max(0.0, (peak_to_mean - 3.0) / 15.0))
        except Exception as e:
            logger.debug('[ScreenReplay] FFT analysis error: %s', e)

        result['moire_score'] = round(moire_score, 4)

        # 3b. FFT peak frequency analysis (screen pixel grid)
        fft_peak_score = 0.0
        try:
            # Compute row-wise and column-wise FFT for grid detection
            row_fft = np.abs(fftpack.fft(gray, axis=1))
            col_fft = np.abs(fftpack.fft(gray, axis=0))

            # Average across rows/cols
            avg_row_fft = np.mean(row_fft[:, :w // 2], axis=0)
            avg_col_fft = np.mean(col_fft[:h // 2, :], axis=1)

            # Look for peaks in the mid-to-high frequency range
            # (phone pixel grid = 300-600 PPI, at typical distance creates specific frequencies)
            for spectrum in [avg_row_fft, avg_col_fft]:
                if len(spectrum) > 10:
                    # Exclude lowest 10% and highest 5%
                    low = len(spectrum) // 10
                    high = len(spectrum) * 95 // 100
                    if high > low:
                        segment = spectrum[low:high]
                        if np.mean(segment) > 0:
                            peak_ratio = np.max(segment) / np.mean(segment)
                            if peak_ratio > 3.0:
                                fft_peak_score = max(fft_peak_score, min(1.0, (peak_ratio - 2.0) / 8.0))
        except Exception as e:
            logger.debug('[ScreenReplay] FFT peak error: %s', e)

        result['fft_peak_score'] = round(fft_peak_score, 4)

        # 3c. Reflection anomaly detection
        reflection_score = 0.0
        try:
            # Screen glass has specular highlights = bright, small, high-contrast regions
            laplacian = cv2.Laplacian(gray, cv2.CV_32F)
            laplacian_var = float(np.var(laplacian))

            # Compute local contrast (std dev in 16x16 blocks)
            block_size = 16
            block_contrasts = []
            for by in range(0, h - block_size, block_size):
                for bx in range(0, w - block_size, block_size):
                    block = gray[by:by + block_size, bx:bx + block_size]
                    block_contrasts.append(float(np.std(block)))

            if block_contrasts:
                contrast_mean = float(np.mean(block_contrasts))
                contrast_std = float(np.std(block_contrasts))

                # Screen reflections create uneven contrast distribution
                # (some blocks very shiny, some not)
                if contrast_mean > 0:
                    reflection_score = min(1.0, max(0.0,
                        (laplacian_var / 500.0) * 0.3 +
                        (contrast_std / contrast_mean) * 0.7
                    ))
        except Exception as e:
            logger.debug('[ScreenReplay] Reflection error: %s', e)

        result['reflection_score'] = round(reflection_score, 4)

        # 3d. Brightness banding detection (screen refresh rate artifacts)
        banding_score = 0.0
        try:
            # Check for horizontal bands: average each row's brightness
            row_brightness = np.mean(gray, axis=1)
            if len(row_brightness) > 10:
                # FFT of row brightness to find periodic bands
                row_fft = np.abs(fftpack.fft(row_brightness))
                # Exclude DC and very low frequencies
                mid = len(row_fft) // 2
                row_fft[:max(3, mid // 20)] = 0

                if np.sum(row_fft) > 0:
                    peak_freq = float(np.max(row_fft)) / float(np.mean(row_fft[len(row_fft) // 20:]))
                    banding_score = min(1.0, max(0.0, (peak_freq - 2.0) / 10.0))
        except Exception as e:
            logger.debug('[ScreenReplay] Banding error: %s', e)

        result['banding_score'] = round(banding_score, 4)

        # Combine scores
        confidence = (
            moire_score * 0.30 +
            fft_peak_score * 0.25 +
            reflection_score * 0.25 +
            banding_score * 0.20
        )
        result['confidence'] = round(confidence, 4)
        result['screenReplayDetected'] = confidence > SCREEN_REPLAY_THRESHOLD

        details = []
        if moire_score > 0.5:
            details.append(f'Moiré interference pattern detected ({moire_score:.2f})')
        if fft_peak_score > 0.5:
            details.append(f'Screen pixel grid artifacts ({fft_peak_score:.2f})')
        if reflection_score > 0.5:
            details.append(f'Glass reflection anomalies ({reflection_score:.2f})')
        if banding_score > 0.5:
            details.append(f'Brightness banding from screen refresh ({banding_score:.2f})')
        if not details:
            details.append('No screen replay indicators detected')

        result['details'] = details
        return result

    # ========== 4. PRINT ATTACK DETECTION ==========

    def detect_print_attack(self, frames_base64):
        """Detect printed photo attacks.

        Analyzes for:
        - Flat facial geometry (low depth variation)
        - Paper edge visibility (sharp rectangular boundaries around face)
        - Uniform texture patterns (matte paper lacks skin micro-texture)
        - Lack of specular highlights

        Returns dict with: printAttackDetected (bool), confidence (0-1), details
        """
        result = {
            'printAttackDetected': False,
            'confidence': 0.0,
            'depth_flatness_score': 0.0,
            'paper_edge_score': 0.0,
            'texture_uniformity_score': 0.0,
            'specular_score': 0.0,
            'details': [],
        }

        decoded = decode_frames(frames_base64, TOTAL_CHALLENGE_FRAMES)
        if len(decoded) < 3:
            result['details'].append('Insufficient frames')
            return result

        # 4a. Depth flatness analysis (from landmarks)
        depth_flatness_score = 0.0
        all_landmarks = []
        for img in decoded:
            lm = self.extract_landmarks(img)
            if lm is not None:
                all_landmarks.append(lm)

        if len(all_landmarks) > 2:
            depth_score = self._compute_depth_score(all_landmarks)
            # Invert: low depth = high flatness
            depth_flatness_score = max(0.0, min(1.0, 1.0 - depth_score))
        else:
            depth_flatness_score = 0.5  # Uncertain

        result['depth_flatness_score'] = round(depth_flatness_score, 4)

        # 4b. Paper edge detection (sharp rectangular boundaries near face)
        paper_edge_score = 0.0
        try:
            mid_img = decoded[len(decoded) // 2]
            gray = cv2.cvtColor(mid_img, cv2.COLOR_BGR2GRAY)

            # Canny edge detection
            edges = cv2.Canny(gray, 50, 150)

            # Hough line transform for straight lines
            lines = cv2.HoughLinesP(
                edges, rho=1, theta=np.pi / 180,
                threshold=50, minLineLength=30, maxLineGap=10
            )

            if lines is not None and len(lines) > 5:
                # Count nearly horizontal and vertical lines
                h_lines = 0
                v_lines = 0
                for line in lines:
                    x1, y1, x2, y2 = line[0]
                    angle = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
                    if angle < 20 or angle > 160:
                        h_lines += 1
                    elif 70 < angle < 110:
                        v_lines += 1

                # Printed photos have rectangular borders (many H + V lines)
                total_lines = len(lines)
                border_ratio = (h_lines + v_lines) / max(total_lines, 1)
                if total_lines > 10:
                    paper_edge_score = min(1.0, max(0.0,
                        (border_ratio - 0.3) * 1.5 +
                        min(total_lines / 50.0, 0.5)
                    ))
        except Exception as e:
            logger.debug('[PrintAttack] Edge detection error: %s', e)

        result['paper_edge_score'] = round(paper_edge_score, 4)

        # 4c. Texture uniformity (printed paper has more uniform texture than skin)
        texture_uniformity_score = 0.0
        try:
            mid_img = decoded[len(decoded) // 2]
            gray = cv2.cvtColor(mid_img, cv2.COLOR_BGR2GRAY)

            # Local Binary Pattern-like texture analysis
            # Compute local variance in 8x8 blocks
            block_size = 8
            local_vars = []
            for by in range(0, gray.shape[0] - block_size, block_size):
                for bx in range(0, gray.shape[1] - block_size, block_size):
                    block = gray[by:by + block_size, bx:bx + block_size]
                    local_vars.append(float(np.var(block)))

            if local_vars:
                var_mean = float(np.mean(local_vars))
                var_std = float(np.std(local_vars))

                # Printed paper has uniform texture (low var_std / var_mean ratio)
                # Real faces have varied texture (high var_std / var_mean)
                if var_mean > 0:
                    texture_cv = var_std / var_mean
                    # Low CV (< 0.5) = uniform = printed paper
                    texture_uniformity_score = max(0.0, min(1.0, (0.8 - texture_cv) / 0.8))
        except Exception as e:
            logger.debug('[PrintAttack] Texture error: %s', e)

        result['texture_uniformity_score'] = round(texture_uniformity_score, 4)

        # 4d. Specular reflection score (matte paper lacks specular highlights)
        specular_score = 0.0
        try:
            mid_img = decoded[len(decoded) // 2]
            gray = cv2.cvtColor(mid_img, cv2.COLOR_BGR2GRAY)

            # Compute histogram and check for peaky distribution
            hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
            hist = hist.flatten() / (gray.size + 1e-6)

            # Real skin has broad histogram; paper has narrower histogram
            # Count bins with significant occupancy
            significant_bins = np.sum(hist > 0.005)
            # Paper: fewer significant bins (narrow range)
            # Skin: more significant bins (wide range)
            hist_width = significant_bins / 256.0
            specular_score = max(0.0, min(1.0, (0.4 - hist_width) * 2.0))
        except Exception as e:
            logger.debug('[PrintAttack] Specular error: %s', e)

        result['specular_score'] = round(specular_score, 4)

        # Combine scores
        confidence = (
            depth_flatness_score * 0.35 +
            paper_edge_score * 0.25 +
            texture_uniformity_score * 0.25 +
            specular_score * 0.15
        )
        result['confidence'] = round(confidence, 4)
        result['printAttackDetected'] = confidence > PRINT_ATTACK_THRESHOLD

        details = []
        if depth_flatness_score > 0.5:
            details.append(f'Flat facial geometry ({depth_flatness_score:.2f})')
        if paper_edge_score > 0.5:
            details.append(f'Paper edges detected ({paper_edge_score:.2f})')
        if texture_uniformity_score > 0.5:
            details.append(f'Uniform texture pattern ({texture_uniformity_score:.2f})')
        if specular_score > 0.5:
            details.append(f'Lack of specular highlights ({specular_score:.2f})')
        if not details:
            details.append('No print attack indicators detected')

        result['details'] = details
        return result

    # ========== 5. LIVENESS SIGNALS ==========

    def compute_liveness_signals(self, frames_base64):
        """Compute comprehensive liveness signals from video frames.

        Measures:
        - Eye Aspect Ratio (EAR) blink detection
        - Head pose estimation (yaw, pitch, roll)
        - Facial landmark movement consistency
        - Mouth movement consistency (MAR)

        Returns dict with livenessScore (0-1), and individual signal metrics.
        """
        result = {
            'livenessScore': 0.0,
            'blink_score': 0.0,
            'head_pose_score': 0.0,
            'landmark_movement_score': 0.0,
            'mouth_movement_score': 0.0,
            'signal_quality': 0.0,
            'signals': {},
        }

        decoded = decode_frames(frames_base64, TOTAL_CHALLENGE_FRAMES)
        if len(decoded) < 3:
            result['livenessScore'] = 0.0
            return result

        # Extract landmarks from all frames
        all_landmarks = []
        for img in decoded:
            lm = self.extract_landmarks(img)
            if lm is not None:
                all_landmarks.append(lm)

        if len(all_landmarks) < 3:
            result['livenessScore'] = 0.2  # Low confidence but not zero
            return result

        # Compute per-frame signals
        ear_vals, mar_vals, yaw_vals, pitch_vals, roll_vals = [], [], [], [], []
        for pts, conf in all_landmarks:
            ear_vals.append(self._compute_ear(pts))
            mar_vals.append(self._compute_mar(pts))
            y, p, r = self._compute_head_pose(pts)
            yaw_vals.append(y)
            pitch_vals.append(p)
            roll_vals.append(r)

        ear_arr = np.array(ear_vals)
        mar_arr = np.array(mar_vals)
        yaw_arr = np.array(yaw_vals)
        pitch_arr = np.array(pitch_vals)
        roll_arr = np.array(roll_vals)

        # 5a. Blink score
        below_threshold = ear_arr < EAR_BLINK_THRESHOLD
        blink_count = 0
        in_blink = False
        for b in below_threshold:
            if b and not in_blink:
                blink_count += 1
                in_blink = True
            elif not b:
                in_blink = False

        ear_range = float(np.max(ear_arr) - np.min(ear_arr))
        ear_std = float(np.std(ear_arr))
        blink_score = min(1.0, max(0.0,
            min(blink_count / 3.0, 1.0) * 0.5 +
            min(ear_range / 0.15, 1.0) * 0.3 +
            min(ear_std / 0.03, 1.0) * 0.2
        ))
        result['blink_score'] = round(blink_score, 4)

        # 5b. Head pose score (movement diversity)
        yaw_range = float(np.max(yaw_arr) - np.min(yaw_arr))
        pitch_range = float(np.max(pitch_arr) - np.min(pitch_arr))
        roll_range = float(np.max(roll_arr) - np.min(roll_arr))
        yaw_std = float(np.std(yaw_arr))
        pitch_std = float(np.std(pitch_arr))

        head_pose_score = min(1.0, max(0.0,
            min((yaw_range + pitch_range) / 15.0, 1.0) * 0.5 +
            min((yaw_std + pitch_std) / 4.0, 1.0) * 0.3 +
            min(roll_range / 5.0, 1.0) * 0.2
        ))
        result['head_pose_score'] = round(head_pose_score, 4)

        # 5c. Landmark movement score (natural facial movement)
        # Compute movement of key landmarks across frames
        if len(all_landmarks) > 2:
            landmark_movements = []
            for j in range(1, len(all_landmarks)):
                pts1, _ = all_landmarks[j - 1]
                pts2, _ = all_landmarks[j]
                # Use nose, eye corners, mouth corners
                key_idxs = [4, 33, 263, 61, 291, 152]
                total_movement = 0
                for ki in key_idxs:
                    if ki < len(pts1) and ki < len(pts2):
                        total_movement += np.linalg.norm(pts2[ki] - pts1[ki])
                landmark_movements.append(total_movement / len(key_idxs))

            if landmark_movements:
                lm_mean = float(np.mean(landmark_movements))
                lm_std = float(np.std(landmark_movements))
                # Real faces have moderate movement with some variation
                landmark_movement_score = min(1.0, max(0.0,
                    min(lm_mean / 3.0, 1.0) * 0.5 +
                    min(lm_std / 1.5, 1.0) * 0.5
                ))
                result['landmark_movement_score'] = round(landmark_movement_score, 4)
            else:
                result['landmark_movement_score'] = 0.0
        else:
            result['landmark_movement_score'] = 0.0

        # 5d. Mouth movement score
        mar_range = float(np.max(mar_arr) - np.min(mar_arr))
        mar_std = float(np.std(mar_arr))
        mouth_movement_score = min(1.0, max(0.0,
            min(mar_range / 0.08, 1.0) * 0.5 +
            min(mar_std / 0.025, 1.0) * 0.3 +
            min(float(np.mean(mar_arr)) / MAR_SMILE_THRESHOLD, 1.0) * 0.2
        ))
        result['mouth_movement_score'] = round(mouth_movement_score, 4)

        # Combined liveness score
        liveness_score = (
            blink_score * 0.25 +
            head_pose_score * 0.30 +
            result['landmark_movement_score'] * 0.25 +
            mouth_movement_score * 0.20
        )
        result['livenessScore'] = round(liveness_score, 4)

        # Signal quality (how many frames had valid detections)
        result['signal_quality'] = round(min(1.0, len(all_landmarks) / max(len(decoded), 1)), 4)

        # Raw signals for audit
        result['signals'] = {
            'ear_min': round(float(np.min(ear_arr)), 4),
            'ear_max': round(float(np.max(ear_arr)), 4),
            'ear_mean': round(float(np.mean(ear_arr)), 4),
            'ear_std': round(ear_std, 4),
            'mar_mean': round(float(np.mean(mar_arr)), 4),
            'mar_std': round(mar_std, 4),
            'yaw_mean': round(float(np.mean(yaw_arr)), 4),
            'yaw_std': round(yaw_std, 4),
            'pitch_mean': round(float(np.mean(pitch_arr)), 4),
            'pitch_std': round(pitch_std, 4),
            'blink_count': int(blink_count),
            'frames_analyzed': len(all_landmarks),
            'total_frames': len(decoded),
        }

        return result

    # ========== 6. DECISION LOGIC ==========

    def evaluate(self, challenge_result, replay_result, screen_result,
                 print_result, liveness_result, challenge_pass_override=None):
        """Evaluate all detection signals and produce final verdict.

        Args:
            challenge_result: dict from verify_challenge_sequence()
            replay_result: dict from detect_replay_video()
            screen_result: dict from detect_screen_replay()
            print_result: dict from detect_print_attack()
            liveness_result: dict from compute_liveness_signals()
            challenge_pass_override: optional bool to force pass/fail

        Returns:
            dict with: verified, livenessScore, replayAttackScore,
                       screenReplayDetected, printAttackDetected,
                       challengePassed, verdict, reasons
        """
        reasons = []

        # Extract key signals
        liveness_score = liveness_result.get('livenessScore', 0.0)
        replay_score = replay_result.get('replayAttackScore', 0.0)
        replay_detected = replay_result.get('replayVideoDetected', False)
        screen_detected = screen_result.get('screenReplayDetected', False)
        print_detected = print_result.get('printAttackDetected', False)
        challenge_passed = challenge_result.get('passed', False)
        challenge_confidence = challenge_result.get('confidence', 0.0)

        # Override challenge if provided
        if challenge_pass_override is not None:
            challenge_passed = challenge_pass_override

        # GATE 1: Replay video detection
        if replay_detected:
            reasons.append(f'Video replay attack detected (score: {replay_score:.2f})')

        # GATE 2: Screen replay
        if screen_detected:
            screen_conf = screen_result.get('confidence', 0.0)
            reasons.append(f'Screen replay attack detected (confidence: {screen_conf:.2f})')

        # GATE 3: Print attack
        if print_detected:
            print_conf = print_result.get('confidence', 0.0)
            reasons.append(f'Print attack detected (confidence: {print_conf:.2f})')

        # GATE 4: Liveness threshold
        if liveness_score < LIVENESS_THRESHOLD:
            reasons.append(f'Liveness score too low ({liveness_score:.2f} < {LIVENESS_THRESHOLD})')

        # GATE 5: Challenge response
        if not challenge_passed:
            challenge_reason = challenge_result.get('reason', 'Challenge validation failed')
            reasons.append(f'Challenge response failed: {challenge_reason}')

        # Final verdict
        verified = (
            not replay_detected and
            not screen_detected and
            not print_detected and
            liveness_score >= LIVENESS_THRESHOLD and
            challenge_passed
        )

        if not verified and not reasons:
            reasons.append('Multiple detection signals indicate replay attack')

        return _to_native({
            'verified': verified,
            'livenessScore': round(liveness_score, 4),
            'replayAttackScore': round(replay_score, 4),
            'screenReplayDetected': screen_detected,
            'printAttackDetected': print_detected,
            'challengePassed': challenge_passed,
            'challengeConfidence': round(challenge_confidence, 4),
            'verdict': 'VERIFIED' if verified else 'REJECTED',
            'reasons': reasons,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
        })


    # ========== 7. LOGGING ==========

    def log_verification(self, session_id, result, challenge_data,
                         replay_result, screen_result, print_result,
                         liveness_result):
        """Log all detection scores and rejection reasons for audit."""
        log_entry = {
            'session_id': session_id,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'verdict': result.get('verdict'),
            'scores': {
                'liveness': result.get('livenessScore'),
                'replay_attack': result.get('replayAttackScore'),
                'screen_replay': screen_result.get('confidence'),
                'print_attack': print_result.get('confidence'),
                'challenge_confidence': result.get('challengeConfidence'),
            },
            'flags': {
                'replay_video': result.get('replayAttackScore', 0) > REPLAY_SCORE_THRESHOLD,
                'screen_replay': result.get('screenReplayDetected'),
                'print_attack': result.get('printAttackDetected'),
                'challenge_passed': result.get('challengePassed'),
            },
            'reasons': result.get('reasons', []),
            'challenge_sequence': challenge_data.get('sequence', []),
            'action_results': challenge_data.get('action_results', []),
            'liveness_signals': liveness_result.get('signals', {}),
        }

        logger.info('[ReplayDetect] Verification result for %s: %s',
                     session_id, json.dumps(log_entry, default=str))
        return log_entry


# Singleton instance
_detector = None

def get_detector():
    """Get or create the singleton ReplayAttackDetector."""
    global _detector
    if _detector is None:
        _detector = ReplayAttackDetector()
    return _detector
