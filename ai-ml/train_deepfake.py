"""
Training Script for EfficientNet-B2 Deepfake Detector

Fine-tunes EfficientNet-B2 on real-world datasets for deepfake detection.
Supports FaceForensics++ (primary) and subset training for fast iteration.

Usage:
    # Quick test (subset ~1000 images):
    python train_deepfake.py --data-root ../data --subset 1000 --epochs 10

    # Full training on FaceForensics++:
    python train_deepfake.py --data-root ../data --epochs 20 --batch-size 16

    # Train on specific dataset:
    python train_deepfake.py --data-root ../data --dataset faceforensics --epochs 20

Dataset structure expected:
    data/
        faceforensics++/
            original_sequences/youtube/c23/videos/   (real)
            manipulated_sequences/
                Deepfakes/c23/videos/               (fake)
                Face2Face/c23/videos/               (fake)
                FaceSwap/c23/videos/                (fake)
"""

import os
import sys
import json
import time
import argparse
import logging
import random
import numpy as np
from pathlib import Path
from datetime import datetime
from collections import Counter

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, random_split, Dataset, Subset
import torchvision.models as models
import torchvision.transforms as transforms
import cv2

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

MODELS_DIR = os.path.join(os.path.dirname(__file__), 'models')
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
OUTPUT_MODEL_PATH = os.path.join(MODELS_DIR, 'deepfake_detector.pth')


# ============================================================
# MODEL ARCHITECTURE
# ============================================================

class DeepfakeEfficientNetB2(nn.Module):
    """EfficientNet-B2 with custom classification head for deepfake detection.

    Binary classification: REAL=0, FAKE=1
    """

    def __init__(self, num_classes=2):
        super().__init__()
        self.backbone = models.efficientnet_b2(weights=models.EfficientNet_B2_Weights.IMAGENET1K_V1)
        in_features = self.backbone.classifier[1].in_features
        self.backbone.classifier = nn.Sequential(
            nn.Dropout(0.5),
            nn.Linear(in_features, 256),
            nn.ReLU(inplace=True),
            nn.Dropout(0.25),
            nn.Linear(256, num_classes),
        )

    def forward(self, x):
        return self.backbone(x)


# ============================================================
# DATASET LOADERS
# ============================================================

class FaceForensicsDeepfakeDataset(Dataset):
    """FaceForensics++ dataset for deepfake detection.

    Expected structure:
        data/faceforensics++/
            original_sequences/youtube/c23/videos/   (REAL, label=0)
            manipulated_sequences/
                Deepfakes/c23/videos/               (FAKE, label=1)
                Face2Face/c23/videos/               (FAKE, label=1)
                FaceSwap/c23/videos/                (FAKE, label=1)

    Extracts evenly-spaced frames from each video.
    """

    def __init__(self, data_root, split='train', transform=None, max_frames_per_video=10):
        self.data_root = data_root
        self.transform = transform
        self.samples = []
        self.max_frames = max_frames_per_video

        self._load_samples(split)

    def _load_samples(self, split):
        ff_root = os.path.join(self.data_root, 'faceforensics++')
        if not os.path.exists(ff_root):
            logger.warning("FaceForensics++ not found at %s", ff_root)
            return

        original_dir = os.path.join(ff_root, 'original_sequences', 'youtube', 'c23', 'videos')
        manipulated_dir = os.path.join(ff_root, 'manipulated_sequences')

        if os.path.exists(original_dir):
            for fname in sorted(os.listdir(original_dir)):
                if fname.endswith('.mp4'):
                    self.samples.append((os.path.join(original_dir, fname), 0))

        for method in ['Deepfakes', 'Face2Face', 'FaceSwap']:
            method_dir = os.path.join(manipulated_dir, method, 'c23', 'videos')
            if os.path.exists(method_dir):
                for fname in sorted(os.listdir(method_dir)):
                    if fname.endswith('.mp4'):
                        self.samples.append((os.path.join(method_dir, fname), 1))

        logger.info("FaceForensics++: %d videos (%s split)",
                     len(self.samples), split)

    def _extract_frames(self, video_path):
        """Extract evenly-spaced frames from video."""
        cap = cv2.VideoCapture(video_path)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total <= 0:
            cap.release()
            return []

        indices = np.linspace(0, total - 1, self.max_frames, dtype=int)
        frames = []
        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if ret:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frames.append(frame)
        cap.release()
        return frames

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        video_path, label = self.samples[idx]
        frames = self._extract_frames(video_path)

        if not frames:
            dummy = np.zeros((224, 224, 3), dtype=np.uint8)
            if self.transform:
                dummy = self.transform(dummy)
            return dummy, label

        frame = frames[np.random.randint(len(frames))]

        if self.transform:
            frame = self.transform(frame)

        return frame, label


class ReplayAttackDataset(Dataset):
    """Replay-Attack dataset for anti-spoofing.

    Expected structure:
        data/replay-attack/
            real/        (REAL faces, label=0)
            attacks/     (Spoof faces, label=1)
    """

    def __init__(self, data_root, transform=None):
        self.data_root = data_root
        self.transform = transform
        self.samples = []

        replay_root = os.path.join(data_root, 'replay-attack')
        if not os.path.exists(replay_root):
            logger.warning("Replay-Attack not found at %s", replay_root)
            return

        for subdir, label in [('real', 0), ('attacks', 1)]:
            path = os.path.join(replay_root, subdir)
            if os.path.exists(path):
                for root, dirs, files in os.walk(path):
                    for fname in files:
                        if fname.lower().endswith(('.jpg', '.png', '.jpeg', '.bmp')):
                            self.samples.append((os.path.join(root, fname), label))

        logger.info("Replay-Attack: %d images", len(self.samples))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        img_path, label = self.samples[idx]
        img = cv2.imread(img_path)
        if img is None:
            img = np.zeros((224, 224, 3), dtype=np.uint8)
        else:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        if self.transform:
            img = self.transform(img)

        return img, label


class OULUNPUDataset(Dataset):
    """OULU-NPU dataset for anti-spoofing.

    Expected structure:
        data/oulu-npu/
            train/          (training images)
                real/       (REAL, label=0)
                fake/       (FAKE, label=1)
            test/           (test images)
                real/
                fake/
    """

    def __init__(self, data_root, transform=None):
        self.data_root = data_root
        self.transform = transform
        self.samples = []

        oulu_root = os.path.join(data_root, 'oulu-npu')
        if not os.path.exists(oulu_root):
            logger.warning("OULU-NPU not found at %s", oulu_root)
            return

        for split in ['train', 'test']:
            split_dir = os.path.join(oulu_root, split)
            if not os.path.exists(split_dir):
                continue
            for subdir, label in [('real', 0), ('fake', 1), ('live', 0), ('spoof', 1)]:
                path = os.path.join(split_dir, subdir)
                if os.path.exists(path):
                    for fname in sorted(os.listdir(path)):
                        if fname.lower().endswith(('.jpg', '.png', '.jpeg', '.bmp')):
                            self.samples.append((os.path.join(path, fname), label))

        logger.info("OULU-NPU: %d images", len(self.samples))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        img_path, label = self.samples[idx]
        img = cv2.imread(img_path)
        if img is None:
            img = np.zeros((224, 224, 3), dtype=np.uint8)
        else:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        if self.transform:
            img = self.transform(img)

        return img, label


class CASIAFASDDataset(Dataset):
    """CASIA-FASD dataset for anti-spoofing / face liveness detection.

    Expected structure:
        data/casia-fasd/
            train/live/      (REAL faces, label=0)
            train/spoof/     (Spoof faces, label=1)
            test/live/       (REAL faces, label=0)
            test/spoof/      (Spoof faces, label=1)
    """

    def __init__(self, data_root, split='train', transform=None, max_samples=None):
        self.data_root = data_root
        self.transform = transform
        self.samples = []

        casia_root = os.path.join(data_root, 'casia-fasd')
        if not os.path.exists(casia_root):
            logger.warning("CASIA-FASD not found at %s", casia_root)
            return

        for subdir, label in [('live', 0), ('spoof', 1)]:
            path = os.path.join(casia_root, split, subdir)
            if os.path.exists(path):
                for fname in sorted(os.listdir(path)):
                    if fname.lower().endswith(('.jpg', '.png', '.jpeg', '.bmp')):
                        self.samples.append((os.path.join(path, fname), label))

        if max_samples and len(self.samples) > max_samples:
            random.seed(42)
            self.samples = random.sample(self.samples, max_samples)

        logger.info("CASIA-FASD (%s): %d images", split, len(self.samples))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        img_path, label = self.samples[idx]
        img = cv2.imread(img_path)
        if img is None:
            img = np.zeros((224, 224, 3), dtype=np.uint8)
        else:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        if self.transform:
            img = self.transform(img)

        return img, label


# ============================================================
# DATA AUGMENTATION
# ============================================================

def get_transforms(split='train'):
    """Get data transforms with augmentation for training."""
    if split == 'train':
        return transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((224, 224)),
            transforms.RandomHorizontalFlip(p=0.5),
            transforms.RandomRotation(15),
            transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3),
            transforms.RandomAffine(degrees=0, translate=(0.1, 0.1)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            transforms.RandomErasing(p=0.2),
        ])
    else:
        return transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])


# ============================================================
# TRAINING METRICS
# ============================================================

def compute_metrics(all_preds, all_labels, all_probs):
    """Compute accuracy, precision, recall, F1, ROC-AUC."""
    preds = np.array(all_preds)
    labels = np.array(all_labels)
    probs = np.array(all_probs)

    tp = np.sum((preds == 1) & (labels == 1))
    fp = np.sum((preds == 1) & (labels == 0))
    fn = np.sum((preds == 0) & (labels == 1))
    tn = np.sum((preds == 0) & (labels == 0))

    accuracy = (tp + tn) / max(tp + fp + fn + tn, 1)
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-6)

    # ROC-AUC via trapezoidal rule
    try:
        sorted_indices = np.argsort(-probs)
        sorted_labels = labels[sorted_indices]
        tprs = []
        fprs = []
        positives = np.sum(labels == 1)
        negatives = np.sum(labels == 0)

        tp_cum = 0
        fp_cum = 0
        for sl in sorted_labels:
            if sl == 1:
                tp_cum += 1
            else:
                fp_cum += 1
            tprs.append(tp_cum / max(positives, 1))
            fprs.append(fp_cum / max(negatives, 1))

        tprs = np.array([0] + tprs + [1])
        fprs = np.array([0] + fprs + [1])
        roc_auc = float(np.trapz(tprs, fprs))
        roc_auc = max(0.0, min(1.0, roc_auc))
    except Exception:
        roc_auc = 0.5

    return {
        'accuracy': round(float(accuracy), 4),
        'precision': round(float(precision), 4),
        'recall': round(float(recall), 4),
        'f1': round(float(f1), 4),
        'roc_auc': round(float(roc_auc), 4),
        'tp': int(tp), 'fp': int(fp), 'fn': int(fn), 'tn': int(tn),
    }


# ============================================================
# TRAINING LOOP
# ============================================================

def train_epoch(model, loader, criterion, optimizer, device):
    """Train for one epoch."""
    model.train()
    total_loss = 0.0
    correct = 0
    total = 0

    for batch_idx, (images, labels) in enumerate(loader):
        images = images.to(device)
        labels = labels.to(device)

        optimizer.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()

        total_loss += loss.item() * images.size(0)
        _, predicted = outputs.max(1)
        correct += predicted.eq(labels).sum().item()
        total += labels.size(0)

        if (batch_idx + 1) % 20 == 0:
            logger.info("    Batch %d/%d, Loss: %.4f, Acc: %.2f%%",
                        batch_idx + 1, len(loader), loss.item(), 100.0 * correct / total)

    avg_loss = total_loss / max(total, 1)
    accuracy = 100.0 * correct / max(total, 1)
    return avg_loss, accuracy


def validate(model, loader, criterion, device):
    """Validate model and compute all metrics."""
    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0
    all_preds = []
    all_labels = []
    all_probs = []

    with torch.no_grad():
        for images, labels in loader:
            images = images.to(device)
            labels = labels.to(device)

            outputs = model(images)
            loss = criterion(outputs, labels)

            total_loss += loss.item() * images.size(0)
            probs = torch.softmax(outputs, dim=1)
            _, predicted = outputs.max(1)
            correct += predicted.eq(labels).sum().item()
            total += labels.size(0)

            all_preds.extend(predicted.cpu().numpy())
            all_labels.extend(labels.cpu().numpy())
            all_probs.extend(probs[:, 1].cpu().numpy())

    avg_loss = total_loss / max(total, 1)
    accuracy = 100.0 * correct / max(total, 1)
    metrics = compute_metrics(all_preds, all_labels, all_probs)

    return avg_loss, accuracy, metrics


# ============================================================
# MAIN TRAINING FUNCTION
# ============================================================

def train_model(args):
    """Main training loop with checkpointing and best-model selection."""
    os.makedirs(MODELS_DIR, exist_ok=True)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    logger.info("Device: %s", device)

    train_transform = get_transforms('train')
    val_transform = get_transforms('val')

    datasets_list = []

    if args.dataset in ('all', 'faceforensics'):
        ds = FaceForensicsDeepfakeDataset(args.data_root, transform=train_transform)
        if len(ds) > 0:
            datasets_list.append(ds)

    if args.dataset in ('all', 'replay'):
        ds = ReplayAttackDataset(args.data_root, transform=train_transform)
        if len(ds) > 0:
            datasets_list.append(ds)

    if args.dataset in ('all', 'oulu'):
        ds = OULUNPUDataset(args.data_root, transform=train_transform)
        if len(ds) > 0:
            datasets_list.append(ds)

    if args.dataset in ('all', 'casia'):
        ds = CASIAFASDDataset(args.data_root, split='train', transform=train_transform)
        if len(ds) > 0:
            datasets_list.append(ds)

    if not datasets_list:
        logger.error("No datasets found in %s", args.data_root)
        logger.error("Expected: data/faceforensics++/, data/replay-attack/, data/oulu-npu/, data/casia-fasd/")
        return

    from torch.utils.data import ConcatDataset
    combined = ConcatDataset(datasets_list) if len(datasets_list) > 1 else datasets_list[0]
    logger.info("Total samples: %d", len(combined))

    # Apply subset limit if specified
    if args.subset and args.subset < len(combined):
        indices = list(range(len(combined)))
        random.seed(42)
        random.shuffle(indices)
        indices = indices[:args.subset]
        combined = Subset(combined, indices)
        logger.info("Using subset: %d samples", args.subset)

    # Train/val split (80/20)
    val_size = int(len(combined) * 0.2)
    train_size = len(combined) - val_size
    train_dataset, val_dataset = random_split(combined, [train_size, val_size])

    # Optimize DataLoader for 8GB RAM
    num_workers = min(2, os.cpu_count() or 1)
    train_loader = DataLoader(
        train_dataset, batch_size=args.batch_size, shuffle=True,
        num_workers=num_workers, pin_memory=True, drop_last=True,
    )
    val_loader = DataLoader(
        val_dataset, batch_size=args.batch_size, shuffle=False,
        num_workers=num_workers, pin_memory=True,
    )

    logger.info("Train: %d, Val: %d", train_size, val_size)

    # Model
    model = DeepfakeEfficientNetB2(num_classes=2).to(device)

    # Freeze backbone, train classifier head only
    for param in model.backbone.parameters():
        param.requires_grad = False
    for param in list(model.backbone.parameters())[-20:]:
        param.requires_grad = True

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(filter(lambda p: p.requires_grad, model.parameters()),
                          lr=args.lr, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    best_f1 = 0.0
    best_roc_auc = 0.0
    history = []

    logger.info("Starting training for %d epochs...", args.epochs)

    for epoch in range(args.epochs):
        logger.info("Epoch %d/%d", epoch + 1, args.epochs)
        start = time.time()

        train_loss, train_acc = train_epoch(model, train_loader, criterion, optimizer, device)
        val_loss, val_acc, metrics = validate(model, val_loader, criterion, device)
        scheduler.step()

        elapsed = time.time() - start
        logger.info(
            "  Train Loss: %.4f, Acc: %.2f%% | Val Loss: %.4f, Acc: %.2f%% | "
            "F1: %.4f, ROC-AUC: %.4f | Time: %.1fs",
            train_loss, train_acc, val_loss, val_acc,
            metrics['f1'], metrics['roc_auc'], elapsed,
        )

        epoch_record = {
            'epoch': epoch + 1,
            'train_loss': round(train_loss, 4),
            'train_acc': round(train_acc, 2),
            'val_loss': round(val_loss, 4),
            'val_acc': round(val_acc, 2),
            **metrics,
            'lr': round(scheduler.get_last_lr()[0], 6),
            'time': round(elapsed, 1),
        }
        history.append(epoch_record)

        # Save best model (by F1, then ROC-AUC)
        is_best = (metrics['f1'] > best_f1) or (
            metrics['f1'] == best_f1 and metrics['roc_auc'] > best_roc_auc
        )
        if is_best:
            best_f1 = metrics['f1']
            best_roc_auc = metrics['roc_auc']
            torch.save({
                'model_state_dict': model.state_dict(),
                'model_type': 'deepfake_efficientnet_b2',
                'num_classes': 2,
                'class_names': ['real', 'fake'],
                'input_size': (3, 224, 224),
                'best_f1': best_f1,
                'best_roc_auc': best_roc_auc,
                'best_accuracy': val_acc,
                'epoch': epoch + 1,
                'threshold': 0.5,
            }, OUTPUT_MODEL_PATH)
            logger.info("  Saved best model (F1: %.4f, ROC-AUC: %.4f)", best_f1, best_roc_auc)

    # Save training history
    history_path = os.path.join(MODELS_DIR, 'deepfake_training_history.json')
    with open(history_path, 'w') as f:
        json.dump(history, f, indent=2)
    logger.info("Training history saved to %s", history_path)

    logger.info("Training complete. Best F1: %.4f, ROC-AUC: %.4f", best_f1, best_roc_auc)
    logger.info("Model saved to: %s", OUTPUT_MODEL_PATH)


# ============================================================
# CLI ENTRY POINT
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='Train EfficientNet-B2 Deepfake Detector',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick test with subset:
  python train_deepfake.py --data-root ../data --subset 1000 --epochs 10

  # Full training:
  python train_deepfake.py --data-root ../data --epochs 20 --batch-size 16

  # Only FaceForensics++:
  python train_deepfake.py --data-root ../data --dataset faceforensics --epochs 20
        """
    )
    parser.add_argument('--data-root', type=str, default=DATA_DIR,
                        help='Root directory containing datasets (default: ./data)')
    parser.add_argument('--dataset', type=str, default='casia',
                        choices=['all', 'faceforensics', 'replay', 'oulu', 'casia'],
                        help='Dataset to use (default: casia)')
    parser.add_argument('--epochs', type=int, default=20,
                        help='Number of training epochs (default: 20)')
    parser.add_argument('--batch-size', type=int, default=16,
                        help='Batch size (default: 16, use 8 for 8GB RAM)')
    parser.add_argument('--lr', type=float, default=1e-4,
                        help='Learning rate (default: 1e-4)')
    parser.add_argument('--subset', type=int, default=None,
                        help='Use only N samples for quick testing')
    args = parser.parse_args()

    train_model(args)


if __name__ == '__main__':
    main()
