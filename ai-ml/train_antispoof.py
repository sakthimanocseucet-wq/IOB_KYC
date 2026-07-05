"""
Face Anti-Spoofing Model Training Script
Fine-tunes a pre-trained EfficientNet-B0 on face anti-spoofing datasets.

Usage:
    python train_antispoof.py --dataset all --epochs 20 --lr 0.001
    python train_antispoof.py --dataset casia --epochs 30
    python train_antispoof.py --dataset oulu --epochs 20 --batch-size 16
"""

import os
import sys
import json
import time
import argparse
import logging
import numpy as np

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, random_split
import torchvision.models as models
import torchvision.transforms as transforms

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

MODELS_DIR = os.path.join(os.path.dirname(__file__), 'models', 'trained')
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
os.makedirs(MODELS_DIR, exist_ok=True)


class AntiSpoofClassifier(nn.Module):
    """
    Anti-spoofing classifier using EfficientNet-B0 backbone.
    Replaces the generic ImageNet head with a binary spoof classifier.
    """

    def __init__(self, num_classes=2, dropout=0.5):
        super().__init__()
        self.backbone = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.IMAGENET1K_V1)

        for param in list(self.backbone.parameters())[:-20]:
            param.requires_grad = False

        in_features = self.backbone.classifier[1].in_features
        self.backbone.classifier = nn.Sequential(
            nn.Dropout(p=dropout),
            nn.Linear(in_features, 256),
            nn.ReLU(),
            nn.Dropout(p=dropout * 0.5),
            nn.Linear(256, num_classes)
        )

    def forward(self, x):
        return self.backbone(x)


class DeepfakeClassifier(nn.Module):
    """
    Deepfake detection classifier using EfficientNet-B2 backbone.
    Trained on FaceForensics++ manipulated vs original sequences.
    """

    def __init__(self, num_classes=2, dropout=0.5):
        super().__init__()
        self.backbone = models.efficientnet_b2(weights=models.EfficientNet_B2_Weights.IMAGENET1K_V1)

        for param in list(self.backbone.parameters())[:-25]:
            param.requires_grad = False

        in_features = self.backbone.classifier[1].in_features
        self.backbone.classifier = nn.Sequential(
            nn.Dropout(p=dropout),
            nn.Linear(in_features, 256),
            nn.ReLU(),
            nn.Dropout(p=dropout * 0.5),
            nn.Linear(256, num_classes)
        )

    def forward(self, x):
        return self.backbone(x)


def get_transforms(split='train'):
    if split == 'train':
        return transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((224, 224)),
            transforms.RandomHorizontalFlip(),
            transforms.RandomRotation(10),
            transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
    else:
        return transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])


def train_epoch(model, loader, criterion, optimizer, device):
    model.train()
    total_loss = 0.0
    correct = 0
    total = 0

    for batch_idx, (images, labels, _) in enumerate(loader):
        images = images.float().to(device)
        labels = labels.long().to(device)

        optimizer.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()

        total_loss += loss.item() * images.size(0)
        _, predicted = outputs.max(1)
        correct += predicted.eq(labels).sum().item()
        total += labels.size(0)

        if (batch_idx + 1) % 50 == 0:
            logger.info("  Batch %d/%d - Loss: %.4f, Acc: %.2f%%",
                        batch_idx + 1, len(loader), loss.item(), 100.0 * correct / total)

    return total_loss / total, 100.0 * correct / total


def validate(model, loader, criterion, device):
    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0
    all_preds = []
    all_labels = []

    with torch.no_grad():
        for images, labels, _ in loader:
            images = images.float().to(device)
            labels = labels.long().to(device)

            outputs = model(images)
            loss = criterion(outputs, labels)

            total_loss += loss.item() * images.size(0)
            _, predicted = outputs.max(1)
            correct += predicted.eq(labels).sum().item()
            total += labels.size(0)

            all_preds.extend(predicted.cpu().numpy())
            all_labels.extend(labels.cpu().numpy())

    all_preds = np.array(all_preds)
    all_labels = np.array(all_labels)

    real_mask = all_labels == 0
    spoof_mask = all_labels == 1

    accuracy = 100.0 * correct / total

    real_acc = 0.0
    spoof_acc = 0.0
    if real_mask.sum() > 0:
        real_acc = 100.0 * (all_preds[real_mask] == 0).sum() / real_mask.sum()
    if spoof_mask.sum() > 0:
        spoof_acc = 100.0 * (all_preds[spoof_mask] == 1).sum() / spoof_mask.sum()

    APCER = 100.0 - spoof_acc
    BPCER = 100.0 - real_acc
    ACER = (APCER + BPCER) / 2.0

    return total_loss / total, accuracy, APCER, BPCER, ACER


def train_model(dataset_name='all', epochs=20, batch_size=32, lr=0.001, model_type='antispoof'):
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    logger.info("Using device: %s", device)

    from dataset_loaders import (CASIAFASDDataset, OULUNPUDataset,
                                  FaceForensicsDataset, ReplayAttackDataset, load_all_datasets)

    if dataset_name == 'all':
        dataset, stats = load_all_datasets(DATA_DIR)
    elif dataset_name == 'casia':
        dataset = CASIAFASDDataset()
        stats = {'CASIA-FASD': {'total': len(dataset)}}
    elif dataset_name == 'oulu':
        dataset = OULUNPUDataset()
        stats = {'OULU-NPU': {'total': len(dataset)}}
    elif dataset_name == 'faceforensics':
        dataset = FaceForensicsDataset()
        stats = {'FaceForensics++': {'total': len(dataset)}}
    elif dataset_name == 'replay':
        dataset = ReplayAttackDataset()
        stats = {'Replay-Attack': {'total': len(dataset)}}
    else:
        logger.error("Unknown dataset: %s", dataset_name)
        return

    if dataset is None or len(dataset) == 0:
        logger.error("No data found! Download datasets to data/ folder first.")
        logger.info("See data/DOWNLOAD.md for instructions.")
        return

    logger.info("Dataset stats: %s", json.dumps(stats, indent=2))
    logger.info("Total samples: %d", len(dataset))

    train_size = int(0.8 * len(dataset))
    val_size = len(dataset) - train_size
    train_dataset, val_dataset = random_split(dataset, [train_size, val_size])

    logger.info("Train: %d samples, Val: %d samples", train_size, val_size)

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True,
                              num_workers=0, pin_memory=False)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False,
                            num_workers=0, pin_memory=False)

    if model_type == 'deepfake':
        model = DeepfakeClassifier(num_classes=2).to(device)
        model_name = 'deepfake_detector'
    else:
        model = AntiSpoofClassifier(num_classes=2).to(device)
        model_name = 'antispoof_model'

    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    logger.info("Model: %s - Total params: %d, Trainable: %d", model_name, total_params, trainable_params)

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(filter(lambda p: p.requires_grad, model.parameters()),
                           lr=lr, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', factor=0.5, patience=3)

    best_acer = 100.0
    best_accuracy = 0.0
    history = []

    logger.info("=" * 60)
    logger.info("Starting training: %s on %s for %d epochs", model_name, dataset_name, epochs)
    logger.info("=" * 60)

    for epoch in range(epochs):
        epoch_start = time.time()
        logger.info("Epoch %d/%d (lr=%.6f)", epoch + 1, epochs, optimizer.param_groups[0]['lr'])

        train_loss, train_acc = train_epoch(model, train_loader, criterion, optimizer, device)
        val_loss, val_acc, APCER, BPCER, ACER = validate(model, val_loader, criterion, device)
        scheduler.step(val_loss)

        epoch_time = time.time() - epoch_start

        logger.info(
            "  Train Loss: %.4f | Train Acc: %.2f%% | Val Loss: %.4f | Val Acc: %.2f%% | ACER: %.2f%% | Time: %.1fs",
            train_loss, train_acc, val_loss, val_acc, ACER, epoch_time
        )
        logger.info("  APCER: %.2f%% (spoof accepted) | BPCER: %.2f%% (real rejected)", APCER, BPCER)

        history.append({
            'epoch': epoch + 1,
            'train_loss': train_loss, 'train_acc': train_acc,
            'val_loss': val_loss, 'val_acc': val_acc,
            'APCER': APCER, 'BPCER': BPCER, 'ACER': ACER,
            'lr': optimizer.param_groups[0]['lr']
        })

        if ACER < best_acer or (ACER == best_acer and val_acc > best_accuracy):
            best_acer = ACER
            best_accuracy = val_acc
            save_path = os.path.join(MODELS_DIR, f'{model_name}_best.pth')
            torch.save({
                'model_state_dict': model.state_dict(),
                'model_type': model_type,
                'dataset': dataset_name,
                'best_acer': best_acer,
                'best_accuracy': best_accuracy,
                'epoch': epoch + 1,
                'input_size': (3, 224, 224),
                'class_names': ['real', 'spoof'],
            }, save_path)
            logger.info("  -> Saved best model (ACER=%.2f%%, Acc=%.2f%%)", best_acer, best_accuracy)

    final_path = os.path.join(MODELS_DIR, f'{model_name}_final.pth')
    torch.save({
        'model_state_dict': model.state_dict(),
        'model_type': model_type,
        'dataset': dataset_name,
        'history': history,
        'input_size': (3, 224, 224),
        'class_names': ['real', 'spoof'],
    }, final_path)

    history_path = os.path.join(MODELS_DIR, f'{model_name}_history.json')
    with open(history_path, 'w') as f:
        json.dump(history, f, indent=2)

    logger.info("=" * 60)
    logger.info("Training complete!")
    logger.info("Best ACER: %.2f%% | Best Accuracy: %.2f%%", best_acer, best_accuracy)
    logger.info("Models saved to: %s", MODELS_DIR)
    logger.info("Best model: %s", os.path.join(MODELS_DIR, f'{model_name}_best.pth'))
    logger.info("=" * 60)

    return model


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Train face anti-spoofing model')
    parser.add_argument('--dataset', type=str, default='all',
                        choices=['all', 'casia', 'oulu', 'faceforensics', 'replay'],
                        help='Dataset to use')
    parser.add_argument('--model-type', type=str, default='antispoof',
                        choices=['antispoof', 'deepfake'],
                        help='Model type to train')
    parser.add_argument('--epochs', type=int, default=20, help='Number of epochs')
    parser.add_argument('--batch-size', type=int, default=32, help='Batch size')
    parser.add_argument('--lr', type=float, default=0.001, help='Learning rate')

    args = parser.parse_args()
    train_model(
        dataset_name=args.dataset,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        model_type=args.model_type,
    )
