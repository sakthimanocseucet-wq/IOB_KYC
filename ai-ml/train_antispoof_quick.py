"""Quick anti-spoofing training using EfficientNet-B0 on CASIA-FASD."""
import os, time, logging, random
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader, random_split
import torchvision.models as models
import torchvision.transforms as transforms
from PIL import Image

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s', force=True)
logger = logging.getLogger(__name__)

MODELS_DIR = os.path.join(os.path.dirname(__file__), 'models', 'trained')
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data', 'casia-fasd')
os.makedirs(MODELS_DIR, exist_ok=True)


class CASIAFASD(Dataset):
    def __init__(self, split='train', max_per_class=3000):
        self.samples = []
        base = os.path.join(DATA_DIR, split)
        for label, subdir in [(0, 'live'), (1, 'spoof')]:
            d = os.path.join(base, subdir)
            if not os.path.exists(d):
                continue
            files = [f for f in os.listdir(d) if f.lower().endswith(('.jpg', '.png', '.bmp'))]
            random.shuffle(files)
            for f in files[:max_per_class]:
                self.samples.append((os.path.join(d, f), label))
        random.shuffle(self.samples)
        self.transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.RandomHorizontalFlip(),
            transforms.ColorJitter(brightness=0.2, contrast=0.2),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
        self.val_transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
        logger.info("CASIA-FASD %s: %d images (live=%d, spoof=%d)",
                     split, len(self.samples),
                     sum(1 for _, l in self.samples if l == 0),
                     sum(1 for _, l in self.samples if l == 1))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        path, label = self.samples[idx]
        img = Image.open(path).convert('RGB')
        if hasattr(self, '_val_mode') and self._val_mode:
            return self.val_transform(img), label
        return self.transform(img), label


class AntiSpoofNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.backbone = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.IMAGENET1K_V1)
        for p in list(self.backbone.parameters())[:-10]:
            p.requires_grad = False
        in_f = self.backbone.classifier[1].in_features
        self.backbone.classifier = nn.Sequential(
            nn.Dropout(0.3),
            nn.Linear(in_f, 2)
        )

    def forward(self, x):
        return self.backbone(x)


def train():
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    logger.info("Device: %s", device)

    train_ds = CASIAFASD('train', max_per_class=3000)
    test_ds = CASIAFASD('test', max_per_class=1000)

    train_loader = DataLoader(train_ds, batch_size=32, shuffle=True, num_workers=0)
    test_loader = DataLoader(test_ds, batch_size=32, shuffle=False, num_workers=0)

    model = AntiSpoofNet().to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=0.001, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=2, factor=0.5)

    best_acc = 0
    epochs = 5

    for epoch in range(epochs):
        model.train()
        total_loss = correct = total = 0
        t0 = time.time()
        for i, (images, labels) in enumerate(train_loader):
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            out = model(images)
            loss = criterion(out, labels)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * images.size(0)
            _, pred = out.max(1)
            correct += pred.eq(labels).sum().item()
            total += labels.size(0)
            if (i + 1) % 100 == 0:
                logger.info("  batch %d/%d loss=%.4f acc=%.1f%%", i+1, len(train_loader), loss.item(), 100*correct/total)

        train_acc = 100.0 * correct / total
        avg_loss = total_loss / total

        model.eval()
        val_correct = val_total = 0
        all_preds, all_labels = [], []
        with torch.no_grad():
            for images, labels in test_loader:
                images, labels = images.to(device), labels.to(device)
                out = model(images)
                _, pred = out.max(1)
                val_correct += pred.eq(labels).sum().item()
                val_total += labels.size(0)
                all_preds.extend(pred.cpu().numpy())
                all_labels.extend(labels.cpu().numpy())

        val_acc = 100.0 * val_correct / val_total
        all_preds = np.array(all_preds)
        all_labels = np.array(all_labels)
        real_mask = all_labels == 0
        spoof_mask = all_labels == 1
        real_acc = 100.0 * (all_preds[real_mask] == 0).sum() / max(real_mask.sum(), 1)
        spoof_acc = 100.0 * (all_preds[spoof_mask] == 1).sum() / max(spoof_mask.sum(), 1)
        apcer = 100.0 - spoof_acc
        bpcer = 100.0 - real_acc
        acer = (apcer + bpcer) / 2.0
        scheduler.step(avg_loss)

        elapsed = time.time() - t0
        logger.info("Epoch %d/%d: loss=%.4f train_acc=%.1f%% val_acc=%.1f%% ACER=%.1f%% APCER=%.1f%% BPCER=%.1f%% time=%.0fs",
                     epoch+1, epochs, avg_loss, train_acc, val_acc, acer, apcer, bpcer, elapsed)

        if val_acc > best_acc:
            best_acc = val_acc
            save_path = os.path.join(MODELS_DIR, 'antispoof_efficientnet_b0.pth')
            torch.save({
                'model_state_dict': model.state_dict(),
                'model_type': 'efficientnet_b0',
                'dataset': 'casia-fasd',
                'best_acc': best_acc,
                'acer': acer,
                'class_names': ['real', 'spoof'],
                'input_size': (3, 224, 224),
            }, save_path)
            logger.info("  -> Saved best model (acc=%.1f%%, ACER=%.1f%%)", best_acc, acer)

    logger.info("Training complete. Best val accuracy: %.1f%%", best_acc)


if __name__ == '__main__':
    train()
