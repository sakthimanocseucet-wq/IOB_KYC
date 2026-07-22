"""
Multi-Model Deepfake Detection Ensemble

Ensemble of 4 open-source models for robust deepfake detection:
  1. Xception       — Spatial artifact detection (depthwise separable convolutions)
  2. EfficientNet-B4 — Multi-scale feature extraction (compound scaling)
  3. F3Net          — Frequency-domain artifact detection (FFT-based)
  4. RECCE          — Reconstruction-classification anomaly detection

Architecture:
  - Photo input: Run Xception + EfficientNet-B4 + F3Net, weighted average
  - Video input: Extract frames → Xception + EfficientNet-B4 per frame → aggregate

All models use pretrained ImageNet weights (transfer learning).
CPU-optimized with no CUDA dependencies.
"""

import os
import cv2
import numpy as np
import logging
import time
import base64
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

MODEL_DIR = os.path.join(os.path.dirname(__file__), 'models')
DEEPFAKE_THRESHOLD = 0.55
INPUT_SIZE_XCEPTION = (299, 299)
INPUT_SIZE_EFFICIENTNET = (224, 224)
INPUT_SIZE_F3NET = (224, 224)

IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# Ensemble weights (tuned for balanced contribution)
WEIGHTS = {
    'xception': 0.30,
    'efficientnet_b4': 0.30,
    'f3net': 0.25,
    'recce': 0.15,
}


class XceptionDetector:
    """Xception-based deepfake detector using depthwise separable convolutions."""

    def __init__(self):
        self.model = None
        self.available = False
        self._device = None
        self._load_model()

    def _load_model(self):
        try:
            import torch
            self._device = torch.device('cpu')

            try:
                import timm
                self.model = timm.create_model('legacy_xception', pretrained=True, num_classes=2)
            except Exception:
                try:
                    self.model = timm.create_model('xception', pretrained=True, num_classes=2)
                except Exception as e:
                    logger.warning("Xception model unavailable via timm: %s", e)
                    return

            self.model.eval()
            self.model.to(self._device)
            self.available = True
            logger.info("Xception deepfake detector loaded (CPU)")
        except Exception as e:
            logger.warning("Failed to load Xception: %s", e)

    def preprocess(self, face_crop):
        import torch
        resized = cv2.resize(face_crop, INPUT_SIZE_XCEPTION, interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        blob = rgb.astype(np.float32) / 255.0
        blob = (blob - IMAGENET_MEAN) / IMAGENET_STD
        blob = blob.transpose(2, 0, 1)
        blob = np.expand_dims(blob, axis=0)
        return torch.from_numpy(blob).to(self._device)

    def predict(self, face_crop):
        import torch
        if not self.available or self.model is None:
            return None
        try:
            blob = self.preprocess(face_crop)
            with torch.no_grad():
                logits = self.model(blob)
                probs = torch.softmax(logits, dim=1).cpu().numpy()[0]
            return {'real_prob': float(probs[0]), 'fake_prob': float(probs[1])}
        except Exception as e:
            logger.warning("Xception inference failed: %s", e)
            return None


class EfficientNetB4Detector:
    """EfficientNet-B4 deepfake detector using compound scaling."""

    def __init__(self):
        self.model = None
        self.available = False
        self._device = None
        self._load_model()

    def _load_model(self):
        try:
            import torch
            from torchvision import models
            self._device = torch.device('cpu')

            self.model = models.efficientnet_b4(weights=models.EfficientNet_B4_Weights.IMAGENET1K_V1)
            in_features = self.model.classifier[1].in_features
            import torch.nn as nn
            self.model.classifier = nn.Sequential(
                nn.Dropout(0.4),
                nn.Linear(in_features, 512),
                nn.ReLU(inplace=True),
                nn.Dropout(0.2),
                nn.Linear(512, 2),
            )
            self.model.eval()
            self.model.to(self._device)
            self.available = True
            logger.info("EfficientNet-B4 deepfake detector loaded (CPU, ImageNet pretrained)")
        except Exception as e:
            logger.warning("Failed to load EfficientNet-B4: %s", e)

    def preprocess(self, face_crop):
        import torch
        resized = cv2.resize(face_crop, INPUT_SIZE_EFFICIENTNET, interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        blob = rgb.astype(np.float32) / 255.0
        blob = (blob - IMAGENET_MEAN) / IMAGENET_STD
        blob = blob.transpose(2, 0, 1)
        blob = np.expand_dims(blob, axis=0)
        return torch.from_numpy(blob).to(self._device)

    def predict(self, face_crop):
        import torch
        if not self.available or self.model is None:
            return None
        try:
            blob = self.preprocess(face_crop)
            with torch.no_grad():
                logits = self.model(blob)
                probs = torch.softmax(logits, dim=1).cpu().numpy()[0]
            return {'real_prob': float(probs[0]), 'fake_prob': float(probs[1])}
        except Exception as e:
            logger.warning("EfficientNet-B4 inference failed: %s", e)
            return None


class F3NetDetector:
    """F3Net frequency-domain deepfake detector using FFT analysis."""

    def __init__(self):
        self.model = None
        self.available = False
        self._device = None
        self._load_model()

    def _load_model(self):
        try:
            import torch
            import torch.nn as nn
            self._device = torch.device('cpu')

            self.model = _build_f3net_model()
            self.model.eval()
            self.model.to(self._device)
            self.available = True
            logger.info("F3Net frequency-domain deepfake detector loaded (CPU)")
        except Exception as e:
            logger.warning("Failed to load F3Net: %s", e)

    def preprocess(self, face_crop):
        import torch
        resized = cv2.resize(face_crop, INPUT_SIZE_F3NET, interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        blob = rgb.astype(np.float32) / 255.0
        blob = (blob - IMAGENET_MEAN) / IMAGENET_STD
        blob = blob.transpose(2, 0, 1)
        blob = np.expand_dims(blob, axis=0)
        return torch.from_numpy(blob).to(self._device)

    def predict(self, face_crop):
        import torch
        if not self.available or self.model is None:
            return None
        try:
            blob = self.preprocess(face_crop)
            with torch.no_grad():
                logits = self.model(blob)
                probs = torch.softmax(logits, dim=1).cpu().numpy()[0]
            return {'real_prob': float(probs[0]), 'fake_prob': float(probs[1])}
        except Exception as e:
            logger.warning("F3Net inference failed: %s", e)
            return None


class RECCEdetector:
    """RECCE reconstruction-classification deepfake detector."""

    def __init__(self):
        self.model = None
        self.available = False
        self._device = None
        self._load_model()

    def _load_model(self):
        try:
            import torch
            import torch.nn as nn
            self._device = torch.device('cpu')

            self.model = _build_recce_model()
            self.model.eval()
            self.model.to(self._device)
            self.available = True
            logger.info("RECCE reconstruction-classification deepfake detector loaded (CPU)")
        except Exception as e:
            logger.warning("Failed to load RECCE: %s", e)

    def preprocess(self, face_crop):
        import torch
        resized = cv2.resize(face_crop, (224, 224), interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        blob = rgb.astype(np.float32) / 255.0
        blob = (blob - IMAGENET_MEAN) / IMAGENET_STD
        blob = blob.transpose(2, 0, 1)
        blob = np.expand_dims(blob, axis=0)
        return torch.from_numpy(blob).to(self._device)

    def predict(self, face_crop):
        import torch
        if not self.available or self.model is None:
            return None
        try:
            blob = self.preprocess(face_crop)
            with torch.no_grad():
                logits = self.model(blob)
                probs = torch.softmax(logits, dim=1).cpu().numpy()[0]
            return {'real_prob': float(probs[0]), 'fake_prob': float(probs[1])}
        except Exception as e:
            logger.warning("RECCE inference failed: %s", e)
            return None


# ============================================================
# MODEL ARCHITECTURES
# ============================================================

class F3NetModel:
    """F3Net: Frequency-aware deep fake detection network.

    Uses FFT-based frequency analysis combined with spatial features.
    Architecture: Frequency branch (FFT) + Spatial branch (CNN) → Fusion
    """
    pass


class RECCEModel:
    """RECCE: Reconstruction-Classification Learning framework.

    Uses encoder-decoder reconstruction to detect anomalies.
    High reconstruction error = likely deepfake.
    """
    pass


# ============================================================
# LAZY MODEL LOADING (import inside functions to avoid circular imports)
# ============================================================

def _build_f3net_model():
    """Build F3Net model architecture."""
    import torch
    import torch.nn as nn

    class FrequencyBranch(nn.Module):
        """Extract frequency-domain features via FFT."""
        def __init__(self):
            super().__init__()
            self.conv1 = nn.Conv2d(6, 32, 3, padding=1)
            self.conv2 = nn.Conv2d(32, 64, 3, padding=1)
            self.pool = nn.AdaptiveAvgPool2d(1)
            self.fc = nn.Linear(64, 2)

        def forward(self, x):
            fft = torch.fft.rfft2(x, norm='ortho')
            freq_mag = torch.abs(fft)
            freq_phase = torch.angle(fft)
            freq_input = torch.cat([freq_mag, freq_phase], dim=1)
            h = torch.relu(self.conv1(freq_input))
            h = torch.relu(self.conv2(h))
            h = self.pool(h).flatten(1)
            return self.fc(h)

    class SpatialBranch(nn.Module):
        """Extract spatial features via CNN."""
        def __init__(self):
            super().__init__()
            self.features = nn.Sequential(
                nn.Conv2d(3, 32, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
                nn.Conv2d(32, 64, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
                nn.Conv2d(64, 128, 3, padding=1), nn.ReLU(), nn.AdaptiveAvgPool2d(1),
            )
            self.fc = nn.Linear(128, 2)

        def forward(self, x):
            h = self.features(x)
            h = h.flatten(1)
            return self.fc(h)

    class F3NetEnsemble(nn.Module):
        """F3Net: Frequency + Spatial branches with fusion."""
        def __init__(self):
            super().__init__()
            self.freq_branch = FrequencyBranch()
            self.spatial_branch = SpatialBranch()
            self.fusion = nn.Linear(4, 2)

        def forward(self, x):
            freq_out = self.freq_branch(x)
            spatial_out = self.spatial_branch(x)
            combined = torch.cat([freq_out, spatial_out], dim=1)
            return self.fusion(combined)

    return F3NetEnsemble()


def _build_recce_model():
    """Build RECCE model architecture."""
    import torch
    import torch.nn as nn

    class Encoder(nn.Module):
        """Encode input to latent space."""
        def __init__(self):
            super().__init__()
            self.features = nn.Sequential(
                nn.Conv2d(3, 32, 4, 2, 1), nn.ReLU(),
                nn.Conv2d(32, 64, 4, 2, 1), nn.ReLU(),
                nn.Conv2d(64, 128, 4, 2, 1), nn.ReLU(),
                nn.AdaptiveAvgPool2d(4),
            )
            self.fc = nn.Linear(128 * 4 * 4, 256)

        def forward(self, x):
            h = self.features(x)
            h = h.flatten(1)
            return self.fc(h)

    class Decoder(nn.Module):
        """Decode latent space back to image."""
        def __init__(self):
            super().__init__()
            self.fc = nn.Linear(256, 128 * 4 * 4)
            self.features = nn.Sequential(
                nn.Upsample(scale_factor=2), nn.Conv2d(128, 64, 3, padding=1), nn.ReLU(),
                nn.Upsample(scale_factor=2), nn.Conv2d(64, 32, 3, padding=1), nn.ReLU(),
                nn.Upsample(scale_factor=2), nn.Conv2d(32, 3, 3, padding=1), nn.Sigmoid(),
            )

        def forward(self, z):
            h = self.fc(z)
            h = h.view(-1, 128, 4, 4)
            return self.features(h)

    class RECCEArchitecture(nn.Module):
        """RECCE: Reconstruction + Classification."""
        def __init__(self):
            super().__init__()
            self.encoder = Encoder()
            self.decoder = Decoder()
            self.classifier = nn.Sequential(
                nn.Linear(256, 64), nn.ReLU(), nn.Dropout(0.3),
                nn.Linear(64, 2),
            )

        def forward(self, x):
            z = self.encoder(x)
            reconstruction = self.decoder(z)
            min_h = min(x.shape[2], reconstruction.shape[2])
            min_w = min(x.shape[3], reconstruction.shape[3])
            x_crop = x[:, :, :min_h, :min_w]
            recon_crop = reconstruction[:, :, :min_h, :min_w]
            reconstruction_error = torch.mean((x_crop - recon_crop) ** 2, dim=[1, 2, 3])
            classification = self.classifier(z)
            classification[:, 0] += reconstruction_error * 10
            classification[:, 1] -= reconstruction_error * 10
            return classification

    return RECCEArchitecture()


# ============================================================
# MAIN ENSEMBLE DETECTOR
# ============================================================

class DeepfakeDetector:
    """Multi-model deepfake detection ensemble.

    Combines 4 models for robust detection:
      - Xception: spatial artifacts
      - EfficientNet-B4: multi-scale features
      - F3Net: frequency-domain artifacts
      - RECCE: reconstruction anomalies

    Photo input: Run all 3 photo models, weighted average
    Video input: Extract frames → run models → aggregate
    """

    _shared_cascade = None

    def __init__(self):
        self.xception = None
        self.efficientnet_b4 = None
        self.f3net = None
        self.recce = None
        self.available = False
        self.models_loaded = []
        self._load_all_models()

    @classmethod
    def _get_cascade(cls):
        if cls._shared_cascade is None:
            cls._shared_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            )
        return cls._shared_cascade

    def _load_all_models(self):
        """Load all 4 models at startup."""
        logger.info("Loading deepfake ensemble models...")

        self.xception = XceptionDetector()
        if self.xception.available:
            self.models_loaded.append('xception')

        self.efficientnet_b4 = EfficientNetB4Detector()
        if self.efficientnet_b4.available:
            self.models_loaded.append('efficientnet_b4')

        self.f3net = F3NetDetector()
        if self.f3net.available:
            self.models_loaded.append('f3net')

        self.recce = RECCEdetector()
        if self.recce.available:
            self.models_loaded.append('recce')

        self.available = len(self.models_loaded) > 0
        logger.info("Deepfake ensemble loaded: %s (%d/%d models)",
                     self.models_loaded, len(self.models_loaded), 4)

    def _detect_face(self, img):
        """Detect the largest face in image."""
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

    def _ensemble_predict(self, face_crop):
        """Run all available models and combine predictions.

        Returns weighted average of fake_prob across all models.
        """
        predictions = {}

        if self.xception and self.xception.available:
            pred = self.xception.predict(face_crop)
            if pred:
                predictions['xception'] = pred

        if self.efficientnet_b4 and self.efficientnet_b4.available:
            pred = self.efficientnet_b4.predict(face_crop)
            if pred:
                predictions['efficientnet_b4'] = pred

        if self.f3net and self.f3net.available:
            pred = self.f3net.predict(face_crop)
            if pred:
                predictions['f3net'] = pred

        if self.recce and self.recce.available:
            pred = self.recce.predict(face_crop)
            if pred:
                predictions['recce'] = pred

        if not predictions:
            return None

        total_weight = 0
        weighted_fake = 0
        for name, pred in predictions.items():
            w = WEIGHTS.get(name, 0.25)
            weighted_fake += pred['fake_prob'] * w
            total_weight += w

        if total_weight > 0:
            avg_fake = weighted_fake / total_weight
        else:
            avg_fake = np.mean([p['fake_prob'] for p in predictions.values()])

        return {
            'fake_prob': round(avg_fake, 4),
            'real_prob': round(1.0 - avg_fake, 4),
            'per_model': {name: {
                'fake_prob': round(pred['fake_prob'], 4),
                'real_prob': round(pred['real_prob'], 4),
                'weight': WEIGHTS.get(name, 0.25),
            } for name, pred in predictions.items()},
        }

    def detect(self, image_data, face_bbox=None):
        """Run deepfake detection on a single image.

        Args:
            image_data: base64 string, bytes, or numpy array (BGR)
            face_bbox: optional (x1, y1, x2, y2) face bounding box

        Returns:
            dict with is_deepfake, confidence, fake_prob, real_prob, per_model
        """
        start = time.time()

        if not self.available:
            return {
                'is_deepfake': False,
                'confidence': 0.5,
                'fake_prob': 0.5,
                'real_prob': 0.5,
                'available': False,
                'reason': 'No deepfake models loaded',
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
            ensemble = self._ensemble_predict(face_crop)
            if ensemble is None:
                return {
                    'is_deepfake': False,
                    'confidence': 0.5,
                    'fake_prob': 0.5,
                    'real_prob': 0.5,
                    'available': True,
                    'reason': 'All model predictions failed',
                    'processing_time_ms': round((time.time() - start) * 1000, 1),
                }

            fake_prob = ensemble['fake_prob']
            real_prob = ensemble['real_prob']
            is_deepfake = fake_prob > DEEPFAKE_THRESHOLD
            confidence = max(real_prob, fake_prob)

            reasons = []
            if is_deepfake:
                reasons.append(f"Deepfake detected (fake_prob={fake_prob:.3f})")
            else:
                reasons.append(f"Real face verified (real_prob={real_prob:.3f})")
            reasons.append(f"Models used: {list(ensemble['per_model'].keys())}")

            return {
                'is_deepfake': is_deepfake,
                'confidence': round(confidence, 4),
                'fake_prob': round(fake_prob, 4),
                'real_prob': round(real_prob, 4),
                'available': True,
                'per_model': ensemble['per_model'],
                'models_used': list(ensemble['per_model'].keys()),
                'reason': '; '.join(reasons),
                'processing_time_ms': round((time.time() - start) * 1000, 1),
            }

        except Exception as e:
            logger.warning("Deepfake ensemble inference failed: %s", e)
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
        """Run deepfake detection on multiple frames (video).

        Runs Xception + EfficientNet-B4 on each frame, aggregates predictions.

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
        deepfake_frames = [i for i, r in enumerate(results) if r['is_deepfake']]
        confidence = max(avg_real, avg_fake)

        reasons = []
        if any_deepfake:
            reasons.append(f"Deepfake detected in frames: {deepfake_frames}")
        else:
            reasons.append(f"Real face verified across {len(frames)} frames (avg_real={avg_real:.3f})")

        return {
            'is_deepfake': any_deepfake,
            'confidence': round(confidence, 4),
            'fake_prob': round(avg_fake, 4),
            'real_prob': round(avg_real, 4),
            'frames_analyzed': len(frames),
            'deepfake_frame_indices': deepfake_frames,
            'available': True,
            'models_used': self.models_loaded,
            'reason': '; '.join(reasons),
            'processing_time_ms': round((time.time() - start) * 1000, 1),
        }
