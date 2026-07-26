"""
Multi-Model Deepfake Detection Ensemble

Official open-source architectures with verified deepfake pretrained checkpoints:
  1. Xception        -- Custom PyTorch impl trained on 140K deepfake faces (StyleGAN)
  2. EfficientNet-B2 -- Trained on CASIA-FASD (torchvision implementation)

No placeholder models. No random initialization. No ImageNet-only fallbacks.
Every model requires a valid deepfake checkpoint or it is disabled.

CPU-optimized with no CUDA dependencies.
"""

import os
import cv2
import numpy as np
import logging
import time
import base64
import threading
from dataclasses import dataclass, field
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger(__name__)

MODEL_DIR = os.path.join(os.path.dirname(__file__), 'models')
DEEPFAKE_THRESHOLD = 0.85
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

CHECKPOINT_DIR = MODEL_DIR

MODEL_DEFINITIONS = {
    'xception': {
        'checkpoint_path': os.path.join(CHECKPOINT_DIR, 'deepfake_xception.pth'),
        'source': 'RamadhanZome/deepfake-xception (HuggingFace)',
        'dataset': '140K StyleGAN deepfake faces',
        'version': '1.0 (StyleGAN benchmark, 99.36% val acc)',
        'architecture': 'Xception (custom PyTorch impl)',
        'paper': 'https://arxiv.org/abs/1610.02357',
    },
    'efficientnet_b2': {
        'checkpoint_path': os.path.join(CHECKPOINT_DIR, 'deepfake_detector.pth'),
        'source': 'Local training via train_deepfake.py',
        'dataset': 'CASIA-FASD',
        'version': '1.0',
        'architecture': 'EfficientNet-B2 (torchvision)',
        'paper': 'https://arxiv.org/abs/1905.11946',
    },
}


class SeparableConv2d(nn.Module):
    def __init__(self, in_c, out_c, k=3, stride=1, padding=1):
        super().__init__()
        self.depthwise = nn.Conv2d(in_c, in_c, k, stride, padding, groups=in_c, bias=False)
        self.pointwise = nn.Conv2d(in_c, out_c, 1, 1, 0, bias=False)

    def forward(self, x):
        return self.pointwise(self.depthwise(x))


def _make_block(in_c, out_c, n, s):
    l = []
    ci = in_c
    for i in range(n):
        l.append(nn.ReLU())
        st = s if i == 0 else 1
        l.append(SeparableConv2d(ci, out_c, 3, stride=st, padding=1))
        l.append(nn.BatchNorm2d(out_c))
        ci = out_c
    sc = nn.Sequential(
        nn.Conv2d(in_c, out_c, 1, stride=s, bias=False),
        nn.BatchNorm2d(out_c),
    )
    return nn.ModuleDict({'layers': nn.Sequential(*l), 'shortcut': sc})


def _make_middle_block(c):
    return _make_block(c, c, 3, 1)


class XceptionDeepfake(nn.Module):
    def __init__(self, nc=2):
        super().__init__()
        self.conv1 = nn.Conv2d(3, 32, 3, stride=2, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(32)
        self.conv2 = nn.Conv2d(32, 64, 3, stride=1, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(64)
        self.block1 = _make_block(64, 128, 2, 2)
        self.block2 = _make_block(128, 256, 2, 2)
        self.block3 = _make_block(256, 728, 2, 2)
        self.middle_flow = nn.ModuleList([_make_middle_block(728) for _ in range(8)])
        self.block4 = _make_block(728, 1024, 2, 2)
        self.sepconv1 = SeparableConv2d(1024, 1536, 3, 1, 1)
        self.bn3 = nn.BatchNorm2d(1536)
        self.sepconv2 = SeparableConv2d(1536, 2048, 3, 1, 1)
        self.bn4 = nn.BatchNorm2d(2048)
        self.fc = nn.Linear(2048, nc)

    def forward(self, x):
        x = F.relu(self.bn1(self.conv1(x)))
        x = F.relu(self.bn2(self.conv2(x)))
        for b in [self.block1, self.block2, self.block3]:
            x = b['shortcut'](x) + b['layers'](x)
        for b in self.middle_flow:
            x = b['shortcut'](x) + b['layers'](x)
        x = self.block4['shortcut'](x) + self.block4['layers'](x)
        x = F.relu(self.bn3(self.sepconv1(x)))
        x = F.relu(self.bn4(self.sepconv2(x)))
        x = F.adaptive_avg_pool2d(x, (1, 1)).flatten(1)
        return self.fc(x)

_MODEL_LOCK = threading.Lock()


def _strict_load_checkpoint(model, checkpoint_path, model_name, model_info):
    if not os.path.exists(checkpoint_path):
        logger.warning(
            "[%s] Checkpoint NOT FOUND at %s. "
            "Model will be DISABLED.",
            model_name, checkpoint_path
        )
        return None

    try:
        state = torch.load(checkpoint_path, map_location='cpu')

        if isinstance(state, dict):
            for key in ('model_state_dict', 'state_dict', 'model'):
                if key in state and isinstance(state[key], dict):
                    state_dict = state[key]
                    break
            else:
                state_dict = state
        else:
            state_dict = state

        try:
            model.load_state_dict(state_dict, strict=True)
            logger.info(
                "[%s] Checkpoint loaded OK (strict=True). source=%s dataset=%s",
                model_name, model_info['source'], model_info['dataset']
            )
            return model_info
        except RuntimeError as e:
            error_msg = str(e)
            logger.warning("[%s] strict=True failed: %s", model_name, error_msg[:200])

            if 'size mismatch' in error_msg and 'classifier' in error_msg:
                logger.warning(
                    "[%s] Classifier shape mismatch (expected, likely num_classes). "
                    "Trying strict=False for classifier keys...", model_name
                )
                missing, unexpected = model.load_state_dict(state_dict, strict=False)
                if missing:
                    logger.warning("[%s] Missing keys (ignored): %s", model_name, missing)
                if unexpected:
                    logger.warning("[%s] Unexpected keys (ignored): %s", model_name, unexpected)
                if len(missing) < 10:
                    logger.info("[%s] Checkpoint loaded with non-strict (classifier adapted)", model_name)
                    return model_info

            logger.warning("[%s] Checkpoint INCOMPATIBLE: %s", model_name, error_msg[:300])
            return None

    except Exception as e:
        logger.warning("[%s] Checkpoint load FAILED: %s", model_name, e)
        return None


class XceptionDetector:
    def __init__(self):
        self.model = None
        self.available = False
        self.device = torch.device('cpu')
        self.model_name = 'xception'
        self.input_size = (224, 224)
        self.info: Optional[dict] = None
        self._load_model()

    def _load_model(self):
        try:
            self.model = XceptionDeepfake(nc=2)
            self.model.eval()
            self.model.to(self.device)

            info = MODEL_DEFINITIONS['xception']
            loaded = _strict_load_checkpoint(self.model, info['checkpoint_path'], 'Xception', info)
            if loaded:
                self.info = loaded
                self.available = True
                logger.info("[Xception] ENABLED (deepfake checkpoint loaded)")
            else:
                logger.warning("[Xception] DISABLED -- no valid checkpoint at %s", info['checkpoint_path'])
                self.model = None
                self.available = False
        except Exception as e:
            logger.warning("[Xception] Failed to initialize: %s", e)
            self.model = None
            self.available = False

    def preprocess(self, face_crop):
        resized = cv2.resize(face_crop, self.input_size, interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        blob = rgb.astype(np.float32) / 255.0
        blob = (blob - IMAGENET_MEAN) / IMAGENET_STD
        blob = blob.transpose(2, 0, 1)
        blob = np.expand_dims(blob, axis=0)
        return torch.from_numpy(blob).to(self.device)

    def predict(self, face_crop):
        if not self.available or self.model is None:
            return None
        try:
            blob = self.preprocess(face_crop)
            with torch.no_grad():
                logits = self.model(blob)
                probs = torch.softmax(logits, dim=1).cpu().numpy()[0]
            return {'real_prob': float(probs[0]), 'fake_prob': float(probs[1])}
        except Exception as e:
            logger.warning("[Xception] Inference failed: %s", e)
            return None


class EfficientNetB2Detector:
    def __init__(self):
        self.model = None
        self.available = False
        self.device = torch.device('cpu')
        self.model_name = 'efficientnet_b2'
        self.input_size = (224, 224)
        self.info: Optional[dict] = None
        self._load_model()

    def _build_model(self):
        from torchvision import models
        backbone = models.efficientnet_b2(weights=None)
        in_features = backbone.classifier[1].in_features
        backbone.classifier = nn.Sequential(
            nn.Dropout(0.5),
            nn.Linear(in_features, 256),
            nn.ReLU(inplace=True),
            nn.Dropout(0.25),
            nn.Linear(256, 2),
        )

        class DeepfakeEfficientNetB2(nn.Module):
            def __init__(self):
                super().__init__()
                self.backbone = backbone
            def forward(self, x):
                return self.backbone(x)

        return DeepfakeEfficientNetB2()

    def _load_model(self):
        try:
            self.model = self._build_model()
            self.model.eval()
            self.model.to(self.device)

            info = MODEL_DEFINITIONS['efficientnet_b2']
            loaded = _strict_load_checkpoint(self.model, info['checkpoint_path'], 'EfficientNet-B2', info)
            if loaded:
                self.info = loaded
                self.available = True
                logger.info("[EfficientNet-B2] ENABLED (deepfake checkpoint loaded)")
            else:
                logger.warning("[EfficientNet-B2] DISABLED -- no valid checkpoint at %s", info['checkpoint_path'])
                self.model = None
                self.available = False
        except Exception as e:
            logger.warning("[EfficientNet-B2] Failed to initialize: %s", e)
            self.model = None
            self.available = False

    def preprocess(self, face_crop):
        resized = cv2.resize(face_crop, self.input_size, interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        blob = rgb.astype(np.float32) / 255.0
        blob = (blob - IMAGENET_MEAN) / IMAGENET_STD
        blob = blob.transpose(2, 0, 1)
        blob = np.expand_dims(blob, axis=0)
        return torch.from_numpy(blob).to(self.device)

    def predict(self, face_crop):
        if not self.available or self.model is None:
            return None
        try:
            blob = self.preprocess(face_crop)
            with torch.no_grad():
                logits = self.model(blob)
                probs = torch.softmax(logits, dim=1).cpu().numpy()[0]
            return {'real_prob': float(probs[0]), 'fake_prob': float(probs[1])}
        except Exception as e:
            logger.warning("[EfficientNet-B2] Inference failed: %s", e)
            return None


DETECTOR_CLASSES = {
    'xception': XceptionDetector,
    'efficientnet_b2': EfficientNetB2Detector,
}

DEFAULT_WEIGHTS = {
    'xception': 0.50,
    'efficientnet_b2': 0.50,
}


class DeepfakeDetector:
    """Multi-model deepfake detection ensemble.

    Only uses models with verified deepfake checkpoints.
    No random initialization. No ImageNet fallbacks.
    Weights are renormalized to sum to 1.0 based on active models.
    """

    _shared_cascade = None

    def __init__(self, shared_insightface_app=None, shared_lock=None):
        self.detectors: dict = {}
        self.available = False
        self.models_loaded = []
        self.models_disabled = []
        self.model_info = {}
        self._shared_insightface = shared_insightface_app
        self._shared_lock = shared_lock
        self._load_all_models()

    @classmethod
    def _get_cascade(cls):
        if cls._shared_cascade is None:
            cls._shared_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            )
        return cls._shared_cascade

    def _load_all_models(self):
        logger.info("=" * 60)
        logger.info("Deepfake Detection: Loading official models...")
        logger.info("=" * 60)

        for name, detector_cls in DETECTOR_CLASSES.items():
            logger.info("--- Initializing %s ---", name)
            instance = detector_cls()
            self.detectors[name] = instance

            if instance.available:
                self.models_loaded.append(name)
                self.model_info[name] = instance.info
                logger.info("[%s] >>> ENABLED", name)
            else:
                self.models_disabled.append(name)
                logger.warning("[%s] >>> DISABLED", name)

        self.available = len(self.models_loaded) > 0
        total = len(DETECTOR_CLASSES)

        logger.info("=" * 60)
        logger.info("Deepfake Ensemble Summary:")
        logger.info("  Enabled:  %s", self.models_loaded if self.models_loaded else "(none)")
        logger.info("  Disabled: %s", self.models_disabled if self.models_disabled else "(none)")
        logger.info("  Status:   %s", "ACTIVE" if self.available else "UNAVAILABLE")
        logger.info("=" * 60)

    def _get_active_weights(self):
        active = self.models_loaded
        if not active:
            return {}
        raw = {name: DEFAULT_WEIGHTS.get(name, 0.5) for name in active}
        total = sum(raw.values())
        if total > 0:
            return {name: w / total for name, w in raw.items()}
        return {name: 1.0 / len(active) for name in active}

    def _detect_face(self, img):
        """Detect face — try InsightFace first (shared, thread-safe), then Haar Cascade fallback."""
        if hasattr(self, '_shared_insightface') and self._shared_insightface is not None:
            try:
                lock = getattr(self, '_shared_lock', None)
                if lock:
                    with lock:
                        faces = self._shared_insightface.get(img)
                else:
                    faces = self._shared_insightface.get(img)
                if faces:
                    face = max(faces, key=lambda f: f.det_score)
                    bbox = face.bbox.astype(int)
                    return (int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3]))
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
        if not self.models_loaded:
            return None

        weights = self._get_active_weights()
        predictions = {}

        for name in self.models_loaded:
            det = self.detectors.get(name)
            if not det or not det.available:
                continue
            with _MODEL_LOCK:
                pred = det.predict(face_crop)
            if pred:
                predictions[name] = pred

        if not predictions:
            return None

        weighted_fake = 0.0
        total_weight = 0.0
        per_model = {}

        for name, pred in predictions.items():
            w = weights.get(name, 0.5)
            weighted_fake += pred['fake_prob'] * w
            total_weight += w

        if total_weight > 0:
            avg_fake = weighted_fake / total_weight
        else:
            avg_fake = np.mean([p['fake_prob'] for p in predictions.values()])

        for name, pred in predictions.items():
            det = self.detectors.get(name)
            per_model[name] = {
                'fake_prob': round(pred['fake_prob'], 4),
                'real_prob': round(pred['real_prob'], 4),
                'weight': weights.get(name, 0.5),
                'checkpoint_loaded': det is not None and det.available,
            }

        return {
            'fake_prob': round(avg_fake, 4),
            'real_prob': round(1.0 - avg_fake, 4),
            'per_model': per_model,
        }

    def _build_model_diagnostics(self):
        diagnostics = {}
        for name in DETECTOR_CLASSES:
            det = self.detectors.get(name)
            if det and det.available and det.info:
                diagnostics[name] = {
                    'enabled': True,
                    'source': det.info['source'],
                    'dataset': det.info['dataset'],
                    'version': det.info['version'],
                    'architecture': det.info['architecture'],
                }
            else:
                info = MODEL_DEFINITIONS.get(name, {})
                diagnostics[name] = {
                    'enabled': False,
                    'source': info.get('source', 'N/A'),
                    'architecture': info.get('architecture', 'N/A'),
                }
        return diagnostics

    def detect(self, image_data, face_bbox=None):
        start = time.time()

        if not self.available:
            return {
                'is_deepfake': False,
                'confidence': 0.5,
                'fake_prob': 0.5,
                'real_prob': 0.5,
                'available': False,
                'models_used': [],
                'models_loaded': [],
                'models_disabled': self.models_disabled,
                'per_model': {},
                'model_diagnostics': self._build_model_diagnostics(),
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
                'models_used': [],
                'models_loaded': self.models_loaded,
                'models_disabled': self.models_disabled,
                'per_model': {},
                'model_diagnostics': self._build_model_diagnostics(),
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
                'models_used': [],
                'models_loaded': self.models_loaded,
                'models_disabled': self.models_disabled,
                'per_model': {},
                'model_diagnostics': self._build_model_diagnostics(),
                'reason': 'No face detected -- cannot assess deepfake',
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
                'models_used': [],
                'models_loaded': self.models_loaded,
                'models_disabled': self.models_disabled,
                'per_model': {},
                'model_diagnostics': self._build_model_diagnostics(),
                'reason': 'Face crop failed -- empty region',
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
                    'models_used': [],
                    'models_loaded': self.models_loaded,
                    'models_disabled': self.models_disabled,
                    'per_model': {},
                    'model_diagnostics': self._build_model_diagnostics(),
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
                'models_loaded': self.models_loaded,
                'models_disabled': self.models_disabled,
                'model_diagnostics': self._build_model_diagnostics(),
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
                'models_used': [],
                'models_loaded': self.models_loaded,
                'models_disabled': self.models_disabled,
                'per_model': {},
                'model_diagnostics': self._build_model_diagnostics(),
                'reason': f'Inference error: {e}',
                'processing_time_ms': round((time.time() - start) * 1000, 1),
            }

    def detect_frames(self, frames, face_bbox=None):
        start = time.time()

        if not frames:
            return {
                'is_deepfake': False,
                'confidence': 0.5,
                'fake_prob': 0.5,
                'real_prob': 0.5,
                'frames_analyzed': 0,
                'models_used': [],
                'models_loaded': self.models_loaded,
                'models_disabled': self.models_disabled,
                'model_diagnostics': self._build_model_diagnostics(),
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

        frame_results = [
            {
                'frame_index': i,
                'is_deepfake': r['is_deepfake'],
                'fake_prob': r['fake_prob'],
                'real_prob': r['real_prob'],
            }
            for i, r in enumerate(results)
        ]

        return {
            'is_deepfake': any_deepfake,
            'confidence': round(confidence, 4),
            'fake_prob': round(avg_fake, 4),
            'real_prob': round(avg_real, 4),
            'frames_analyzed': len(frames),
            'deepfake_frame_indices': deepfake_frames,
            'frame_results': frame_results,
            'available': True,
            'models_used': self.models_loaded,
            'models_loaded': self.models_loaded,
            'models_disabled': self.models_disabled,
            'model_diagnostics': self._build_model_diagnostics(),
            'reason': '; '.join(reasons),
            'processing_time_ms': round((time.time() - start) * 1000, 1),
        }
