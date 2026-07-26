"""
Test Deepfake Detection Tool

Usage:
  python test_deepfake.py <image_path>

Tests:
  1. Deepfake detection (Xception + EfficientNet-B2 ensemble)
  2. Anti-spoofing (MiniFASNet V2)
  3. Face verification (ArcFace)
"""

import sys
import os
import json
import base64
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'ai-ml'))


def image_to_base64(path):
    with open(path, 'rb') as f:
        data = f.read()
    ext = os.path.splitext(path)[1].lower()
    mime = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png'}.get(ext.lstrip('.'), 'image/jpeg')
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def test_deepfake(image_path):
    print("=" * 60)
    print("DEEPFAKE DETECTION TEST")
    print("=" * 60)
    print(f"Image: {image_path}")
    print()

    from deepfake_detector import DeepfakeDetector
    detector = DeepfakeDetector()

    print(f"Models loaded: {detector.models_loaded}")
    print(f"Models disabled: {detector.models_disabled}")
    print()

    img_b64 = image_to_base64(image_path)
    result = detector.detect(img_b64)

    print(f"Is Deepfake:    {result['is_deepfake']}")
    print(f"Fake Probability: {result['fake_prob']:.4f}")
    print(f"Real Probability: {result['real_prob']:.4f}")
    print(f"Confidence:     {result['confidence']:.4f}")
    print(f"Available:      {result['available']}")
    print(f"Models Used:    {result['models_used']}")
    print(f"Reason:         {result['reason']}")
    print(f"Processing:     {result['processing_time_ms']}ms")
    print()
    print("Per-Model Results:")
    for model_name, model_data in result.get('per_model', {}).items():
        print(f"  {model_name}: fake={model_data['fake_prob']:.4f}, real={model_data['real_prob']:.4f}, weight={model_data['weight']:.2f}")
    print()
    return result


def test_anti_spoof(image_path):
    print("=" * 60)
    print("ANTI-SPOOFING TEST")
    print("=" * 60)

    from minifasnet_detector import MiniFASNetDetector
    detector = MiniFASNetDetector()

    print(f"Available: {detector.available}")
    print(f"Threshold: {detector.spoof_threshold}")
    print()

    img_b64 = image_to_base64(image_path)
    result = detector.detect(img_b64)

    print(f"Is Spoof:       {result['is_spoof']}")
    print(f"Real Score:     {result['real_score']:.4f}")
    print(f"Fake Score:     {result['fake_score']:.4f}")
    print(f"Confidence:     {result['confidence']:.4f}")
    print(f"Reason:         {result['reason']}")
    print(f"Processing:     {result['processing_time_ms']}ms")
    print()
    return result


def test_face_verify(id_path, selfie_path):
    print("=" * 60)
    print("FACE VERIFICATION TEST")
    print("=" * 60)

    from face_verification import FaceVerifier
    verifier = FaceVerifier()

    print(f"Available: {verifier.available}")
    print()

    id_b64 = image_to_base64(id_path)
    selfie_b64 = image_to_base64(selfie_path)
    result = verifier.verify(id_b64, selfie_b64)

    print(f"Verified:       {result['verified']}")
    print(f"Similarity:     {result.get('similarity', 'N/A')}")
    print(f"Threshold:      {result.get('threshold', 'N/A')}")
    print(f"Reason:         {result['reason']}")
    print(f"Processing:     {result.get('processing_time_ms', 0)}ms")
    print()
    return result


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python test_deepfake.py <image_path>              -- Test deepfake + anti-spoof")
        print("  python test_deepfake.py <id_photo> <selfie_photo> -- Test face verification")
        sys.exit(1)

    image1 = sys.argv[1]

    if len(sys.argv) == 3:
        image2 = sys.argv[2]
        test_face_verify(image1, image2)
    else:
        test_deepfake(image1)
        test_anti_spoof(image1)
