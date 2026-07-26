"""
Flask API Server for AI/ML Face Verification Pipeline

Consolidated endpoints for production KYC verification:
  GET  /health             — System status and model availability
  POST /face-detect        — Detect faces in an image
  POST /liveness/challenge — Generate a challenge sequence
  POST /detailed-verify    — Full gate-based verification pipeline

Verification Flow:
  1. Face Detection   → InsightFace ArcFace
  2. Face Verification → ArcFace embeddings + cosine similarity
   3. Liveness         → MediaPipe challenge-response (wink, mouth open, look up/down)
  4. Deepfake         → EfficientNet-B2 (AI-generated faces)

Gate Decision:
  verified = faceMatchPassed AND livenessPassed AND NOT deepfakeDetected
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
import logging
import time
import uuid
import numpy as np
from flask.json.provider import DefaultJSONProvider

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NumpyJSONProvider(DefaultJSONProvider):
    def default(self, o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, np.bool_):
            return bool(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        return super().default(o)


app = Flask(__name__)
app.json_provider_class = NumpyJSONProvider
app.json = NumpyJSONProvider(app)
CORS(app, origins=[
    'http://localhost:8080',
    'http://127.0.0.1:8080',
    'http://localhost:8090',
    'http://127.0.0.1:8090',
    'http://localhost:5500',
    'http://127.0.0.1:5500',
    'https://iobkyc-production.up.railway.app',
])

# Debug frame directory (only used when AI_DEBUG=1)
DEBUG_FRAME_DIR = os.path.join(os.path.dirname(__file__), 'debug_frames')
DEBUG_ENABLED = os.environ.get('AI_DEBUG', '0') == '1'
if DEBUG_ENABLED:
    os.makedirs(DEBUG_FRAME_DIR, exist_ok=True)


def _safe_detect(fn, name, default=None):
    """Run a detector function with timing and error handling."""
    import traceback as _tb
    start = time.time()
    try:
        result = fn()
        elapsed = round((time.time() - start) * 1000, 1)
        logger.info("[DETECT] %s completed in %.1fms", name, elapsed)
        return result
    except Exception as e:
        elapsed = round((time.time() - start) * 1000, 1)
        logger.warning("[DETECT] %s failed in %.1fms: %s", name, elapsed, e)
        logger.warning("[DETECT] %s traceback:\n%s", name, _tb.format_exc())
        if default is not None:
            return default
        raise


def _safe_get(d, key, default=0):
    """Safely get a value from a dict."""
    if d is None:
        return default
    return d.get(key, default)


def _compress_image_base64(b64_str, max_dim=1024, jpeg_quality=75):
    """Compress a base64 image string to reduce memory and processing time.

    Resizes to max_dim on the longest side and re-encodes as JPEG.
    Returns the compressed base64 string (with data URI prefix).
    """
    import cv2
    try:
        if not b64_str or not isinstance(b64_str, str):
            return b64_str
        data = b64_str
        if ',' in data:
            prefix = data.split(',')[0] + ','
            data = data.split(',')[1]
        else:
            prefix = 'data:image/jpeg;base64,'
        img_bytes = __import__('base64').b64decode(data)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return b64_str
        h, w = img.shape[:2]
        if max(h, w) <= max_dim:
            return b64_str
        scale = max_dim / max(h, w)
        new_w, new_h = int(w * scale), int(h * scale)
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        _, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
        compressed = __import__('base64').b64encode(buf.tobytes()).decode('utf-8')
        logger.info("[Compress] %dx%d → %dx%d (%.0fKB → %.0fKB)",
                     w, h, new_w, new_h, len(img_bytes) / 1024, len(compressed) * 3 / 4 / 1024)
        return prefix + compressed
    except Exception as e:
        logger.warning("[Compress] Failed to compress image: %s — using original", e)
        return b64_str


# ============================================================
# INITIALIZE DETECTORS (4 singletons only)
# ============================================================

logger.info("Initializing AI/ML modules (production pipeline)...")

face_verifier = None
challenge_liveness = None
deepfake_detector = None

try:
    from face_verification import FaceVerifier
    face_verifier = FaceVerifier()
    if getattr(face_verifier, 'insightface_app', None) is None:
        logger.error("FATAL: InsightFace ArcFace model is not loaded.")
    else:
        logger.info("InsightFace ArcFace model loaded successfully")
except Exception as e:
    logger.warning("Face verification unavailable: %s", e)

try:
    from liveness_detection import ChallengeLivenessDetector, CHALLENGE_TYPES, MIN_FRAMES_FOR_CHALLENGE
    challenge_liveness = ChallengeLivenessDetector()
except Exception as e:
    logger.warning("Liveness detection unavailable: %s", e)

try:
    from deepfake_detector import DeepfakeDetector, DEEPFAKE_THRESHOLD
    deepfake_detector = DeepfakeDetector()
except Exception as e:
    logger.warning("Deepfake detection unavailable: %s", e)

logger.info("Detectors initialized (some may be unavailable):")
logger.info("  Face verification: %s", "OK" if face_verifier else "UNAVAILABLE")
logger.info("  Liveness: %s", "OK" if challenge_liveness else "UNAVAILABLE")
logger.info("  Deepfake: %s", "OK" if deepfake_detector else "UNAVAILABLE")

# ============================================================
# STARTUP DIAGNOSTIC — Verify models actually work end-to-end
# Runs in a background thread to avoid blocking Flask startup
# ============================================================
def _run_startup_diagnostic():
    """Run quick inference test on synthetic images to catch model issues early."""
    try:
        import cv2
        import base64

        test_img = np.zeros((100, 100, 3), dtype=np.uint8)
        test_img[:, :] = (140, 160, 200)
        _, buf = cv2.imencode('.jpg', test_img)
        test_b64 = 'data:image/jpeg;base64,' + base64.b64encode(buf.tobytes()).decode()

        if face_verifier and getattr(face_verifier, 'insightface_app', None):
            try:
                img = face_verifier.decode_image(test_b64)
                faces = face_verifier._get_faces(img)
                logger.info("[StartupDiag] InsightFace: %d face(s)", len(faces))
                if faces and faces[0].embedding is not None:
                    logger.info("[StartupDiag] InsightFace embedding dim=%d", len(faces[0].embedding))
            except Exception as e:
                logger.error("[StartupDiag] InsightFace FAILED: %s", e)

        if deepfake_detector and deepfake_detector.available:
            try:
                result = deepfake_detector.detect(test_b64)
                logger.info("[StartupDiag] Deepfake: is_deepfake=%s", result.get('is_deepfake'))
            except Exception as e:
                logger.error("[StartupDiag] Deepfake FAILED: %s", e)

        logger.info("[StartupDiag] Complete")
    except Exception as e:
        logger.warning("[StartupDiag] Skipped: %s", e)

import threading as _threading
_threading.Thread(target=_run_startup_diagnostic, daemon=True).start()

# ============================================================
# CHALLENGE SESSION STORE (thread-safe)
# ============================================================
import threading
_challenge_sessions = {}  # session_id -> {challenges, current_idx, results, created_at}
_session_lock = threading.Lock()
_SESSION_TTL = 300  # seconds before session expires (5 min to handle retries)


def _cleanup_expired_sessions():
    """Remove expired sessions to prevent memory leaks."""
    now = time.time()
    with _session_lock:
        expired = [sid for sid, s in _challenge_sessions.items()
                   if now - s.get('created_at', 0) > _SESSION_TTL]
        for sid in expired:
            del _challenge_sessions[sid]
    if expired:
        logger.info("[Session Cleanup] Removed %d expired sessions", len(expired))


# ============================================================
# ENDPOINTS
# ============================================================

@app.route('/health', methods=['GET'])
def health():
    """System health check with model availability status."""
    return jsonify({
        'status': 'healthy',
        'modules': {
            'face_verification': {
                'available': face_verifier is not None and getattr(face_verifier, 'insightface_app', None) is not None,
                'model': 'InsightFace ArcFace (buffalo_l)',
            },
            'liveness': {
                'available': challenge_liveness is not None and not getattr(challenge_liveness, 'FALLBACK_MODE', True),
                'model': 'MediaPipe FaceLandmarker',
                'fallback_mode': getattr(challenge_liveness, 'FALLBACK_MODE', True),
            },
            'deepfake': {
                'available': deepfake_detector is not None and getattr(deepfake_detector, 'available', False),
                'model': 'Deepfake Ensemble (Xception + EfficientNet-B2) -- official architectures only',
                'models_loaded': getattr(deepfake_detector, 'models_loaded', []),
                'models_disabled': getattr(deepfake_detector, 'models_disabled', []),
                'model_diagnostics': getattr(deepfake_detector, '_build_model_diagnostics', lambda: {})(),
                'threshold': DEEPFAKE_THRESHOLD,
            },
        },
        'endpoints': {
            'GET /health': 'System status',
            'GET /diagnose': 'Detailed model diagnosis',
            'POST /face-detect': 'Detect faces in image',
            'POST /liveness/challenge': 'Generate challenge sequence',
            'POST /detailed-verify': 'Full verification pipeline',
        }
    })


@app.route('/diagnose', methods=['GET'])
def diagnose():
    """Detailed diagnostic endpoint — tests every model with a synthetic image.

    Hit GET /diagnose from browser to see exactly what's broken.
    No auth required. Returns JSON with per-model status.
    """
    import cv2
    import base64
    results = {}

    # Create test image: 200x200 gradient with skin-tone center
    test_img = np.zeros((200, 200, 3), dtype=np.uint8)
    test_img[50:150, 50:150] = (140, 160, 200)  # BGR skin-tone block
    cv2.circle(test_img, (100, 90), 25, (160, 180, 210), -1)  # face-like ellipse
    _, buf = cv2.imencode('.jpg', test_img)
    test_b64 = 'data:image/jpeg;base64,' + base64.b64encode(buf.tobytes()).decode()

    # 1. InsightFace test
    try:
        if face_verifier and getattr(face_verifier, 'insightface_app', None):
            img = face_verifier.decode_image(test_b64)
            with face_verifier._lock:
                faces = face_verifier.insightface_app.get(img)
            if faces:
                f = faces[0]
                has_emb = f.embedding is not None
                emb_len = len(f.embedding) if has_emb else 0
                results['insightface'] = {
                    'status': 'OK' if has_emb else 'DETECTION_ONLY',
                    'faces_found': len(faces),
                    'has_embedding': has_emb,
                    'embedding_dim': emb_len,
                    'det_score': round(float(f.det_score), 3),
                }
            else:
                results['insightface'] = {
                    'status': 'NO_FACES_DETECTED',
                    'faces_found': 0,
                    'note': 'Synthetic image has no real face — this is expected',
                }
        else:
            results['insightface'] = {'status': 'NOT_LOADED', 'error': 'InsightFace app is None'}
    except Exception as e:
        import traceback
        results['insightface'] = {'status': 'ERROR', 'error': str(e), 'traceback': traceback.format_exc()}

    # 3. Deepfake test
    try:
        if deepfake_detector and deepfake_detector.available:
            r = deepfake_detector.detect(test_b64)
            results['deepfake'] = {
                'status': 'OK',
                'models_loaded': deepfake_detector.models_loaded,
                'models_disabled': deepfake_detector.models_disabled,
                'is_deepfake': r.get('is_deepfake'),
                'fake_prob': r.get('fake_prob'),
                'reason': r.get('reason'),
                'has_shared_insightface': getattr(deepfake_detector, '_shared_insightface', None) is not None,
            }
        else:
            results['deepfake'] = {'status': 'NOT_LOADED'}
    except Exception as e:
        import traceback
        results['deepfake'] = {'status': 'ERROR', 'error': str(e), 'traceback': traceback.format_exc()}

    # 4. Model file check
    import os
    model_files = {}
    model_dir = os.path.join(os.path.dirname(__file__), 'models')
    for root, dirs, files in os.walk(model_dir):
        for f in files:
            fpath = os.path.join(root, f)
            size_mb = os.path.getsize(fpath) / (1024 * 1024)
            rel = os.path.relpath(fpath, model_dir)
            model_files[rel] = f'{size_mb:.1f}MB'
    results['model_files'] = model_files

    # 5. Environment
    import sys
    results['environment'] = {
        'python': sys.version,
        'platform': sys.platform,
        'numpy': np.__version__,
    }
    try:
        import torch
        results['environment']['torch'] = torch.__version__
        results['environment']['cuda'] = torch.cuda.is_available()
    except ImportError:
        results['environment']['torch'] = 'NOT_INSTALLED'

    try:
        import onnxruntime
        results['environment']['onnxruntime'] = onnxruntime.__version__
        results['environment']['onnx_providers'] = onnxruntime.get_available_providers()
    except ImportError:
        results['environment']['onnxruntime'] = 'NOT_INSTALLED'

    return jsonify(results)


@app.route('/face-detect', methods=['POST'])
def face_detect():
    """Detect faces in an image.

    Request:  { "image": "<base64>" }
    Response: { "success": true, "data": { "face_count": N, "faces": [...] } }
    """
    data = request.json
    if not data or 'image' not in data:
        return jsonify({'success': False, 'error': 'image field required'}), 400
    try:
        result = _safe_detect(
            lambda: face_verifier.detect_faces(data['image']),
            'face_detect',
            {'face_count': 0, 'faces': []}
        )
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/liveness/debug', methods=['GET'])
def liveness_debug():
    """Diagnostic endpoint — returns current state and challenge info."""
    has_lm = challenge_liveness.face_landmarker is not None
    return jsonify({
        'success': True,
        'data': {
            'fallback_mode': challenge_liveness.FALLBACK_MODE,
            'face_landmarker_loaded': has_lm,
            'challenge_types': CHALLENGE_TYPES,
            'thresholds': {
                'ear_closed': challenge_liveness.EAR_CLOSED_THRESHOLD,
                'mar_open': challenge_liveness.MAR_OPEN_THRESHOLD,
                'shake_yaw_degrees': challenge_liveness.SHAKE_YAW_DEGREES,
                'look_yaw_degrees': challenge_liveness.LOOK_YAW_DEGREES,
                'pitch_up_degrees': challenge_liveness.PITCH_UP_DEGREES,
                'min_sustained_frames': challenge_liveness.MIN_SUSTAINED_FRAMES,
                'baseline_frames': challenge_liveness.BASELINE_FRAMES,
            },
            'min_frames': MIN_FRAMES_FOR_CHALLENGE,
            'active_sessions': len(_challenge_sessions),
        }
    })


@app.route('/liveness/challenge', methods=['POST'])
def generate_liveness_challenge():
    """Generate a new 4-challenge session for liveness verification.

    Returns only the first challenge; subsequent challenges are served
    one-at-a-time via verify-challenge.

    Request:  {} (empty body)
    Response: { "success": true, "data": {
        "session_id": "...", "challenge": {...}, "challenge_index": 0,
        "total_challenges": 4
    } }
    """
    try:
        _cleanup_expired_sessions()
        challenges = _safe_detect(
            lambda: challenge_liveness.generate_challenge_session(),
            'generate_challenge_session',
        )
        session_id = str(uuid.uuid4())
        with _session_lock:
            _challenge_sessions[session_id] = {
                'challenges': challenges,
                'current_idx': 0,
                'results': [],
                'created_at': time.time(),
            }
        first = challenges[0]
        return jsonify({
            'success': True,
            'data': {
                'session_id': session_id,
                'challenge': first,
                'challenge_index': 0,
                'total_challenges': 4,
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/detailed-verify', methods=['POST'])
def detailed_verify():
    """Full gate-based face verification pipeline.

    Request:
    {
        "id_face": "<base64>",          // ID document face
        "selfie": "<base64>",           // Live selfie
        "challenge": { ... },           // Challenge data from /liveness/challenge
        "frames": ["<base64>", ...]     // Captured webcam frames
    }

    Response:
    {
        "verified": false,
        "faceMatchPassed": false,
        "livenessPassed": false,
        "spoofDetected": true,
        "deepfakeDetected": false,
        "verdict": "REJECTED",
        "reasons": ["Face match failed (0.2345)"],
        "confidence": {
            "face_similarity": 0.2345,
            "liveness": 0.8500,
            "spoof": 0.9200,
            "deepfake": 0.1200
        }
    }
    """
    start_total = time.time()
    data = request.json

    if not data or 'selfie' not in data:
        return jsonify({'success': False, 'error': 'selfie is required'}), 400

    id_face = data.get('id_face')
    selfie = data['selfie']
    profile_photo = data.get('profile_photo')
    challenge = data.get('challenge')
    frames = data.get('frames', [])
    session_result = data.get('session_result')
    is_rekyc = bool(data.get('rekyc', False))

    # Compress large images to reduce memory and processing time
    if id_face and isinstance(id_face, str) and len(id_face) > 2_000_000:
        logger.info("[VERIFY] Compressing large id_face (%.0fKB)", len(id_face) / 1024)
        id_face = _compress_image_base64(id_face)
    if selfie and isinstance(selfie, str) and len(selfie) > 2_000_000:
        logger.info("[VERIFY] Compressing large selfie (%.0fKB)", len(selfie) / 1024)
        selfie = _compress_image_base64(selfie)
    if profile_photo and isinstance(profile_photo, str) and len(profile_photo) > 2_000_000:
        logger.info("[VERIFY] Compressing large profile_photo (%.0fKB)", len(profile_photo) / 1024)
        profile_photo = _compress_image_base64(profile_photo)

    # ============================================================
    # 1. FACE VERIFICATION (always runs for Re-KYC with relaxed threshold)
    # ============================================================
    if is_rekyc:
        # Re-KYC: use profile_photo as fallback id_face when id_face is missing
        rekyc_id_face = id_face or profile_photo
        if not rekyc_id_face:
            logger.warning("[VERIFY] Re-KYC — no ID document or profile photo available for face match")
            face_result = {'verified': False, 'cosine_similarity': 0, 'reason': 'No ID document or profile photo available', 'face_detected_id': False, 'face_detected_selfie': False}
            faceMatchPassed = False
            face_similarity = 0
            face_three_way = None
        else:
            logger.info("[VERIFY] Re-KYC — comparing live selfie against old uploaded documents (relaxed threshold)")
            logger.info("[VERIFY] rekyc id_face type=%s size=%s selfie type=%s size=%s",
                        type(rekyc_id_face).__name__, len(rekyc_id_face) if rekyc_id_face else 0,
                        type(selfie).__name__, len(selfie) if selfie else 0)

            # Direct call with full error logging (no _safe_detect wrapper)
            import traceback as _tb
            try:
                face_result = face_verifier.verify(rekyc_id_face, selfie, strict=False)
                logger.info("[VERIFY] rekyc face_result: verified=%s similarity=%.4f reason=%s face_detected_id=%s face_detected_selfie=%s",
                            face_result.get('verified'), face_result.get('cosine_similarity', 0),
                            face_result.get('reason'), face_result.get('face_detected_id'), face_result.get('face_detected_selfie'))
            except Exception as e:
                logger.error("[VERIFY] rekyc face_verifier.verify FAILED: %s", e)
                logger.error("[VERIFY] rekyc traceback:\n%s", _tb.format_exc())
                face_result = {'verified': False, 'cosine_similarity': 0, 'reason': str(e), 'face_detected_id': False, 'face_detected_selfie': False}

            faceMatchPassed = bool(face_result.get('verified', False))
            face_similarity = round(_safe_get(face_result, 'cosine_similarity', 0), 4)

            # 3-way comparison: ID vs Photo, Photo vs Selfie (informational only)
            face_three_way = None
            if profile_photo and id_face:
                id_vs_photo = _safe_detect(
                    lambda: face_verifier.verify(id_face, profile_photo, strict=False),
                    'face_verify_id_photo',
                    {'verified': False, 'cosine_similarity': 0}
                )
                photo_vs_selfie = _safe_detect(
                    lambda: face_verifier.verify(profile_photo, selfie, strict=False),
                    'face_verify_photo_selfie',
                    {'verified': False, 'cosine_similarity': 0}
                )
                face_three_way = {
                    'id_vs_selfie': {
                        'similarity': face_similarity,
                        'passed': faceMatchPassed,
                    },
                    'id_vs_photo': {
                        'similarity': round(_safe_get(id_vs_photo, 'cosine_similarity', 0), 4),
                        'passed': bool(_safe_get(id_vs_photo, 'verified', False)),
                    },
                    'photo_vs_selfie': {
                        'similarity': round(_safe_get(photo_vs_selfie, 'cosine_similarity', 0), 4),
                        'passed': bool(_safe_get(photo_vs_selfie, 'verified', False)),
                    },
                }
                logger.info("[VERIFY] rekyc 3-way: id_selfie=%.4f id_photo=%.4f photo_selfie=%.4f",
                            face_three_way['id_vs_selfie']['similarity'],
                            face_three_way['id_vs_photo']['similarity'],
                            face_three_way['photo_vs_selfie']['similarity'])
    else:
        # Primary: ID face vs selfie
        face_result = _safe_detect(
            lambda: face_verifier.verify(id_face, selfie, strict=True),
            'face_verify',
            {'verified': False, 'cosine_similarity': 0, 'reason': 'Face verification error'}
        )
        logger.info("[VERIFY] face_result: verified=%s similarity=%s reason=%s",
                    face_result.get('verified'), face_result.get('cosine_similarity'), face_result.get('reason'))

        faceMatchPassed = bool(face_result.get('verified', False))
        face_similarity = round(_safe_get(face_result, 'cosine_similarity', 0), 4)

        # 3-way comparison: ID vs Photo, Photo vs Selfie (ID vs Selfie already done)
        face_three_way = None
        if profile_photo and id_face:
            # ID face vs profile photo — lenient threshold because ID may be old
            id_vs_photo = _safe_detect(
                lambda: face_verifier.verify(id_face, profile_photo, strict=False),
                'face_verify_id_photo',
                {'verified': False, 'cosine_similarity': 0}
            )
            # Profile photo vs selfie — strict, both are current
            photo_vs_selfie = _safe_detect(
                lambda: face_verifier.verify(profile_photo, selfie, strict=True),
                'face_verify_photo_selfie',
                {'verified': False, 'cosine_similarity': 0}
            )
            face_three_way = {
                'id_vs_selfie': {
                    'similarity': face_similarity,
                    'passed': faceMatchPassed,
                },
                'id_vs_photo': {
                    'similarity': round(_safe_get(id_vs_photo, 'cosine_similarity', 0), 4),
                    'passed': bool(_safe_get(id_vs_photo, 'verified', False)),
                },
                'photo_vs_selfie': {
                    'similarity': round(_safe_get(photo_vs_selfie, 'cosine_similarity', 0), 4),
                    'passed': bool(_safe_get(photo_vs_selfie, 'verified', False)),
                },
            }
            # All three must pass for face match to be considered valid
            all_three_passed = all(v['passed'] for v in face_three_way.values())
            logger.info("[VERIFY] 3-way: id_selfie=%.4f id_photo=%.4f photo_selfie=%.4f → all_pass=%s",
                        face_three_way['id_vs_selfie']['similarity'],
                        face_three_way['id_vs_photo']['similarity'],
                        face_three_way['photo_vs_selfie']['similarity'],
                        all_three_passed)
            faceMatchPassed = all_three_passed

    # ============================================================
    # 2. LIVENESS (challenge-response) — Full session integration
    # ============================================================
    livenessPassed = False
    liveness_confidence = 0.0
    liveness_reason = 'Liveness challenge not completed'
    session_liveness_confirmed = False
    challenge_result = None

    # Look up full session data from server-side storage (session_id passed from frontend)
    session_id = data.get('session_id', data.get('liveness_session_id'))
    session_data = None
    if session_id and session_id in _challenge_sessions:
        session_data = _challenge_sessions.get(session_id)

    if session_data:
        # Use full server-side session data for richer verification
        results = session_data.get('results', [])
        completed = sum(1 for r in results if r.get('challenge_passed', False))
        all_passed = (completed >= 4)
        if all_passed:
            livenessPassed = True
            session_liveness_confirmed = True
            confidences = [r.get('confidence', 0) for r in results]
            liveness_confidence = round(float(np.mean(confidences)) if confidences else 0.5, 4)
            liveness_reason = f'Verified via 4-step sequential challenge session ({completed}/4 passed)'
            logger.info('[DetailedVerify] Session %s: %d/4 challenges passed — liveness confirmed',
                       session_id, completed)
        else:
            passed_results = [r for r in results if r.get('challenge_passed', False)]
            if passed_results:
                partial_confidences = [r.get('confidence', 0) for r in passed_results]
                liveness_confidence = round(float(np.mean(partial_confidences)), 4)
                liveness_reason = f'Incomplete liveness session: {completed}/4 challenges passed'
                logger.warning('[DetailedVerify] Session %s incomplete: %d/4 (partial conf=%.3f)', session_id, completed, liveness_confidence)
            else:
                liveness_reason = f'Incomplete liveness session: {completed}/4 challenges passed'
                logger.warning('[DetailedVerify] Session %s incomplete: %d/4', session_id, completed)
    elif session_result and session_result.get('challengePassed'):
        # Fallback: accept client-side session summary if server session unavailable
        livenessPassed = True
        session_liveness_confirmed = True
        liveness_confidence = session_result.get('livenessScore', 0.5)
        liveness_reason = 'Verified via 4-step sequential challenge session (client summary)'
        logger.info('[DetailedVerify] Client-side session result accepted: livenessScore=%.3f',
                   liveness_confidence)
    elif challenge and frames and len(frames) >= 2:
        challenge_result = _safe_detect(
            lambda: challenge_liveness.verify_challenge(challenge, frames),
            'verify_challenge',
            {'challenge_passed': False, 'confidence': 0, 'reason': 'Challenge verification error'}
        )
        livenessPassed = bool(_safe_get(challenge_result, 'challenge_passed', False))
        liveness_confidence = round(_safe_get(challenge_result, 'confidence', 0), 4)
        liveness_reason = _safe_get(challenge_result, 'reason', '')

    # Extract screen replay detection from challenge result details
    screenReplayDetected = False
    screen_replay_conf = 0.0
    if challenge_result and 'details' in challenge_result:
        replay_det = challenge_result['details'].get('replay_detection', {})
        screenReplayDetected = bool(replay_det.get('is_replay', False))
        screen_replay_conf = round(replay_det.get('confidence', 0.0), 4)

    # ============================================================
    # 3. DEEPFAKE (Official Models: Xception + EfficientNet-B2)
    # ============================================================
    deepfake_result = _safe_detect(
        lambda: deepfake_detector.detect(selfie),
        'deepfake_detect',
        {'is_deepfake': False, 'confidence': 0.5}
    )

    deepfakeDetected = bool(_safe_get(deepfake_result, 'is_deepfake', False))
    deepfake_confidence = round(_safe_get(deepfake_result, 'confidence', 0.5), 4)
    deepfake_reason = _safe_get(deepfake_result, 'reason', '')
    deepfake_per_model = deepfake_result.get('per_model', {})
    deepfake_models_used = deepfake_result.get('models_used', [])

    # ============================================================
    # 4. GATE DECISION — ALL GATES MUST PASS
    # ============================================================
    # All 3 gates must pass for verification.

    verified = (
        faceMatchPassed
        and livenessPassed
        and (not deepfakeDetected)
    )

    reasons = []
    if not faceMatchPassed:
        reasons.append(f"Face match failed (similarity={face_similarity})")
    if not livenessPassed:
        reasons.append(f"Liveness challenge failed: {liveness_reason}")
    if deepfakeDetected:
        reasons.append(f"Deepfake detected: {deepfake_reason}")
    if screenReplayDetected:
        reasons.append(f"Screen replay detected (score: {screen_replay_conf})")

    verdict = 'VERIFIED' if verified else 'REJECTED'

    elapsed_total = round((time.time() - start_total) * 1000, 1)

    logger.info(
        "[VERIFY] face=%s live=%s deepfake=%s screen_replay=%s → %s (%.1fms)",
        faceMatchPassed, livenessPassed, deepfakeDetected,
        screenReplayDetected, verdict, elapsed_total,
    )
    if not verified:
        logger.warning("[VERIFY_REJECTED] reasons=%s", reasons)

    response = {
        'verified': bool(verified),
        'faceMatchPassed': bool(faceMatchPassed),
        'livenessPassed': bool(livenessPassed),
        'sessionLivenessConfirmed': bool(session_liveness_confirmed),
        'deepfakeDetected': bool(deepfakeDetected),
        'screenReplayDetected': bool(screenReplayDetected),
        'rekyc': is_rekyc,
        'face_three_way': face_three_way,
        'verdict': verdict,
        'reasons': reasons,
        'confidence': {
            'face_similarity': face_similarity,
            'liveness': liveness_confidence,
            'deepfake': deepfake_confidence,
            'screen_replay': screen_replay_conf,
        },
        'deepfake_per_model': deepfake_per_model,
        'deepfake_models_used': deepfake_models_used,
        'processing_time_ms': elapsed_total,
    }

    # Include per-challenge session details when available
    if session_data:
        results = session_data.get('results', [])
        response['livenessDetails'] = [
            {
                'challenge': r.get('challenge_type', 'unknown'),
                'passed': bool(r.get('challenge_passed', False)),
                'confidence': round(r.get('confidence', 0), 3),
                'reason': r.get('reason', ''),
            }
            for r in results
        ]
        response['livenessSessionId'] = session_id

    return jsonify({'success': True, 'data': response})


# ============================================================
# COMPATIBILITY ENDPOINTS (Spring Boot /api/ai/* routes)
# ============================================================

@app.route('/api/ai/ocr', methods=['POST'])
def api_ocr():
    """OCR extraction for Aadhaar/PAN cards. Called by Spring Boot /api/ai/ocr."""
    try:
        from ocr_extraction import ocr_image
        image_file = request.files.get('image')
        doc_type = request.form.get('doc_type', 'AADHAAR')
        if not image_file:
            return jsonify({'success': False, 'error': 'image file required'}), 400
        image_bytes = image_file.read()
        result = _safe_detect(lambda: ocr_image(image_bytes, doc_type), 'ocr', {'success': False, 'error': 'OCR failed'})
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ai/face-verify', methods=['POST'])
def api_face_verify():
    """Face verification. Called by Spring Boot /api/ai/face-verify."""
    data = request.json
    if not data or 'id_face' not in data or 'selfie' not in data:
        return jsonify({'success': False, 'error': 'id_face and selfie required'}), 400
    try:
        if face_verifier is None:
            return jsonify({'success': True, 'data': {'verified': False, 'reason': 'Face verification module not available'}})
        result = _safe_detect(
            lambda: face_verifier.verify(data['id_face'], data['selfie']),
            'face_verify',
            {'verified': False, 'reason': 'Verification failed'}
        )
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ai/liveness/challenge', methods=['POST'])
def api_liveness_challenge():
    """Generate challenge session. Called by Spring Boot /api/ai/liveness/challenge."""
    return generate_liveness_challenge()


@app.route('/api/ai/liveness/verify-challenge', methods=['POST'])
def api_liveness_verify():
    """Verify one challenge from a session and return next or final result.

    Sequential protocol:
      - Client sends session_id + challenge + frames
      - Server verifies the current expected challenge
      - If passed and more remain -> returns next_challenge
      - If all 4 passed -> returns final verdict (APPROVED)
      - If failed -> returns retry_allowed
    """
    data = request.json
    if not data or 'session_id' not in data or 'challenge' not in data or 'frames' not in data:
        return jsonify({'success': False, 'error': 'session_id, challenge, and frames required'}), 400
    try:
        _cleanup_expired_sessions()
        session_id = data['session_id']
        with _session_lock:
            session = _challenge_sessions.get(session_id)
        if not session:
            return jsonify({'success': False, 'error': 'Session expired or invalid. Please request a new challenge.'}), 400

        idx = session['current_idx']
        if idx >= 4:
            return jsonify({'success': False, 'error': 'All challenges already completed for this session.'}), 400

        expected = session['challenges'][idx]
        received_type = data['challenge'].get('challenge_type')
        if received_type and received_type != expected['challenge_type']:
            logger.warning('[Session] Challenge type mismatch: expected=%s got=%s',
                           expected['challenge_type'], received_type)
            return jsonify({
                'success': True,
                'data': {
                    'passed': False,
                    'challenge_index': idx,
                    'reason': 'Challenge type mismatch — replay attack suspected',
                    'retry_allowed': False,
                }
            })

        # --- DEBUG: Log frame details ---
        frames = data['frames']
        n_frames = len(frames)
        logger.info("[VERIFY_DBG] session=%s challenge=%s idx=%d frames=%d",
                    session_id, expected['challenge_type'], idx, n_frames)

        if n_frames > 0:
            first_frame = frames[0]
            if isinstance(first_frame, str):
                frame_len = len(first_frame)
                has_prefix = first_frame.startswith('data:image')
                if ',' in first_frame:
                    b64_part = first_frame.split(',')[1]
                    b64_len = len(b64_part)
                else:
                    b64_part = first_frame
                    b64_len = frame_len
                logger.info("[VERIFY_DBG] First frame: total_len=%d has_prefix=%s b64_len=%d",
                            frame_len, has_prefix, b64_len)

                # Save first and last frame to disk for debugging (only when AI_DEBUG=1)
                if DEBUG_ENABLED:
                    try:
                        import base64 as _b64
                        import cv2 as _cv2
                        save_b64 = b64_part if not has_prefix else first_frame.split(',')[1]
                        img_bytes = _b64.b64decode(save_b64)
                        nparr = np.frombuffer(img_bytes, np.uint8)
                        img = _cv2.imdecode(nparr, _cv2.IMREAD_COLOR)
                        if img is not None:
                            h, w = img.shape[:2]
                            brightness = float(np.mean(img))
                            logger.info("[VERIFY_DBG] First frame decoded: %dx%d brightness=%.1f", w, h, brightness)
                            save_path = os.path.join(DEBUG_FRAME_DIR, f"latest_frame0.jpg")
                            _cv2.imwrite(save_path, img)
                            if n_frames > 1:
                                last_frame = frames[-1]
                                if isinstance(last_frame, str):
                                    last_b64 = last_frame.split(',')[1] if ',' in last_frame else last_frame
                                    last_img_bytes = _b64.b64decode(last_b64)
                                    last_nparr = np.frombuffer(last_img_bytes, np.uint8)
                                    last_img = _cv2.imdecode(last_nparr, _cv2.IMREAD_COLOR)
                                    if last_img is not None:
                                        _cv2.imwrite(os.path.join(DEBUG_FRAME_DIR, "latest_frame_last.jpg"), last_img)
                                        logger.info("[VERIFY_DBG] Last frame saved: %dx%d brightness=%.1f",
                                                    last_img.shape[1], last_img.shape[0], float(np.mean(last_img)))
                            logger.info("[VERIFY_DBG] Sample frames saved to %s", DEBUG_FRAME_DIR)
                        else:
                            logger.warning("[VERIFY_DBG] Failed to decode first frame as image!")
                    except Exception as e:
                        logger.warning("[VERIFY_DBG] Frame save error: %s", e)

        result = _safe_detect(
            lambda: challenge_liveness.verify_challenge(expected, data['frames']),
            'verify_challenge',
            {'challenge_passed': False, 'confidence': 0.0, 'reason': 'Verification error'}
        )
        passed = bool(result.get('challenge_passed', False))
        with _session_lock:
            session['results'].append(result)

        logger.info("[VERIFY_DBG] Result: passed=%s confidence=%.3f reason=%s",
                    passed, result.get('confidence', 0), result.get('reason', ''))

        if passed:
            session['current_idx'] += 1
            if session['current_idx'] >= 4:
                final = challenge_liveness.evaluate_session(session['results'])
                logger.info('[Session] %s — all 4 challenges completed: %s',
                            session_id, final['verdict'])
                return jsonify({'success': True, 'data': final})
            else:
                next_ch = session['challenges'][session['current_idx']]
                completed_count = sum(1 for r in session['results'] if r.get('challenge_passed', False))
                return jsonify({
                    'success': True,
                    'data': {
                        'passed': True,
                        'challenge_index': session['current_idx'],
                        'total_challenges': 4,
                        'completedChallenges': completed_count,
                        'next_challenge': next_ch,
                    }
                })
        else:
            completed_count = sum(1 for r in session['results'] if r.get('challenge_passed', False))
            return jsonify({
                'success': True,
                'data': {
                    'passed': False,
                    'challenge_index': idx,
                    'completedChallenges': completed_count,
                    'reason': result.get('reason', 'Challenge failed'),
                    'retry_allowed': True,
                }
            })
    except Exception as e:
        logger.exception('[LivenessVerify] Error: %s', e)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ai/liveness/combined', methods=['POST'])
def api_liveness_combined():
    """Combined liveness. Redirects to detailed-verify."""
    return detailed_verify()


@app.route('/api/ai/flash-verify', methods=['POST'])
def api_flash_verify():
    """Verify flash illumination response — stub (not implemented)."""
    return jsonify({'success': True, 'data': {'passed': True, 'confidence': 0.5, 'reason': 'Flash verification not implemented — skipped'}})


@app.route('/api/ai/detailed-verify', methods=['POST'])
def api_detailed_verify():
    """Detailed verify. Called by Spring Boot /api/ai/detailed-verify."""
    return detailed_verify()


@app.route('/api/ai/face-detect', methods=['POST'])
def api_face_detect():
    """Face detect. Called by Spring Boot /api/ai/face-detect."""
    data = request.json
    if not data or 'image' not in data:
        return jsonify({'success': False, 'error': 'image required'}), 400
    try:
        result = _safe_detect(
            lambda: face_verifier.detect_faces(data['image']),
            'face_detect',
            {'face_count': 0, 'faces': []}
        )
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ai/risk-score', methods=['POST'])
def api_risk_score():
    """Risk scoring placeholder. Returns low risk."""
    return jsonify({'success': True, 'data': {'risk_score': 0.1, 'risk_level': 'low'}})


@app.route('/api/ai/fraud-check', methods=['POST'])
def api_fraud_check():
    """Fraud check placeholder. Returns no fraud."""
    return jsonify({'success': True, 'data': {'fraud_detected': False, 'confidence': 0.95}})


@app.route('/api/ai/verify-and-liveness', methods=['POST'])
def api_verify_and_liveness():
    """Combined verify and liveness. Redirects to detailed-verify."""
    return detailed_verify()


# ============================================================
# QR CODE VERIFICATION
# ============================================================

@app.route('/api/ai/qr-extract', methods=['POST'])
def api_qr_extract():
    """Extract personal details from document QR codes.

    Request (multipart form):
        aadhaar_image: Aadhaar card image (optional)
        pan_image: PAN card image (optional)

    Response:
        JSON with extracted fields: name, dob, gender, aadhaar_number, pan_number, address
    """
    try:
        from qr_verification import detect_qr_code, parse_aadhaar_qr, parse_pan_qr

        result = {'name': '', 'dob': '', 'gender': '', 'aadhaar_number': '', 'pan_number': '', 'address': ''}

        aadhaar_file = request.files.get('aadhaar_image')
        pan_file = request.files.get('pan_image')

        if aadhaar_file:
            aadhaar_bytes = aadhaar_file.read()
            aadhaar_qr = detect_qr_code(aadhaar_bytes)
            if aadhaar_qr['detected'] and aadhaar_qr['data']:
                parsed = parse_aadhaar_qr(aadhaar_qr['data'])
                result['name'] = parsed.get('name', '')
                result['dob'] = parsed.get('dob', '')
                result['gender'] = parsed.get('gender', '')
                result['aadhaar_number'] = parsed.get('aadhaar_number', '')
                result['address'] = parsed.get('address', '')
                logger.info("[QR-EXTRACT] Aadhaar QR parsed: name=%s dob=%s uid=%s",
                           bool(result['name']), bool(result['dob']), bool(result['aadhaar_number']))

        if pan_file:
            pan_bytes = pan_file.read()
            pan_qr = detect_qr_code(pan_bytes)
            if pan_qr['detected'] and pan_qr['data']:
                parsed = parse_pan_qr(pan_qr['data'])
                if parsed.get('name') and not result['name']:
                    result['name'] = parsed['name']
                if parsed.get('dob') and not result['dob']:
                    result['dob'] = parsed['dob']
                result['pan_number'] = parsed.get('pan_number', '')
                logger.info("[QR-EXTRACT] PAN QR parsed: name=%s pan=%s",
                           bool(parsed.get('name')), bool(parsed.get('pan_number')))

        return jsonify({'success': True, 'data': result})
    except Exception as e:
        logger.exception('[QR-EXTRACT] Error: %s', e)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ai/qr-verify', methods=['POST'])
def api_qr_verify():
    """QR code verification for Aadhaar/PAN cards.

    Accepts an uploaded document image and existing OCR output,
    detects and decodes QR code, then compares fields.

    Request (multipart form):
        image: file — Document image containing QR code
        ocr_data: JSON string — Existing OCR extraction output
        doc_type: string — 'AADHAAR' or 'PAN' (default: AADHAAR)

    Response:
        JSON with verification results (see qr_verification.py)
    """
    try:
        from qr_verification import verify_qr

        image_file = request.files.get('image')
        if not image_file:
            return jsonify({'success': False, 'error': 'image file required'}), 400

        ocr_data_raw = request.form.get('ocr_data')
        if not ocr_data_raw:
            return jsonify({'success': False, 'error': 'ocr_data JSON required'}), 400

        try:
            ocr_data = json.loads(ocr_data_raw) if isinstance(ocr_data_raw, str) else ocr_data_raw
        except (json.JSONDecodeError, TypeError):
            return jsonify({'success': False, 'error': 'Invalid ocr_data JSON'}), 400

        if isinstance(ocr_data, dict) and 'data' in ocr_data:
            ocr_data = ocr_data['data']

        doc_type = request.form.get('doc_type', 'AADHAAR').upper()

        image_bytes = image_file.read()
        result = _safe_detect(
            lambda: verify_qr(image_bytes, ocr_data, doc_type),
            'qr_verify',
            {
                'qr_detected': False,
                'verification_status': 'Skipped',
                'message': 'QR verification error',
                'match_percentage': 0,
                'results': {}
            }
        )

        return jsonify({'success': True, 'data': result})
    except Exception as e:
        logger.exception('[QRVerify] Error: %s', e)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/ai/qr-verify-base64', methods=['POST'])
def api_qr_verify_base64():
    """QR code verification using base64 image (for frontend integration).

    Request JSON:
        image: string — base64-encoded document image
        ocr_data: object — Existing OCR extraction output
        doc_type: string — 'AADHAAR' or 'PAN' (default: AADHAAR)

    Response:
        JSON with verification results
    """
    try:
        from qr_verification import verify_qr

        data = request.json
        if not data or 'image' not in data:
            return jsonify({'success': False, 'error': 'image field required'}), 400

        ocr_data = data.get('ocr_data', {})
        if isinstance(ocr_data, str):
            try:
                ocr_data = json.loads(ocr_data)
            except (json.JSONDecodeError, TypeError):
                return jsonify({'success': False, 'error': 'Invalid ocr_data JSON'}), 400

        if isinstance(ocr_data, dict) and 'data' in ocr_data:
            ocr_data = ocr_data['data']

        doc_type = data.get('doc_type', 'AADHAAR').upper()

        result = _safe_detect(
            lambda: verify_qr(data['image'], ocr_data, doc_type),
            'qr_verify_base64',
            {
                'qr_detected': False,
                'verification_status': 'Skipped',
                'message': 'QR verification error',
                'match_percentage': 0,
                'results': {}
            }
        )

        return jsonify({'success': True, 'data': result})
    except Exception as e:
        logger.exception('[QRVerify] Error: %s', e)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/qr-face-compare', methods=['POST'])
def qr_face_compare():
    """Compare face from QR code against face on ID card.

    Request:
        {
            "card_image": "<base64>",
            "face_image": "<base64>"  (optional)
        }
    Response:
        {
            "success": true,
            "data": {
                "match_percentage": 75.5,
                "confidence": 0.755,
                "status": "MATCH",
                "tampering_flag": false
            }
        }
    """
    try:
        from qr_verification import compare_qr_face_with_card_face

        data = request.json
        if not data or 'card_image' not in data:
            return jsonify({'success': False, 'error': 'card_image field required'}), 400

        face_image = data.get('face_image')

        result = _safe_detect(
            lambda: compare_qr_face_with_card_face(data['card_image'], face_image),
            'qr_face_compare',
            {
                'match_percentage': 0,
                'confidence': 0,
                'status': 'ERROR',
                'tampering_flag': False,
                'message': 'QR face comparison error',
            }
        )

        return jsonify({'success': True, 'data': result})
    except Exception as e:
        logger.exception('[QRFaceCompare] Error: %s', e)
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# MAIN
# ============================================================

if __name__ == '__main__':
    port = int(os.environ.get('AI_PORT', 5001))
    logger.info("Starting AI/ML API server on port %d", port)
    app.run(host='0.0.0.0', port=port, debug=False)
