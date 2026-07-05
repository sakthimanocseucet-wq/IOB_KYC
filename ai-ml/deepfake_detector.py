"""
EfficientNet-B2 Deepfake Detector

Fine-tuned EfficientNet-B2 for detecting AI-generated deepfake faces.
Trained on FaceForensics++ dataset.

Architecture: EfficientNet-B2 backbone + custom classification head
Input: 224x224 RGB face crop, ImageNet-normalized
Output: binary [real, fake] logits
"""

import os
import cv2
import numpy as np
import logging
import time
import base64
from pathlib import Path

logger = logging.getLogger(__name__)

MODEL_DIR = os.path.join(os.path.dirname(__file__), 'models')
BEST_MODEL_PATH = os.path.join(MODEL_DIR, 'deepfake_detector.pth')
FINAL_MODEL_PATH = os.path.join(MODEL_DIR, 'deepfake_efficientnet_b2_final.pth')

INPUT_SIZE = (224, 224)
DEEPFAKE_THRESHOLD = 0.75

IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class DeepfakeEfficientNetB2:
    """EfficientNet-B2 model architecture for deepfake detection."""

    @staticmethod
    def build(num_classes=2):
        """Build EfficientNet-B2 with custom classification head."""
        import torch
        import torch.nn as nn
        from torchvision import models

        model = models.efficientnet_b2(weights=None)
        in_features = model.classifier[1].in_features
        model.classifier = nn.Sequential(
            nn.Dropout(0.5),
            nn.Linear(in_features, 256),
            nn.ReLU(inplace=True),
            nn.Dropout(0.25),
            nn.Linear(256, num_classes),
        )
        return model


class DeepfakeDetector:
    """EfficientNet-B2 deepfake detection.

    Detects AI-generated faces (deepfakes, face swaps, GAN-generated faces)
    using a binary classifier fine-tuned on FaceForensics++ dataset.

    Output: is_deepfake (bool), confidence (0-1)
    """

    _shared_face_app = None  # Shared InsightFace instance across all detectors
    _shared_cascade = None   # Shared Haar cascade instance

    def __init__(self):
        self.model = None
        self.available = False
        self._device = None
        self._transform = None

        self._load_model()

    @classmethod
    def _get_face_app(cls):
        """Get or create shared InsightFace FaceAnalysis instance."""
        if cls._shared_face_app is None:
            try:
                from insightface.app import FaceAnalysis
                app = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'])
                app.prepare(ctx_id=0, det_size=(640, 640))
                cls._shared_face_app = app
            except Exception:
                pass
        return cls._shared_face_app

    @classmethod
    def _get_cascade(cls):
        """Get or create shared Haar cascade instance."""
        if cls._shared_cascade is None:
            cls._shared_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            )
        return cls._shared_cascade

    def _load_model(self):
        """Load trained deepfake detection model."""
        try:
            import torch
            self._device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

            model_path = None
            if os.path.exists(BEST_MODEL_PATH):
                model_path = BEST_MODEL_PATH
            elif os.path.exists(FINAL_MODEL_PATH):
                model_path = FINAL_MODEL_PATH

            if model_path is None:
                logger.warning(
                    "Deepfake model not found at %s — deepfake detection disabled",
                    BEST_MODEL_PATH,
                )
                return

            checkpoint = torch.load(model_path, map_location=self._device, weights_only=False)

            if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
                state_dict = checkpoint['model_state_dict']
                num_classes = checkpoint.get('num_classes', 2)
            else:
                state_dict = checkpoint
                num_classes = 2

            model = DeepfakeEfficientNetB2.build(num_classes=num_classes)
            model.load_state_dict(state_dict, strict=False)
            model.eval()
            model.to(self._device)

            self.model = model
            self.available = True
            logger.info("Deepfake EfficientNet-B2 loaded from %s", model_path)

        except Exception as e:
            logger.warning("Failed to load deepfake model: %s", e)

    def _preprocess(self, face_crop):
        """Preprocess face crop for EfficientNet-B2.

        Input: BGR face crop (any size)
        Output: (1, 3, 224, 224) float32 tensor, RGB, ImageNet-normalized
        """
        import torch

        resized = cv2.resize(face_crop, INPUT_SIZE, interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        blob = rgb.astype(np.float32) / 255.0
        blob = (blob - IMAGENET_MEAN) / IMAGENET_STD
        blob = blob.transpose(2, 0, 1)  # HWC → CHW
        blob = np.expand_dims(blob, axis=0)  # NCHW
        return torch.from_numpy(blob).to(self._device)

    def _detect_face(self, img):
        """Detect the largest face in image. Returns (x1,y1,x2,y2) or None."""
        face_app = self._get_face_app()
        if face_app is not None:
            try:
                faces = face_app.get(img)
                if faces:
                    best = max(faces, key=lambda f: f.bbox[2] * f.bbox[3])
                    x1, y1, x2, y2 = best.bbox.astype(int)
                    return (x1, y1, x2, y2)
            except Exception:
                pass

        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            cascade = self._get_cascade()
            faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(60, 60))
            if len(faces) == 0:
                return None
            x, y, w, h = max(faces, key=lambda r: r[2] * r[3])
            return (x, y, x + w, y + h)
        except Exception:
            return None

    def _crop_face(self, img, bbox, margin=0.2):
        """Crop face region with margin."""
        h, w = img.shape[:2]
        x1, y1, x2, y2 = bbox
        bw, bh = x2 - x1, y2 - y1
        mx, my = int(bw * margin), int(bh * margin)
        crop_x1 = max(0, x1 - mx)
        crop_y1 = max(0, y1 - my)
        crop_x2 = min(w, x2 + mx)
        crop_y2 = min(h, y2 + my)
        return img[crop_y1:crop_y2, crop_x1:crop_x2]

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
            raise ValueError("Failed to decode image for deepfake detection")
        return img

    def detect(self, image_data, face_bbox=None):
        """Run deepfake detection on a single image.

        Args:
            image_data: base64 string, bytes, or numpy array (BGR)
            face_bbox: optional (x1, y1, x2, y2) face bounding box

        Returns:
            dict with is_deepfake, confidence, fake_prob, real_prob
        """
        start = time.time()

        if not self.available:
            return {
                'is_deepfake': False,
                'confidence': 0.5,
                'fake_prob': 0.5,
                'real_prob': 0.5,
                'available': False,
                'reason': 'Deepfake model not loaded',
                'processing_time_ms': 0,
            }

        try:
            img = self.decode_image(image_data)
        except Exception as e:
            return {
                'is_deepfake': False,
                'confidence': 0.5,
                'fake_prob': 0.5,
                'real_prob': 0.5,
                'available': True,
                'reason': f'Image decode error: {e}',
                'processing_time_ms': round((time.time() - start) * 1000, 1),
            }

        if face_bbox is None:
            face_bbox = self._detect_face(img)
        if face_bbox is None:
            return {
                'is_deepfake': False,
                'confidence': 0.5,
                'fake_prob': 0.5,
                'real_prob': 0.5,
                'available': True,
                'reason': 'No face detected — cannot assess deepfake',
                'processing_time_ms': round((time.time() - start) * 1000, 1),
            }

        face_crop = self._crop_face(img, face_bbox)
        if face_crop.size == 0:
            return {
                'is_deepfake': False,
                'confidence': 0.5,
                'fake_prob': 0.5,
                'real_prob': 0.5,
                'available': True,
                'reason': 'Face crop failed — empty region',
                'processing_time_ms': round((time.time() - start) * 1000, 1),
            }

        try:
            import torch
            blob = self._preprocess(face_crop)
            with torch.no_grad():
                logits = self.model(blob)
                probs = torch.softmax(logits, dim=1).cpu().numpy()[0]

            real_prob = float(probs[0])
            fake_prob = float(probs[1])
            is_deepfake = fake_prob > DEEPFAKE_THRESHOLD
            confidence = max(real_prob, fake_prob)

            reasons = []
            if is_deepfake:
                reasons.append(f"Deepfake detected (fake_prob={fake_prob:.3f})")
            else:
                reasons.append(f"Real face verified (real_prob={real_prob:.3f})")

            return {
                'is_deepfake': is_deepfake,
                'confidence': round(confidence, 4),
                'fake_prob': round(fake_prob, 4),
                'real_prob': round(real_prob, 4),
                'available': True,
                'reason': '; '.join(reasons),
                'processing_time_ms': round((time.time() - start) * 1000, 1),
            }

        except Exception as e:
            logger.warning("Deepfake inference failed: %s", e)
            return {
                'is_deepfake': False,
                'confidence': 0.5,
                'fake_prob': 0.5,
                'real_prob': 0.5,
                'available': True,
                'reason': f'Inference error: {e}',
                'processing_time_ms': round((time.time() - start) * 1000, 1),
            }

    def detect_frames(self, frames, face_bbox=None):
        """Run deepfake detection on multiple frames.

        If ANY frame is deepfake → overall deepfake detected.

        Args:
            frames: list of base64 strings, bytes, or numpy arrays
            face_bbox: optional face bounding box (applied to all frames)

        Returns:
            dict with aggregated results across all frames.
        """
        start = time.time()

        if not frames:
            return {
                'is_deepfake': False,
                'confidence': 0.5,
                'fake_prob': 0.5,
                'real_prob': 0.5,
                'frames_analyzed': 0,
                'reason': 'No frames provided',
                'processing_time_ms': 0,
            }

        results = []
        for frame in frames:
            r = self.detect(frame, face_bbox)
            results.append(r)

        fake_probs = [r['fake_prob'] for r in results]
        real_probs = [r['real_prob'] for r in results]

        avg_fake = float(np.mean(fake_probs))
        avg_real = float(np.mean(real_probs))

        any_deepfake = any(r['is_deepfake'] for r in results)
        confidence = max(avg_real, avg_fake)

        reasons = []
        if any_deepfake:
            deepfake_frames = [i for i, r in enumerate(results) if r['is_deepfake']]
            reasons.append(f"Deepfake detected in frames: {deepfake_frames}")
        else:
            reasons.append(f"Real face verified across {len(frames)} frames (avg_real={avg_real:.3f})")

        return {
            'is_deepfake': any_deepfake,
            'confidence': round(confidence, 4),
            'fake_prob': round(avg_fake, 4),
            'real_prob': round(avg_real, 4),
            'frames_analyzed': len(frames),
            'available': True,
            'reason': '; '.join(reasons),
            'processing_time_ms': round((time.time() - start) * 1000, 1),
        }
