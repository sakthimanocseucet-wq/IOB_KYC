"""
Comprehensive AI/ML Model Test Tool
Tests all verification models: Deepfake, Anti-Spoof, Face, Liveness, OCR

Usage:
  python test_all_models.py                    -- Test model loading only
  python test_all_models.py --live <image>     -- Test with real image
  python test_all_models.py --full <img1> <img2> -- Full pipeline test
  python test_all_models.py --api              -- Test via deployed API
"""

import sys
import os
import json
import time
import base64
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'ai-ml'))

DIVIDER = "=" * 60


def img_to_b64(path):
    with open(path, 'rb') as f:
        data = f.read()
    ext = os.path.splitext(path)[1].lower().lstrip('.')
    mime = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png'}.get(ext, 'image/jpeg')
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def test_model_loading():
    """Test 1: Verify all models load correctly."""
    print(f"\n{DIVIDER}")
    print("TEST 1: MODEL LOADING")
    print(DIVIDER)

    results = {}

    # Deepfake
    try:
        from deepfake_detector import DeepfakeDetector
        t0 = time.time()
        d = DeepfakeDetector()
        elapsed = round((time.time() - t0) * 1000)
        results['deepfake'] = {
            'status': 'OK' if d.available else 'DISABLED',
            'loaded': d.models_loaded,
            'disabled': d.models_disabled,
            'load_time_ms': elapsed,
        }
        print(f"[Deepfake]     {'OK' if d.available else 'DISABLED'} | loaded={d.models_loaded} | {elapsed}ms")
    except Exception as e:
        results['deepfake'] = {'status': 'ERROR', 'error': str(e)}
        print(f"[Deepfake]     ERROR: {e}")

    # Anti-spoof
    try:
        from minifasnet_detector import MiniFASNetDetector
        t0 = time.time()
        s = MiniFASNetDetector()
        elapsed = round((time.time() - t0) * 1000)
        ok = getattr(s, 'available', s.model is not None)
        threshold = getattr(s, 'SPOOF_THRESHOLD', 'N/A')
        results['anti_spoof'] = {
            'status': 'OK' if ok else 'DISABLED',
            'threshold': threshold,
            'load_time_ms': elapsed,
        }
        print(f"[Anti-Spoof]   {'OK' if ok else 'DISABLED'} | threshold={threshold} | {elapsed}ms")
    except Exception as e:
        results['anti_spoof'] = {'status': 'ERROR', 'error': str(e)}
        print(f"[Anti-Spoof]   ERROR: {e}")

    # Face verification
    try:
        from face_verification import FaceVerifier
        t0 = time.time()
        f = FaceVerifier()
        elapsed = round((time.time() - t0) * 1000)
        ok = getattr(f, 'available', f.insightface_app is not None)
        results['face_verify'] = {
            'status': 'OK' if ok else 'DISABLED',
            'load_time_ms': elapsed,
        }
        print(f"[Face Verify]  {'OK' if ok else 'DISABLED'} | {elapsed}ms")
    except Exception as e:
        results['face_verify'] = {'status': 'ERROR', 'error': str(e)}
        print(f"[Face Verify]  ERROR: {e}")

    # Liveness
    try:
        from liveness_detection import ChallengeLivenessDetector
        t0 = time.time()
        l = ChallengeLivenessDetector()
        elapsed = round((time.time() - t0) * 1000)
        ok = getattr(l, 'available', l.face_landmarker is not None)
        results['liveness'] = {
            'status': 'OK' if ok else 'DISABLED',
            'load_time_ms': elapsed,
        }
        print(f"[Liveness]     {'OK' if ok else 'DISABLED'} | {elapsed}ms")
    except Exception as e:
        results['liveness'] = {'status': 'ERROR', 'error': str(e)}
        print(f"[Liveness]     ERROR: {e}")

    # OCR
    try:
        from ocr_extraction import get_ocr
        t0 = time.time()
        engine = get_ocr()
        elapsed = round((time.time() - t0) * 1000)
        results['ocr'] = {'status': 'OK', 'load_time_ms': elapsed}
        print(f"[OCR]          OK | {elapsed}ms")
    except Exception as e:
        results['ocr'] = {'status': 'ERROR', 'error': str(e)}
        print(f"[OCR]          ERROR: {e}")

    # QR
    try:
        from qr_verification import detect_qr_code
        results['qr'] = {'status': 'OK'}
        print(f"[QR Code]      OK")
    except Exception as e:
        results['qr'] = {'status': 'ERROR', 'error': str(e)}
        print(f"[QR Code]      ERROR: {e}")

    loaded = sum(1 for v in results.values() if v['status'] == 'OK')
    total = len(results)
    print(f"\nResult: {loaded}/{total} models active")

    return results


def test_deepfake(image_path):
    """Test 2: Deepfake detection on a single image."""
    print(f"\n{DIVIDER}")
    print("TEST 2: DEEPFAKE DETECTION")
    print(DIVIDER)
    print(f"Image: {image_path}")

    from deepfake_detector import DeepfakeDetector
    detector = DeepfakeDetector()

    if not getattr(detector, 'available', detector.models_loaded is False):
        print("SKIP: Deepfake models not loaded")
        return None

    img_b64 = img_to_b64(image_path)
    result = detector.detect(img_b64)

    verdict = "DEEPFAKE DETECTED" if result['is_deepfake'] else "REAL FACE"
    print(f"\nVerdict:    {verdict}")
    print(f"Fake prob:  {result['fake_prob']:.4f}")
    print(f"Real prob:  {result['real_prob']:.4f}")
    print(f"Confidence: {result['confidence']:.4f}")
    print(f"Models:     {result['models_used']}")
    print(f"Time:       {result['processing_time_ms']}ms")

    for name, info in result.get('per_model', {}).items():
        print(f"  [{name}] fake={info['fake_prob']:.4f} real={info['real_prob']:.4f}")

    return result


def test_anti_spoof(image_path):
    """Test 3: Anti-spoofing on a single image."""
    print(f"\n{DIVIDER}")
    print("TEST 3: ANTI-SPOOFING")
    print(DIVIDER)
    print(f"Image: {image_path}")

    from minifasnet_detector import MiniFASNetDetector
    detector = MiniFASNetDetector()

    if not getattr(detector, 'available', detector.model is None):
        print("SKIP: Anti-spoof model not loaded")
        return None

    img_b64 = img_to_b64(image_path)
    result = detector.detect(img_b64)

    verdict = "SPOOF DETECTED" if result['is_spoof'] else "REAL PERSON"
    print(f"\nVerdict:    {verdict}")
    print(f"Real score: {result['real_score']:.4f}")
    print(f"Fake score: {result['fake_score']:.4f}")
    print(f"Confidence: {result['confidence']:.4f}")
    print(f"Time:       {result['processing_time_ms']}ms")

    return result


def test_face_verify(id_path, selfie_path):
    """Test 4: Face verification between two images."""
    print(f"\n{DIVIDER}")
    print("TEST 4: FACE VERIFICATION")
    print(DIVIDER)
    print(f"ID photo:   {id_path}")
    print(f"Selfie:     {selfie_path}")

    from face_verification import FaceVerifier
    verifier = FaceVerifier()

    if not getattr(verifier, 'available', verifier.insightface_app is None):
        print("SKIP: Face verifier not loaded")
        return None

    id_b64 = img_to_b64(id_path)
    selfie_b64 = img_to_b64(selfie_path)
    result = verifier.verify(id_b64, selfie_b64)

    verdict = "MATCH" if result['verified'] else "NO MATCH"
    print(f"\nVerdict:    {verdict}")
    print(f"Similarity: {result.get('similarity', 'N/A')}")
    print(f"Threshold:  {result.get('threshold', 'N/A')}")
    print(f"Time:       {result.get('processing_time_ms', 0)}ms")

    return result


def test_api_health():
    """Test 5: API health endpoint."""
    print(f"\n{DIVIDER}")
    print("TEST 5: API HEALTH CHECK")
    print(DIVIDER)

    import urllib.request
    url = "https://iobkyc-production.up.railway.app/api/ai/healthz"
    try:
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        print(f"Status: OK")
        print(f"Models: {json.dumps(data.get('models', {}), indent=2)}")
        return data
    except Exception as e:
        print(f"Status: ERROR - {e}")
        return None


def run_all_tests(image1=None, image2=None, api_only=False):
    """Run full test suite."""
    print(f"\n{'#' * 60}")
    print("#  IOB KYC AI/ML MODEL TEST SUITE")
    print(f"{'#' * 60}")

    start = time.time()

    if api_only:
        test_api_health()
    else:
        test_model_loading()
        if image1:
            test_deepfake(image1)
            test_anti_spoof(image1)
        if image1 and image2:
            test_face_verify(image1, image2)

    elapsed = round(time.time() - start, 1)
    print(f"\n{'#' * 60}")
    print(f"#  All tests completed in {elapsed}s")
    print(f"{'#' * 60}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='IOB KYC AI/ML Test Suite')
    parser.add_argument('--live', metavar='IMAGE', help='Test deepfake + anti-spoof on image')
    parser.add_argument('--full', nargs=2, metavar=('ID', 'SELFIE'), help='Full pipeline test')
    parser.add_argument('--api', action='store_true', help='Test deployed API only')
    args = parser.parse_args()

    if args.api:
        run_all_tests(api_only=True)
    elif args.full:
        run_all_tests(image1=args.full[0], image2=args.full[1])
    elif args.live:
        run_all_tests(image1=args.live)
    else:
        run_all_tests()
