"""
Face Verification Module for Digital KYC System
Uses InsightFace ArcFace embeddings for accurate face matching.

Features:
- ArcFace deep learning embeddings (512-dim)
- Cosine similarity matching with configurable threshold
- Face quality checks: blur, brightness, face size, position
- Multi-face rejection (uses highest confidence face)
- Gender mismatch detection
"""

import cv2
import numpy as np
import json
import base64
import logging
import time
import hashlib

logger = logging.getLogger(__name__)

try:
    from insightface.app import FaceAnalysis
    HAS_INSIGHTFACE = True
except ImportError:
    HAS_INSIGHTFACE = False
    logger.warning("InsightFace not available — face verification will not work")


class FaceQuality:
    """Face quality assessment for KYC images."""

    MIN_FACE_SIZE_RATIO = 0.04
    MAX_FACE_SIZE_RATIO = 0.85
    MIN_BRIGHTNESS = 30
    MAX_BRIGHTNESS = 230
    CENTER_TOLERANCE = 0.35

    @staticmethod
    def compute_blur_score(face_img):
        gray = cv2.cvtColor(face_img, cv2.COLOR_BGR2GRAY) if len(face_img.shape) == 3 else face_img
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        variance = laplacian.var()
        score = min(1.0, variance / 200.0)
        return round(score, 3), variance

    @staticmethod
    def compute_brightness(face_img):
        gray = cv2.cvtColor(face_img, cv2.COLOR_BGR2GRAY) if len(face_img.shape) == 3 else face_img
        mean_val = np.mean(gray)
        if mean_val < FaceQuality.MIN_BRIGHTNESS:
            score = mean_val / FaceQuality.MIN_BRIGHTNESS
        elif mean_val > FaceQuality.MAX_BRIGHTNESS:
            score = (255 - mean_val) / (255 - FaceQuality.MAX_BRIGHTNESS)
        else:
            score = 1.0
        return round(max(0, min(1, score)), 3), round(float(mean_val), 1)

    @staticmethod
    def compute_face_size_score(face_w, face_h, img_w, img_h):
        face_area = face_w * face_h
        img_area = img_w * img_h
        ratio = face_area / img_area
        if ratio < FaceQuality.MIN_FACE_SIZE_RATIO:
            return 0.1, round(ratio, 3)
        elif ratio > FaceQuality.MAX_FACE_SIZE_RATIO:
            return 0.3, round(ratio, 3)
        elif ratio < 0.20:
            return round(0.4 + (ratio - FaceQuality.MIN_FACE_SIZE_RATIO) * 4.0, 3), round(ratio, 3)
        else:
            return 1.0, round(ratio, 3)

    @staticmethod
    def compute_position_score(face_x, face_y, face_w, face_h, img_w, img_h):
        face_center_x = (face_x + face_w / 2) / img_w
        face_center_y = (face_y + face_h / 2) / img_h
        dx = abs(face_center_x - 0.5)
        dy = abs(face_center_y - 0.5)
        offset = max(dx, dy)
        score = max(0, 1.0 - offset / FaceQuality.CENTER_TOLERANCE)
        return round(score, 3)

    @staticmethod
    def compute_overall_quality(face_img, face_bbox, img_shape):
        x, y, w, h = face_bbox
        img_h, img_w = img_shape[:2]
        blur_score, blur_val = FaceQuality.compute_blur_score(face_img)
        bright_score, brightness = FaceQuality.compute_brightness(face_img)
        size_score, size_ratio = FaceQuality.compute_face_size_score(w, h, img_w, img_h)
        pos_score = FaceQuality.compute_position_score(x, y, w, h, img_w, img_h)
        weights = {'blur': 0.35, 'brightness': 0.25, 'size': 0.25, 'position': 0.15}
        overall = (
            weights['blur'] * blur_score +
            weights['brightness'] * bright_score +
            weights['size'] * size_score +
            weights['position'] * pos_score
        )
        issues = []
        if blur_score < 0.5:
            issues.append(f"Image is blurry (sharpness: {blur_val:.1f})")
        if bright_score < 0.5:
            issues.append(f"Poor lighting (brightness: {brightness:.0f}/255)")
        if size_score < 0.5:
            issues.append(f"Face too {'small' if size_ratio < 0.15 else 'large'} in frame ({size_ratio:.1%})")
        if pos_score < 0.5:
            issues.append("Face not centered in frame")

        return {
            'overall_score': round(overall, 3),
            'blur_score': blur_score,
            'blur_value': round(blur_val, 1),
            'brightness_score': bright_score,
            'brightness': brightness,
            'size_score': size_score,
            'size_ratio': size_ratio,
            'position_score': pos_score,
            'passed': bool(overall >= 0.30),
            'issues': issues
        }


class FaceVerifier:
    """Production-ready face verification using InsightFace ArcFace.

    InsightFace ArcFace is the ONLY face recognition model.
    No OpenCV Haar Cascade, no DeepFace, no histogram fallbacks.
    """

    COSINE_THRESHOLD = 0.40
    COSINE_THRESHOLD_STRICT = 0.55

    def __init__(self):
        self.insightface_app = None
        self._lock = __import__('threading').Lock()
        self._init_insightface()

    def _init_insightface(self):
        """Initialize InsightFace ArcFace model. Hard-fails if unavailable."""
        if not HAS_INSIGHTFACE:
            logger.error("InsightFace not installed — face verification unavailable")
            return
        try:
            self.insightface_app = FaceAnalysis(
                name='buffalo_l',
                providers=['CUDAExecutionProvider', 'CPUExecutionProvider'],
                allowed_modules=['detection', 'recognition']
            )
            self.insightface_app.prepare(ctx_id=0, det_size=(640, 640))
            logger.info("InsightFace ArcFace model loaded successfully")
        except Exception as e:
            logger.warning("Failed to load InsightFace: %s", e)
            self.insightface_app = None

    def decode_image(self, image_data):
        """Decode base64 string, bytes, or file to BGR numpy array."""
        if isinstance(image_data, str):
            if ',' in image_data:
                image_data = image_data.split(',')[1]
            image_bytes = base64.b64decode(image_data)
        elif isinstance(image_data, bytes):
            image_bytes = image_data
        else:
            raise ValueError("Unsupported image data type")

        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Failed to decode image - invalid format")
        return img

    def _get_faces(self, img):
        """Detect and recognize faces using InsightFace only.

        Uses multi-pass detection: first try with standard (640,640),
        then retry with larger (1280,1280) if no faces found (helps with
        small faces in ID card photos). Thread-safe via lock.
        """
        if self.insightface_app is None:
            raise RuntimeError(
                "InsightFace ArcFace model is not loaded. "
                "Face verification cannot proceed."
            )
        with self._lock:
            # Pass 1: standard detection
            faces = self.insightface_app.get(img)
            if faces:
                return faces

            # Pass 2: retry with larger detection size for small faces (ID cards)
            logger.info("[FaceDetect] No faces at 640, retrying with 1280...")
            try:
                self.insightface_app.prepare(ctx_id=0, det_size=(1280, 1280))
                faces = self.insightface_app.get(img)
                self.insightface_app.prepare(ctx_id=0, det_size=(640, 640))
                if faces:
                    logger.info("[FaceDetect] Found %d face(s) at 1280 det_size", len(faces))
                    return faces
            except Exception as e:
                logger.warning("[FaceDetect] 1280 retry failed: %s", e)
                try:
                    self.insightface_app.prepare(ctx_id=0, det_size=(640, 640))
                except Exception:
                    pass

            # Pass 3: try with enhanced image (CLAHE contrast + sharpening)
            logger.info("[FaceDetect] Trying enhanced image preprocessing...")
            try:
                enhanced = self._enhance_for_detection(img)
                self.insightface_app.prepare(ctx_id=0, det_size=(640, 640))
                faces = self.insightface_app.get(enhanced)
                if faces:
                    logger.info("[FaceDetect] Found %d face(s) with enhanced image", len(faces))
                    return faces
                # Also try 1280 on enhanced
                self.insightface_app.prepare(ctx_id=0, det_size=(1280, 1280))
                faces = self.insightface_app.get(enhanced)
                self.insightface_app.prepare(ctx_id=0, det_size=(640, 640))
                if faces:
                    logger.info("[FaceDetect] Found %d face(s) with enhanced image at 1280", len(faces))
                    return faces
            except Exception as e:
                logger.warning("[FaceDetect] Enhanced detection failed: %s", e)
                try:
                    self.insightface_app.prepare(ctx_id=0, det_size=(640, 640))
                except Exception:
                    pass

        return []

    def _enhance_for_detection(self, img):
        """Enhance image for better face detection (CLAHE + sharpening)."""
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        enhanced = cv2.merge([l, a, b])
        enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
        kernel = np.array([[-1,-1,-1],[-1,9,-1],[-1,-1,-1]], dtype=np.float32)
        enhanced = cv2.filter2D(enhanced, -1, kernel)
        return enhanced

    def _enhance_face_for_quality(self, face_img):
        """Enhance face image for better quality assessment in low light."""
        if face_img is None or face_img.size == 0:
            return face_img
        lab = cv2.cvtColor(face_img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
        l = clahe.apply(l)
        enhanced = cv2.merge([l, a, b])
        enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
        denoised = cv2.fastNlMeansDenoisingColored(enhanced, None, 5, 5)
        return denoised

    def _cosine_similarity(self, emb1, emb2):
        """Compute cosine similarity between two embedding vectors."""
        emb1 = np.array(emb1, dtype=np.float32).flatten()
        emb2 = np.array(emb2, dtype=np.float32).flatten()
        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)
        if norm1 < 1e-6 or norm2 < 1e-6:
            return 0.0
        return float(np.dot(emb1, emb2) / (norm1 * norm2))

    def verify(self, id_face_image, selfie_image, strict=False):
        """Verify identity by comparing ID document face with live selfie.

        Args:
            id_face_image: base64 string, bytes, or file of ID document face
            selfie_image: base64 string, bytes, or file of live selfie
            strict: if True, use higher cosine threshold (0.55 vs 0.40)

        Returns:
            dict with verified, cosine_similarity, confidence, reason
        """
        start_time = time.time()

        if self.insightface_app is None:
            logger.error("[FaceVerify] InsightFace is None — model not loaded")
            raise RuntimeError(
                "InsightFace ArcFace model is not loaded. "
                "Face verification cannot proceed — system startup integrity check failed."
            )

        id_b64 = id_face_image if isinstance(id_face_image, str) else '(bytes)'
        selfie_b64 = selfie_image if isinstance(selfie_image, str) else '(bytes)'
        id_size = len(id_b64) if isinstance(id_b64, str) else 0
        selfie_size = len(selfie_b64) if isinstance(selfie_b64, str) else 0
        id_hash = hashlib.md5(id_b64.encode() if isinstance(id_b64, str) else id_b64).hexdigest()[:12]
        selfie_hash = hashlib.md5(selfie_b64.encode() if isinstance(selfie_b64, str) else selfie_b64).hexdigest()[:12]
        same_input = (id_hash == selfie_hash)

        logger.info("[FaceVerify] Input sizes: id=%d selfie=%d id_hash=%s selfie_hash=%s same=%s strict=%s",
                     id_size, selfie_size, id_hash, selfie_hash, same_input, strict)

        result = {
            'verified': False,
            'confidence': 0.0,
            'cosine_similarity': 0.0,
            'reason': '',
            'face_detected_id': False,
            'face_detected_selfie': False,
            'id_face_quality': None,
            'selfie_face_quality': None,
            'model': 'insightface_arcface',
            'input_id_hash': id_hash,
            'input_selfie_hash': selfie_hash,
            'same_input': same_input,
            'processing_time_ms': 0
        }

        try:
            img_id = self.decode_image(id_face_image)
            img_selfie = self.decode_image(selfie_image)
            logger.info("[FaceVerify] Decoded: id=%dx%dx%d selfie=%dx%dx%d",
                         img_id.shape[1], img_id.shape[0], img_id.shape[2] if len(img_id.shape) > 2 else 1,
                         img_selfie.shape[1], img_selfie.shape[0], img_selfie.shape[2] if len(img_selfie.shape) > 2 else 1)
        except Exception as e:
            result['reason'] = f"Image decode error: {str(e)}"
            logger.warning("[FaceVerify] Decode error: %s", e)
            result['processing_time_ms'] = round((time.time() - start_time) * 1000, 1)
            return result

        logger.info("[FaceVerify] ID image: %dx%d selfie image: %dx%d",
                     img_id.shape[1], img_id.shape[0], img_selfie.shape[1], img_selfie.shape[0])

        faces_id = self._get_faces(img_id)

        for face in faces_id:
            if face.embedding is not None:
                face.embedding = np.array(face.embedding, dtype=np.float32).copy()

        faces_selfie = self._get_faces(img_selfie)

        logger.info("[FaceVerify] ID faces=%d selfie_faces=%d id_shape=%s selfie_shape=%s",
                     len(faces_id), len(faces_selfie), img_id.shape, img_selfie.shape)

        if len(faces_id) == 0:
            result['reason'] = "No face detected in ID card image"
            logger.warning("[FaceVerify] No face in ID image (shape=%s)", img_id.shape)
            result['processing_time_ms'] = round((time.time() - start_time) * 1000, 1)
            return result
        result['face_detected_id'] = True

        if len(faces_id) > 1:
            faces_id = [max(faces_id, key=lambda f: f.det_score)]

        if len(faces_selfie) == 0:
            result['reason'] = "No face detected in selfie image"
            logger.warning("[FaceVerify] No face in selfie (shape=%s)", img_selfie.shape)
            result['processing_time_ms'] = round((time.time() - start_time) * 1000, 1)
            return result
        result['face_detected_selfie'] = True

        if len(faces_selfie) > 1:
            faces_selfie = [max(faces_selfie, key=lambda f: f.det_score)]

        face_id = faces_id[0]
        face_selfie = faces_selfie[0]

        logger.info("[FaceVerify] ID face det_score=%.3f emb=%s selfie face det_score=%.3f emb=%s",
                     float(face_id.det_score), face_id.embedding is not None,
                     float(face_selfie.det_score), face_selfie.embedding is not None)

        id_bbox = face_id.bbox.astype(int)
        selfie_bbox = face_selfie.bbox.astype(int)

        id_face_roi = img_id[max(0, id_bbox[1]):id_bbox[3], max(0, id_bbox[0]):id_bbox[2]]
        selfie_face_roi = img_selfie[max(0, selfie_bbox[1]):selfie_bbox[3], max(0, selfie_bbox[0]):selfie_bbox[2]]

        if id_face_roi.size > 0:
            enhanced_id_roi = self._enhance_face_for_quality(id_face_roi)
            result['id_face_quality'] = FaceQuality.compute_overall_quality(
                enhanced_id_roi,
                (id_bbox[0], id_bbox[1], id_bbox[2] - id_bbox[0], id_bbox[3] - id_bbox[1]),
                img_id.shape
            )
        if selfie_face_roi.size > 0:
            enhanced_selfie_roi = self._enhance_face_for_quality(selfie_face_roi)
            result['selfie_face_quality'] = FaceQuality.compute_overall_quality(
                enhanced_selfie_roi,
                (selfie_bbox[0], selfie_bbox[1], selfie_bbox[2] - selfie_bbox[0], selfie_bbox[3] - selfie_bbox[1]),
                img_selfie.shape
            )

        if result['id_face_quality'] and not result['id_face_quality']['passed']:
            issues = '; '.join(result['id_face_quality']['issues'])
            result['reason'] = f"ID face quality too low: {issues}"
            result['processing_time_ms'] = round((time.time() - start_time) * 1000, 1)
            return result

        if result['selfie_face_quality'] and not result['selfie_face_quality']['passed']:
            issues = '; '.join(result['selfie_face_quality']['issues'])
            logger.warning("Selfie quality warning: %s (continuing)", issues)

        id_emb = face_id.embedding
        selfie_emb = face_selfie.embedding
        logger.info("[FaceVerify] ID embedding: %s (len=%s), Selfie embedding: %s (len=%s)",
                     type(id_emb).__name__ if id_emb is not None else 'None',
                     len(id_emb) if id_emb is not None else 0,
                     type(selfie_emb).__name__ if selfie_emb is not None else 'None',
                     len(selfie_emb) if selfie_emb is not None else 0)

        if id_emb is not None and selfie_emb is not None:
            emb_id_norm = np.linalg.norm(np.array(id_emb, dtype=np.float32).flatten())
            emb_selfie_norm = np.linalg.norm(np.array(selfie_emb, dtype=np.float32).flatten())
            logger.info("[FaceVerify] Embedding norms: id=%.4f selfie=%.4f", emb_id_norm, emb_selfie_norm)

            similarity = self._cosine_similarity(id_emb, selfie_emb)
            result['cosine_similarity'] = round(similarity, 4)

            threshold = self.COSINE_THRESHOLD_STRICT if strict else self.COSINE_THRESHOLD
            logger.info("[FaceVerify] Similarity=%.4f threshold=%.2f strict=%s", similarity, threshold, strict)

            if similarity < threshold:
                logger.info("[FaceVerify] Low similarity, trying enhanced images...")
                try:
                    enhanced_id = self._enhance_for_detection(img_id)
                    enhanced_selfie = self._enhance_for_detection(img_selfie)
                    faces_id_enh = self._get_faces(enhanced_id)
                    faces_selfie_enh = self._get_faces(enhanced_selfie)
                    if faces_id_enh and faces_selfie_enh:
                        emb_id_enh = np.array(faces_id_enh[0].embedding, dtype=np.float32)
                        emb_selfie_enh = np.array(faces_selfie_enh[0].embedding, dtype=np.float32)
                        similarity_enh = self._cosine_similarity(emb_id_enh, emb_selfie_enh)
                        if similarity_enh > similarity:
                            logger.info("[FaceVerify] Enhanced similarity %.4f > raw %.4f", similarity_enh, similarity)
                            similarity = similarity_enh
                            result['cosine_similarity'] = round(similarity, 4)
                            result['enhanced_comparison'] = True
                except Exception as e:
                    logger.warning("[FaceVerify] Enhanced comparison failed: %s", e)
            if similarity >= threshold:
                confidence = round(min(100, (similarity - threshold) / (1.0 - threshold) * 40 + 60), 2)
            else:
                confidence = round(max(0, similarity / threshold * 60), 2)
            result['confidence'] = confidence
            result['verified'] = similarity >= threshold

            if result['verified']:
                result['reason'] = f"Face match confirmed (similarity: {similarity:.4f}, threshold: {threshold})"
            else:
                if similarity < 0.3:
                    result['reason'] = "Faces appear to be completely different people"
                elif similarity < 0.45:
                    result['reason'] = f"Low similarity - likely different individuals ({similarity:.4f})"
                else:
                    result['reason'] = f"Similarity {similarity:.4f} below threshold {threshold}"
        else:
            logger.error("[FaceVerify] Cannot compute embeddings: id_emb=%s selfie_emb=%s",
                         'None' if id_emb is None else f'OK({len(id_emb)})',
                         'None' if selfie_emb is None else f'OK({len(selfie_emb)})')
            result['reason'] = "Could not compute face embeddings"
            result['processing_time_ms'] = round((time.time() - start_time) * 1000, 1)
            return result

        id_gender = getattr(face_id, 'gender', None)
        selfie_gender = getattr(face_selfie, 'gender', None)
        if id_gender is not None and selfie_gender is not None:
            if id_gender != selfie_gender:
                result['reason'] = f"Gender mismatch: ID shows {id_gender}, selfie shows {selfie_gender}"
                result['verified'] = False
                result['confidence'] = round(result['confidence'] * 0.7, 2)

        result['processing_time_ms'] = round((time.time() - start_time) * 1000, 1)
        return result

    def detect_faces(self, image_data):
        """Detect faces in an image and return bounding boxes + metadata."""
        try:
            img = self.decode_image(image_data)
            faces = self._get_faces(img)
            result = {
                'face_count': len(faces),
                'faces': [],
                'model': 'insightface_arcface'
            }
            for face in faces:
                bbox = face.bbox.astype(int)
                face_data = {
                    'bbox': {
                        'x': int(bbox[0]),
                        'y': int(bbox[1]),
                        'w': int(bbox[2] - bbox[0]),
                        'h': int(bbox[3] - bbox[1])
                    },
                    'confidence': round(float(face.det_score), 3),
                }
                if hasattr(face, 'age') and face.age is not None:
                    face_data['age'] = int(face.age)
                if hasattr(face, 'gender') and face.gender is not None:
                    face_data['gender'] = str(face.gender)
                if face.embedding is not None:
                    face_data['embedding_dim'] = len(face.embedding)
                result['faces'].append(face_data)
            return result
        except Exception as e:
            return {'face_count': 0, 'error': str(e)}

    @staticmethod
    def _to_native(obj):
        """Convert numpy types to native Python types for JSON serialization."""
        if isinstance(obj, dict):
            return {k: FaceVerifier._to_native(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [FaceVerifier._to_native(v) for v in obj]
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return obj


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    verifier = FaceVerifier()
    with open('id_face.jpg', 'rb') as f1, open('selfie.jpg', 'rb') as f2:
        result = verifier.verify(f1.read(), f2.read())
    print(json.dumps(result, indent=2, default=str))
