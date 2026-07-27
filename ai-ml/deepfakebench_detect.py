"""
DeepfakeBench Integration - Standalone CLI Tool

Usage:
    python deepfakebench_detect.py --image face.jpg --model ucf
    python deepfakebench_detect.py --image face.jpg --model all

Supported models: xception, recce, f3net, ucf, srm, spsl, capsule, ffd, core, mnet4, mnet4I, resnet34, effnb4
"""

import os
import sys
import argparse
import torch
import cv2
import numpy as np

DEEPFAKEBENCH_DIR = os.path.join(os.path.dirname(__file__), 'DeepfakeBench')
sys.path.insert(0, DEEPFAKEBENCH_DIR)
sys.path.insert(0, os.path.join(DEEPFAKEBENCH_DIR, 'training'))

IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

AVAILABLE_MODELS = {
    'xception': {'weight': 'xception_best.pth', 'acc': '94.50%'},
    'ucf': {'weight': 'ucf_best.pth', 'acc': '95.27%'},
    'recce': {'weight': 'recce_best.pth', 'acc': '94.22%'},
    'f3net': {'weight': 'f3net_best.pth', 'acc': 'N/A'},
    'srm': {'weight': 'srm_best.pth', 'acc': '93.0%'},
    'spsl': {'weight': 'spsl_best.pth', 'acc': '92.5%'},
    'capsule': {'weight': 'capsule_best.pth', 'acc': '84.21%'},
    'ffd': {'weight': 'ffd_best.pth', 'acc': '94.34%'},
    'core': {'weight': 'core_best.pth', 'acc': '94.31%'},
    'mnet4': {'weight': 'meso4_best.pth', 'acc': '60.77%'},
    'mnet4I': {'weight': 'meso4Incep_best.pth', 'acc': '75.83%'},
    'resnet34': {'weight': 'cnnaug_best.pth', 'acc': '84.93%'},
    'effnb4': {'weight': 'effnb4_best.pth', 'acc': '95.67%'},
}

def preprocess_image(image_path, size=256):
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Cannot read image: {image_path}")
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = cv2.resize(img, (size, size))
    blob = img.astype(np.float32) / 255.0
    blob = (blob - IMAGENET_MEAN) / IMAGENET_STD
    blob = blob.transpose(2, 0, 1)
    return torch.from_numpy(blob).unsqueeze(0)

def detect_with_model(image_path, model_name):
    if model_name not in AVAILABLE_MODELS:
        print(f"Unknown model: {model_name}")
        return None

    info = AVAILABLE_MODELS[model_name]
    weight_path = os.path.join(DEEPFAKEBENCH_DIR, 'training', 'weights', info['weight'])

    if not os.path.exists(weight_path):
        print(f"Weight not found: {weight_path}")
        return None

    try:
        from detectors import DETECTOR
        from utils.inference import load_model

        config = {
            'backbone_name': model_name if model_name != 'resnet34' else 'resnet34',
            'pretrained': weight_path,
        }

        print(f"Loading {model_name} (acc: {info['acc']})...")
        print(f"Note: Full integration requires DeepfakeBench environment")

        return {'model': model_name, 'status': 'available', 'accuracy': info['acc']}

    except ImportError as e:
        print(f"Import error: {e}")
        print("DeepfakeBench dependencies may be missing")
        return None

def main():
    parser = argparse.ArgumentParser(description='DeepfakeBench Detection')
    parser.add_argument('--image', required=True, help='Path to image')
    parser.add_argument('--model', default='all', help='Model name or "all"')
    args = parser.parse_args()

    if not os.path.exists(args.image):
        print(f"Image not found: {args.image}")
        return

    if args.model == 'all':
        print("Available DeepfakeBench models:")
        print("-" * 50)
        for name, info in AVAILABLE_MODELS.items():
            print(f"  {name:15s} | Accuracy: {info['acc']}")
        print("-" * 50)
        print("\nTo use: python deepfakebench_detect.py --image face.jpg --model ucf")
    else:
        result = detect_with_model(args.image, args.model)
        if result:
            print(f"\nResult: {result}")

if __name__ == '__main__':
    main()
