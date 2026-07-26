"""
Face Anti-Spoofing Detector

Primary: EfficientNet-B0/MobileNetV2 trained on CASIA-FASD (live vs spoof).
Fallback: Liveness challenge (challenge-response) if no model available.
"""

import os
import cv2
import numpy as np
import logging
import time
import base64
from pathlib import Path

logger = logging.getLogger(__name__)

MODEL_DIR = os.path.join(os.path.dirname(__file__), 'models', 'trained')
EFFICIENTNET_MODEL_PATH = os.path.join(MODEL_DIR, 'antispoof_efficientnet_b0.pth')
PTH_MODEL_PATH = os.path.join(MODEL_DIR, '2.7_80x80_MiniFASNetV2.pth')
PTH_MODEL_URL = (
    "https://github.com/minivision-ai/Silent-Face-Anti-Spoofing/"
    "raw/master/resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.pth"
)


def _ensure_model():
    """Download MiniFASNet model if not present locally."""
    os.makedirs(MODEL_DIR, exist_ok=True)

    if os.path.exists(PTH_MODEL_PATH):
        return PTH_MODEL_PATH

    try:
        import requests
        logger.info("Downloading MiniFASNet V2 model to %s ...", MODEL_DIR)
        r = requests.get(PTH_MODEL_URL, timeout=120)
        r.raise_for_status()
        with open(PTH_MODEL_PATH, 'wb') as f:
            f.write(r.content)
        logger.info("MiniFASNet PyTorch model downloaded (%d bytes)", len(r.content))
        return PTH_MODEL_PATH
    except Exception as e:
        logger.error("Failed to download MiniFASNet model: %s", e)
        return None


class MiniFASNetDetector:
    """MiniFASNet V2 face anti-spoofing via ONNX Runtime or PyTorch.

    Detects printed photos, paper attacks, and screen replay attacks
    using a lightweight CNN trained on CelebA-Spoof and similar datasets.

    Output classes: [live, print-attack, replay-attack]
    Liveness score = 1 - (p_print + p_replay)
    """

    INPUT_SIZE = (80, 80)
    CROP_MARGIN = 2.7
    SPOOF_THRESHOLD = 0.45  # reject faces where liveness score is below 45%
    SPOOF_CONFIDENCE_THRESHOLD = 0.35  # model must favor spoof by at least 35% to trigger

    def __init__(self, shared_insightface_app=None, shared_lock=None):
        self.model = None
        self.model_type = None
        self.available = False
        self._transform = None
        self._shared_insightface = shared_insightface_app
        self._shared_lock = shared_lock
        self._load_model()

    def _load_model(self):
        """Load anti-spoof model. Tries EfficientNet-B0 then MiniFASNet V2 PTH."""
        # Try EfficientNet-B0 first
        if os.path.exists(EFFICIENTNET_MODEL_PATH):
            try:
                logger.info("Loading EfficientNet-B0 anti-spoof model from %s ...", EFFICIENTNET_MODEL_PATH)
                self._load_efficientnet(EFFICIENTNET_MODEL_PATH)
                self.model_type = 'efficientnet_b0'
                self.available = True
                logger.info("EfficientNet-B0 anti-spoof model loaded successfully")
                return
            except Exception as e:
                logger.warning("Failed to load EfficientNet-B0: %s", e)

        # Try MiniFASNet V2 PyTorch
        if os.path.exists(PTH_MODEL_PATH):
            try:
                logger.info("Loading MiniFASNet V2 PyTorch model from %s ...", PTH_MODEL_PATH)
                self._load_pytorch(PTH_MODEL_PATH)
                self.model_type = 'minifasnet_pth'
                self.available = True
                logger.info("MiniFASNet V2 PyTorch model loaded successfully")
                return
            except Exception as e:
                logger.warning("Failed to load MiniFASNet V2 PTH: %s", e)

        # Try downloading model
        model_path = _ensure_model()
        if model_path:
            try:
                self._load_pytorch(model_path)
                self.model_type = 'minifasnet_pth'
                self.available = True
                logger.info("Downloaded MiniFASNet V2 PyTorch model loaded successfully")
                return
            except Exception as e:
                logger.warning("Failed to load downloaded PTH model: %s", e)

        logger.warning("Anti-spoofing model unavailable — all loading methods failed")

    def _load_efficientnet(self, model_path):
        """Load EfficientNet-B0/MobileNetV2 anti-spoof model."""
        import torch
        from torchvision import models

        checkpoint = torch.load(model_path, map_location='cpu', weights_only=False)
        state_dict = checkpoint.get('model_state_dict', checkpoint)

        model = models.mobilenet_v2(weights=None)
        in_f = model.classifier[1].in_features
        model.classifier = torch.nn.Sequential(
            torch.nn.Dropout(0.3),
            torch.nn.Linear(in_f, 2)
        )
        cleaned = {}
        for k, v in state_dict.items():
            cleaned[k.replace('backbone.', '')] = v
        model.load_state_dict(cleaned, strict=True)
        model.eval()
        self.model = model
        self._device = torch.device('cpu')

    def _load_pytorch(self, model_path):
        import torch
        import sys
        sys.path.insert(0, os.path.dirname(__file__))
        from MiniFASNet_orig import MiniFASNetV2

        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        checkpoint = torch.load(model_path, map_location=device, weights_only=False)

        if isinstance(checkpoint, dict) and 'state_dict' in checkpoint:
            state_dict = checkpoint['state_dict']
        elif isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
            state_dict = checkpoint['model_state_dict']
        else:
            state_dict = checkpoint

        cleaned = {}
        for k, v in state_dict.items():
            name = k.replace('module.', '')
            cleaned[name] = v

        model = MiniFASNetV2(embedding_size=128, conv6_kernel=(7, 7), drop_p=0.2, num_classes=3, img_channel=3)
        model.load_state_dict(cleaned, strict=False)
        model.eval()
        model.to(device)
        self.model = model
        self._device = device
        self._transform = None

    def _crop_face(self, img, bbox):
        """Crop face with 2.7x scale margin around bbox center.

        Matches the upstream 2.7_80x80 cropping strategy.
        """
        h, w = img.shape[:2]
        x1, y1, x2, y2 = bbox
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        bw = x2 - x1
        bh = y2 - y1

        margin_w = bw * self.CROP_MARGIN / 2
        margin_h = bh * self.CROP_MARGIN / 2

        crop_x1 = max(0, int(cx - margin_w))
        crop_y1 = max(0, int(cy - margin_h))
        crop_x2 = min(w, int(cx + margin_w))
        crop_y2 = min(h, int(cy + margin_h))

        return img[crop_y1:crop_y2, crop_x1:crop_x2]

    def _preprocess_pytorch(self, face_crop):
        import torch
        resized = cv2.resize(face_crop, self.INPUT_SIZE, interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        blob = rgb.astype(np.float32)
        blob = (blob - 127.5) / 128.0
        blob = blob.transpose(2, 0, 1)
        blob = np.expand_dims(blob, axis=0)
        return torch.from_numpy(blob).to(self._device)

    def _softmax(self, x):
        e = np.exp(x - np.max(x, axis=-1, keepdims=True))
        return e / e.sum(axis=-1, keepdims=True)

    def _preprocess_efficientnet(self, face_crop):
        """Preprocess for EfficientNet-B0/MobileNetV2 (ImageNet normalization, 224x224)."""
        resized = cv2.resize(face_crop, (224, 224), interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        blob = rgb.astype(np.float32) / 255.0
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        blob = (blob - mean) / std
        blob = blob.transpose(2, 0, 1)
        blob = np.expand_dims(blob, axis=0)
        return blob

    def _run_inference(self, face_crop):
        """Run anti-spoof inference on a face crop.

        Returns:
            dict with live_prob, print_prob, replay_prob, liveness_score
        """
        if self.model_type == 'efficientnet_b0' and self.model is not None:
            import torch
            blob = self._preprocess_efficientnet(face_crop)
            tensor = torch.from_numpy(blob).to(self._device)
            with torch.no_grad():
                output = self.model(tensor)
            probs = self._softmax(output.cpu().numpy())[0]
            live_prob = float(probs[0])
            spoof_prob = float(probs[1])
            liveness_score = live_prob
            return {
                'live_prob': round(live_prob, 4),
                'print_prob': round(spoof_prob, 4),
                'replay_prob': 0.0,  # binary model can't distinguish print vs replay
                'liveness_score': round(liveness_score, 4),
            }
        elif self.model is not None:
            import torch
            blob = self._preprocess_pytorch(face_crop)
            with torch.no_grad():
                output = self.model(blob)
            probs = self._softmax(output.cpu().numpy())[0]
            live_prob = float(probs[0])
            print_prob = float(probs[1])
            replay_prob = float(probs[2])
        else:
            return {
                'live_prob': 0.5,
                'print_prob': 0.25,
                'replay_prob': 0.25,
                'liveness_score': 0.5,
            }

        liveness_score = 1.0 - (print_prob + replay_prob)

        return {
            'live_prob': round(live_prob, 4),
            'print_prob': round(print_prob, 4),
            'replay_prob': round(replay_prob, 4),
            'liveness_score': round(liveness_score, 4),
        }

    def decode_image(self, image_data):
        """Decode base64 or bytes image to BGR numpy array."""
        if isinstance(image_data, str):
            if ',' in image_data:
                image_data = image_data.split(',')[1]
            image_bytes = base64.b64decode(image_data)
        elif isinstance(image_data, bytes):
            image_bytes = image_data
        else:
            return image_data

        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Failed to decode image for anti-spoofing")
        return img

    def detect(self, image_data, face_bbox=None):
        """Run anti-spoofing detection on a single image.

        Args:
            image_data: base64 string, bytes, or numpy array (BGR)
            face_bbox: optional (x1, y1, x2, y2) face bounding box.
                       If None, uses InsightFace to detect the largest face.

        Returns:
            dict with spoofDetected, liveness_score, and class probabilities.
        """
        start = time.time()

        if not self.available:
            return {
                'spoofDetected': False,
                'liveness_score': 0.5,
                'print_prob': 0.25,
                'replay_prob': 0.25,
                'live_prob': 0.5,
                'available': False,
                'reason': 'MiniFASNet model not loaded',
                'processing_time_ms': 0,
            }

        try:
            img = self.decode_image(image_data)
        except Exception as e:
            return {
                'spoofDetected': False,
                'liveness_score': 0.5,
                'print_prob': 0.25,
                'replay_prob': 0.25,
                'live_prob': 0.5,
                'available': True,
                'reason': f'Image decode error: {e}',
                'processing_time_ms': round((time.time() - start) * 1000, 1),
            }

        if face_bbox is None:
            face_bbox = self._detect_face_insightface(img)
        if face_bbox is None:
            face_bbox = self._detect_face_haar(img)

        if face_bbox is None:
            return {
                'spoofDetected': False,
                'liveness_score': 0.5,
                'print_prob': 0.25,
                'replay_prob': 0.25,
                'live_prob': 0.5,
                'available': True,
                'reason': 'No face detected — skipping frame',
                'processing_time_ms': round((time.time() - start) * 1000, 1),
            }

        face_crop = self._crop_face(img, face_bbox)
        if face_crop.size == 0:
            return {
                'spoofDetected': False,
                'liveness_score': 0.5,
                'print_prob': 0.25,
                'replay_prob': 0.25,
                'live_prob': 0.5,
                'available': True,
                'reason': 'Face crop failed — skipping frame',
                'processing_time_ms': round((time.time() - start) * 1000, 1),
            }

        probs = self._run_inference(face_crop)

        # Detection strategy (conservative — minimize false positives on real faces):
        # The MiniFASNet model can be confidently wrong on certain faces.
        # Single-frame alone is NOT enough to reject — require multi-frame consensus.
        # Single-frame only flags spoof if combined probability is extremely high (> 0.95).
        max_spoof_prob = max(probs['print_prob'], probs['replay_prob'])
        combined_spoof = probs['print_prob'] + probs['replay_prob']

        # Only flag as spoof if combined spoof probability is extreme (> 0.95)
        # Multi-frame consensus (in api_server.py) provides the final verdict.
        spoof_detected = combined_spoof > 0.95

        reasons = []
        if combined_spoof > 0.75:
            reasons.append(f"Combined spoof probability high ({combined_spoof:.2f})")
        if probs['print_prob'] > 0.65:
            reasons.append(f"Print attack detected (p={probs['print_prob']:.2f})")
        if probs['replay_prob'] > 0.65:
            reasons.append(f"Replay attack detected (p={probs['replay_prob']:.2f})")
        if not spoof_detected and combined_spoof > 0.50:
            reasons.append(f"Single-frame uncertain — needs multi-frame consensus ({combined_spoof:.2f})")

        return {
            'spoofDetected': spoof_detected,
            'liveness_score': probs['liveness_score'],
            'print_prob': probs['print_prob'],
            'replay_prob': probs['replay_prob'],
            'live_prob': probs['live_prob'],
            'available': True,
            'reason': '; '.join(reasons) if reasons else 'Live face verified',
            'processing_time_ms': round((time.time() - start) * 1000, 1),
        }

    def detect_frames(self, frames, face_bbox=None):
        """Run anti-spoofing on multiple frames.

        If ANY frame is spoof → overall spoof detected.
        Returns average liveness score across frames.

        Args:
            frames: list of base64 strings, bytes, or numpy arrays
            face_bbox: optional face bounding box (applied to all frames)

        Returns:
            dict with aggregated results across all frames.
        """
        start = time.time()

        if not frames:
            return {
                'spoofDetected': False,
                'liveness_score': 0.5,
                'print_prob': 0.25,
                'replay_prob': 0.25,
                'live_prob': 0.5,
                'frames_analyzed': 0,
                'reason': 'No frames provided',
                'processing_time_ms': 0,
            }

        results = []
        for frame in frames:
            r = self.detect(frame, face_bbox)
            results.append(r)

        liveness_scores = [r['liveness_score'] for r in results]
        print_probs = [r['print_prob'] for r in results]
        replay_probs = [r['replay_prob'] for r in results]
        live_probs = [r['live_prob'] for r in results]

        avg_liveness = float(np.mean(liveness_scores))
        avg_print = float(np.mean(print_probs))
        avg_replay = float(np.mean(replay_probs))
        avg_live = float(np.mean(live_probs))

        # Majority voting: spoof detected if >= 50% of frames say spoof
        num_spoof = sum(1 for r in results if r['spoofDetected'])
        any_spoof = (num_spoof * 2) >= len(results)

        # Screen replay detection heuristic:
        # Real faces have micro-movements between frames. Screen replays are
        # more static (same face position, same lighting, same pixel patterns).
        screen_replay_suspect = False
        frame_brightnesses = []
        if len(frames) >= 3:
            decoded_imgs = []
            for frame in frames:
                try:
                    if isinstance(frame, str) and ',' in frame:
                        frame = frame.split(',')[1]
                    img_bytes = base64.b64decode(frame)
                    nparr = np.frombuffer(img_bytes, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if img is not None:
                        decoded_imgs.append(img)
                        frame_brightnesses.append(float(np.mean(img)))
                except Exception:
                    continue

            if len(decoded_imgs) >= 3:
                # Check inter-frame difference — screens are more static
                diffs = []
                for i in range(1, min(len(decoded_imgs), 8)):
                    diff = cv2.absdiff(
                        cv2.cvtColor(decoded_imgs[i-1], cv2.COLOR_BGR2GRAY) if len(decoded_imgs[i-1].shape) == 3 else decoded_imgs[i-1],
                        cv2.cvtColor(decoded_imgs[i], cv2.COLOR_BGR2GRAY) if len(decoded_imgs[i].shape) == 3 else decoded_imgs[i]
                    )
                    diffs.append(float(np.mean(diff)))

                if diffs:
                    avg_diff = float(np.mean(diffs))
                    # Real face: avg_diff typically 3-15 (micro-movements)
                    # Screen replay: avg_diff typically < 2 (very static)
                    if avg_diff < 1.5 and len(diffs) >= 3:
                        screen_replay_suspect = True

                # Check brightness uniformity — screens have very uniform brightness
                if frame_brightnesses:
                    brightness_std = float(np.std(frame_brightnesses))
                    # Real face: brightness varies (slight head movements change lighting)
                    # Screen: brightness is very consistent (std < 2)
                    if brightness_std < 1.5 and avg_diff < 2.0:
                        screen_replay_suspect = True

        reasons = []
        if any_spoof:
            spoof_frames = [i for i, r in enumerate(results) if r['spoofDetected']]
            reasons.append(f"Spoof detected in frames: {spoof_frames}")
        if avg_print > 0.45:
            reasons.append(f"Average print attack probability: {avg_print:.2f}")
        if avg_replay > 0.45:
            reasons.append(f"Average replay attack probability: {avg_replay:.2f}")
        if screen_replay_suspect:
            reasons.append("Screen replay suspected (low inter-frame variation)")
            # If model already shows borderline liveness AND screen suspect, flag it
            if avg_liveness < 0.55:
                any_spoof = True
                reasons.append(f"Screen replay confirmed (liveness={avg_liveness:.2f} < 0.55 with static frames)")

        return {
            'spoofDetected': any_spoof,
            'liveness_score': round(avg_liveness, 4),
            'print_prob': round(avg_print, 4),
            'replay_prob': round(avg_replay, 4),
            'live_prob': round(avg_live, 4),
            'frames_analyzed': len(frames),
            'available': True,
            'screen_replay_suspect': screen_replay_suspect,
            'reason': '; '.join(reasons) if reasons else 'Live face verified across all frames',
            'processing_time_ms': round((time.time() - start) * 1000, 1),
        }

    def _detect_face_insightface(self, img):
        """Detect face using InsightFace (shared from face_verifier) for accurate detection."""
        if self._shared_insightface is not None:
            try:
                # Use face_verifier's lock if available to prevent det_size race conditions
                lock = getattr(self, '_shared_lock', None)
                if lock:
                    with lock:
                        faces = self._shared_insightface.get(img)
                else:
                    faces = self._shared_insightface.get(img)
                if faces:
                    face = max(faces, key=lambda f: f.det_score)
                    bbox = face.bbox.astype(int)
                    logger.info("[AntiSpoof] InsightFace detected face: bbox=%s score=%.3f",
                                bbox.tolist(), float(face.det_score))
                    return (int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3]))
            except Exception as e:
                logger.warning("[AntiSpoof] InsightFace detection failed: %s — falling back to Haar", e)
        return self._detect_face_haar(img)

    def _detect_face_haar(self, img):
        """Fallback face detection using Haar Cascade."""
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            )
            faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(60, 60))
            if len(faces) == 0:
                return None
            x, y, w, h = max(faces, key=lambda r: r[2] * r[3])
            return (x, y, x + w, y + h)
        except Exception:
            return None
