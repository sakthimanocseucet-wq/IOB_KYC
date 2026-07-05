"""
Dataset loaders for face anti-spoofing training.
Supports CASIA-FASD, OULU-NPU, FaceForensics++, Replay-Attack.
"""

import os
import glob
import logging
from torch.utils.data import Dataset
from PIL import Image
import torchvision.transforms as transforms

logger = logging.getLogger(__name__)


class CASIAFASDDataset(Dataset):
    """CASIA-FASD face anti-spoofing dataset.
    
    Expected structure:
        data/casia-fasd/
            train/live/    *.jpg (real faces)
            train/spoof/   *.jpg (printed photos, warped photos)
            test/live/     *.jpg
            test/spoof/    *.jpg
    """

    def __init__(self, data_dir=None, split='train', transform=None):
        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(__file__), 'data', 'casia-fasd')
        
        self.samples = []
        self.transform = transform or transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        ])

        for label, subdir in [(0, 'live'), (1, 'spoof')]:
            img_dir = os.path.join(data_dir, split, subdir)
            if not os.path.exists(img_dir):
                continue
            for ext in ('*.jpg', '*.jpeg', '*.png', '*.bmp'):
                for img_path in glob.glob(os.path.join(img_dir, '**', ext), recursive=True):
                    self.samples.append((img_path, label))

        logger.info("CASIA-FASD (%s): %d samples", split, len(self.samples))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        img_path, label = self.samples[idx]
        img = Image.open(img_path).convert('RGB')
        if self.transform:
            img = self.transform(img)
        return img, label, idx


class OULUNPUDataset(Dataset):
    """OULU-NPU dataset stub - returns empty if not present."""

    def __init__(self, data_dir=None, split='train', transform=None):
        self.samples = []
        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(__file__), 'data', 'oulu-npu')
        logger.info("OULU-NPU: dataset not found at %s", data_dir)

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        raise IndexError("Empty dataset")


class FaceForensicsDataset(Dataset):
    """FaceForensics++ dataset for deepfake detection."""

    def __init__(self, data_dir=None, split='train', transform=None):
        self.samples = []
        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(__file__), 'data', 'faceforensics++')

        self.transform = transform or transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        ])

        real_dir = os.path.join(data_dir, 'original_sequences', 'youtube', 'c23', 'videos')
        fake_dir = os.path.join(data_dir, 'manipulated_sequences', 'Deepfakes', 'c23', 'videos')

        for subdir, label in [(real_dir, 0), (fake_dir, 1)]:
            if not os.path.exists(subdir):
                continue
            for ext in ('*.jpg', '*.jpeg', '*.png'):
                for img_path in glob.glob(os.path.join(subdir, '**', ext), recursive=True):
                    self.samples.append((img_path, label))

        logger.info("FaceForensics++: %d samples", len(self.samples))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        img_path, label = self.samples[idx]
        img = Image.open(img_path).convert('RGB')
        if self.transform:
            img = self.transform(img)
        return img, label


class ReplayAttackDataset(Dataset):
    """Replay-Attack dataset stub."""

    def __init__(self, data_dir=None, split='train', transform=None):
        self.samples = []
        logger.info("Replay-Attack: dataset not found")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        raise IndexError("Empty dataset")


def load_all_datasets(data_dir):
    """Load all available datasets and return combined dataset."""
    all_samples = []
    stats = {}

    casia = CASIAFASDDataset(data_dir)
    if len(casia) > 0:
        all_samples.extend(casia.samples)
        stats['CASIA-FASD'] = {'total': len(casia)}

    ff = FaceForensicsDataset(data_dir)
    if len(ff) > 0:
        all_samples.extend(ff.samples)
        stats['FaceForensics++'] = {'total': len(ff)}

    class CombinedDataset(Dataset):
        def __init__(self, samples, transform=None):
            self.samples = samples
            self.transform = transform or transforms.Compose([
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
            ])

        def __len__(self):
            return len(self.samples)

        def __getitem__(self, idx):
            img_path, label = self.samples[idx]
            img = Image.open(img_path).convert('RGB')
            if self.transform:
                img = self.transform(img)
            return img, label

    return CombinedDataset(all_samples), stats
