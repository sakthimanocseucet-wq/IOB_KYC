# Bank KYC Face Verification System

Production-ready face verification pipeline for digital KYC using real-world datasets.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    API Server (Flask)                     │
│                   http://localhost:5001                    │
├──────────────┬──────────────┬──────────────┬─────────────┤
│  /health     │ /face-detect │ /liveness/   │ /detailed-  │
│              │              │ challenge    │ verify      │
└──────┬───────┴──────┬───────┴──────┬───────┴──────┬──────┘
       │              │              │              │
       ▼              ▼              ▼              ▼
┌──────────────┬──────────────┬──────────────┬─────────────┐
│ InsightFace  │ InsightFace  │ MediaPipe    │ Full Gate   │
│ ArcFace      │ Detection    │ FaceLand-    │ Pipeline    │
│ (512-dim)    │              │ marker       │             │
└──────────────┴──────────────┴──────────────┴─────────────┘
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    │                     │                     │
                    ▼                     ▼                     ▼
            ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
            │ MiniFASNet V2│    │ EfficientNet │    │ Challenge    │
            │ (Anti-Spoof) │    │ B2 (Deepfake)│    │ Liveness     │
            └──────────────┘    └──────────────┘    └──────────────┘
```

## Verification Flow

1. **Face Detection** → InsightFace ArcFace detects faces
2. **Face Verification** → ArcFace embeddings + cosine similarity
3. **Liveness** → MediaPipe challenge-response (blink, turn, smile)
4. **Anti-Spoofing** → MiniFASNet V2 (printed photo, screen replay)
5. **Deepfake** → EfficientNet-B2 (AI-generated faces)

### Gate Decision (No Score Averaging)

```
verified = faceMatchPassed AND livenessPassed AND NOT spoofDetected AND NOT deepfakeDetected
```

If ANY gate fails → REJECTED.

## File Structure

```
ai-ml/
├── api_server.py              # Flask API (4 endpoints)
├── face_verification.py       # InsightFace ArcFace face matching
├── liveness_detection.py      # MediaPipe challenge-response
├── minifasnet_detector.py     # MiniFASNet V2 anti-spoofing
├── deepfake_detector.py       # EfficientNet-B2 deepfake detection
├── train_deepfake.py          # Training script for deepfake model
├── requirements.txt           # Python dependencies
├── models/
│   ├── deepfake_detector.pth  # Trained deepfake model (after training)
│   ├── face_landmarker.task   # MediaPipe face landmarker
│   └── trained/
│       ├── minifasnet_v2.onnx # MiniFASNet V2 (pre-trained)
│       └── antispoof_model_*.pth
└── data/                      # Training datasets
    ├── faceforensics++/       # FaceForensics++ dataset
    ├── replay-attack/         # Replay-Attack dataset
    └── oulu-npu/              # OULU-NPU dataset
```

## Installation

### 1. Create Virtual Environment

```bash
cd ai-ml
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Verify Installation

```bash
python -c "import insightface; import mediapipe; import torch; import onnxruntime; print('All OK')"
```

## API Endpoints

### GET /health

```bash
curl http://localhost:5001/health
```

Response:
```json
{
  "status": "healthy",
  "modules": {
    "face_verification": {"available": true, "model": "InsightFace ArcFace (buffalo_l)"},
    "liveness": {"available": true, "model": "MediaPipe FaceLandmarker"},
    "anti_spoofing": {"available": true, "model": "MiniFASNet V2"},
    "deepfake": {"available": false, "model": "EfficientNet-B2"}
  }
}
```

### POST /face-detect

```bash
curl -X POST http://localhost:5001/face-detect \
  -H "Content-Type: application/json" \
  -d '{"image": "<base64-encoded-image>"}'
```

### POST /liveness/challenge

```bash
curl -X POST http://localhost:5001/liveness/challenge \
  -H "Content-Type: application/json" \
  -d '{}'
```

Response:
```json
{
  "success": true,
  "data": {
    "challenge_type": "blink",
    "challenge_sequence": ["blink", "smile"],
    "prompt": "Please blink your eyes 4 times",
    "token": "abc123...",
    "expires_at": "2026-06-14T08:49:35"
  }
}
```

### POST /detailed-verify

```bash
curl -X POST http://localhost:5001/detailed-verify \
  -H "Content-Type: application/json" \
  -d '{
    "id_face": "<base64>",
    "selfie": "<base64>",
    "challenge": {...},
    "frames": ["<base64>", ...]
  }'
```

Response:
```json
{
  "success": true,
  "data": {
    "verified": false,
    "faceMatchPassed": true,
    "livenessPassed": false,
    "spoofDetected": false,
    "deepfakeDetected": false,
    "verdict": "REJECTED",
    "reasons": ["Liveness challenge failed"],
    "confidence": {
      "face_similarity": 0.78,
      "liveness": 0.3,
      "spoof": 0.85,
      "deepfake": 0.5
    }
  }
}
```

## Training Deepfake Detector

### Download Datasets

**FaceForensics++** (primary):
```bash
# Download from https://github.com/ondyari/FaceForensics
# Extract to data/faceforensics++/
```

**Replay-Attack** (anti-spoofing):
```bash
# Download from https://www.idiap.ch/en/dataset/replay-attack
# Extract to data/replay-attack/
```

**OULU-NPU** (anti-spoofing):
```bash
# Download from https://sites.google.com/site/oulufaceanti-spoofingdatabase
# Extract to data/oulu-npu/
```

### Quick Test (Subset)

```bash
python train_deepfake.py --data-root ../data --subset 1000 --epochs 10 --batch-size 8
```

### Full Training

```bash
python train_deepfake.py --data-root ../data --epochs 20 --batch-size 16
```

### Training Output

- Model saved to: `models/deepfake_detector.pth`
- Training history: `models/deepfake_training_history.json`
- Metrics: Accuracy, Precision, Recall, F1, ROC-AUC

## Models

| Model | Type | Size | Source |
|-------|------|------|--------|
| InsightFace ArcFace | Face recognition | 275 MB | Auto-downloaded |
| MediaPipe FaceLandmarker | Liveness | 3.58 MB | Auto-downloaded |
| MiniFASNet V2 | Anti-spoofing | 1.66 MB | Auto-downloaded |
| EfficientNet-B2 | Deepfake detection | ~30 MB | After training |

## Tech Stack

- **Backend**: Spring Boot (port 8080)
- **AI/ML**: Flask (port 5001)
- **Frontend**: HTML/CSS/JS
- **Models**: PyTorch, ONNX Runtime, MediaPipe, InsightFace
