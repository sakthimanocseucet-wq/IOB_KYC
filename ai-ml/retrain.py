import sys, os, time, json, logging
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, Subset
import torchvision.models as models

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
MODELS_DIR = os.path.join(BASE, 'models', 'trained')
os.makedirs(MODELS_DIR, exist_ok=True)

from dataset_loaders import CASIAFASDDataset


class AntiSpoofClassifier(nn.Module):
    def __init__(self, num_classes=2, dropout=0.5):
        super().__init__()
        self.backbone = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.IMAGENET1K_V1)
        for param in list(self.backbone.parameters())[:-20]:
            param.requires_grad = False
        in_features = self.backbone.classifier[1].in_features
        self.backbone.classifier = nn.Sequential(
            nn.Dropout(p=dropout), nn.Linear(in_features, 256), nn.ReLU(),
            nn.Dropout(p=dropout * 0.5), nn.Linear(256, num_classes)
        )

    def forward(self, x):
        return self.backbone(x)


def main():
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    logger.info("Using device: %s", device)

    full_dataset = CASIAFASDDataset()
    logger.info("Full dataset: %d samples", len(full_dataset))

    np.random.seed(42)
    indices = np.random.choice(len(full_dataset), size=10000, replace=False)
    subset = Subset(full_dataset, indices)

    train_size = int(0.8 * len(subset))
    val_size = len(subset) - train_size
    train_ds, val_ds = torch.utils.data.random_split(subset, [train_size, val_size])
    logger.info("Train: %d, Val: %d", train_size, val_size)

    train_loader = DataLoader(train_ds, batch_size=64, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=64, shuffle=False, num_workers=0)

    model = AntiSpoofClassifier(num_classes=2).to(device)
    total_params = sum(p.numel() for p in model.parameters())
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    logger.info("Params: total=%d trainable=%d", total_params, trainable_params)

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(filter(lambda p: p.requires_grad, model.parameters()), lr=0.002, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='min', factor=0.5, patience=2)

    best_acer = 100.0
    history = []
    EPOCHS = 5

    for epoch in range(EPOCHS):
        t0 = time.time()
        model.train()
        total_loss = 0.0
        correct = 0
        total = 0
        for batch_idx, (images, labels, _) in enumerate(train_loader):
            images = images.float().to(device)
            labels = labels.long().to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * images.size(0)
            _, pred = outputs.max(1)
            correct += pred.eq(labels).sum().item()
            total += labels.size(0)
            if (batch_idx + 1) % 30 == 0:
                logger.info("  Batch %d/%d - Loss: %.4f Acc: %.2f%%",
                            batch_idx + 1, len(train_loader), loss.item(), 100.0 * correct / total)
        train_loss = total_loss / total
        train_acc = 100.0 * correct / total

        model.eval()
        val_loss = 0.0
        val_correct = 0
        val_total = 0
        all_preds, all_labels = [], []
        with torch.no_grad():
            for images, labels, _ in val_loader:
                images = images.float().to(device)
                labels = labels.long().to(device)
                outputs = model(images)
                loss = criterion(outputs, labels)
                val_loss += loss.item() * images.size(0)
                _, pred = outputs.max(1)
                val_correct += pred.eq(labels).sum().item()
                val_total += labels.size(0)
                all_preds.extend(pred.cpu().numpy())
                all_labels.extend(labels.cpu().numpy())
        val_loss /= val_total
        val_acc = 100.0 * val_correct / val_total

        all_preds = np.array(all_preds)
        all_labels = np.array(all_labels)
        real_mask = all_labels == 0
        spoof_mask = all_labels == 1
        real_acc = 100.0 * (all_preds[real_mask] == 0).sum() / max(real_mask.sum(), 1) if real_mask.any() else 0
        spoof_acc = 100.0 * (all_preds[spoof_mask] == 1).sum() / max(spoof_mask.sum(), 1) if spoof_mask.any() else 0
        APCER = 100.0 - spoof_acc
        BPCER = 100.0 - real_acc
        ACER = (APCER + BPCER) / 2.0
        scheduler.step(val_loss)
        elapsed = time.time() - t0
        lr = optimizer.param_groups[0]['lr']

        history.append({
            'epoch': epoch + 1, 'train_loss': float(train_loss), 'train_acc': float(train_acc),
            'val_loss': float(val_loss), 'val_acc': float(val_acc),
            'APCER': float(APCER), 'BPCER': float(BPCER), 'ACER': float(ACER), 'lr': float(lr)
        })
        logger.info("Epoch %d/%d (lr=%.6f) - Train Loss: %.4f Acc: %.2f%% | Val Loss: %.4f Acc: %.2f%% | ACER: %.2f%% | %.1fs",
                     epoch + 1, EPOCHS, lr, train_loss, train_acc, val_loss, val_acc, ACER, elapsed)
        logger.info("  APCER: %.2f%% BPCER: %.2f%%", APCER, BPCER)

        if ACER < best_acer:
            best_acer = ACER
            torch.save({
                'model_state_dict': model.state_dict(), 'model_type': 'antispoof',
                'dataset': 'casia', 'best_acer': best_acer, 'best_accuracy': val_acc,
                'epoch': epoch + 1, 'input_size': (3, 224, 224), 'class_names': ['real', 'spoof']
            }, os.path.join(MODELS_DIR, 'antispoof_model_best.pth'))
            logger.info("  -> Saved best model (ACER=%.2f%%, Acc=%.2f%%)", best_acer, val_acc)

    torch.save({
        'model_state_dict': model.state_dict(), 'model_type': 'antispoof', 'dataset': 'casia',
        'history': history, 'input_size': (3, 224, 224), 'class_names': ['real', 'spoof']
    }, os.path.join(MODELS_DIR, 'antispoof_model_final.pth'))

    with open(os.path.join(MODELS_DIR, 'antispoof_model_history.json'), 'w') as f:
        json.dump(history, f, indent=2)

    logger.info("=" * 60)
    logger.info("Training complete! Best ACER: %.2f%%", best_acer)
    logger.info("Models saved to: %s", MODELS_DIR)
    logger.info("=" * 60)


if __name__ == '__main__':
    main()
