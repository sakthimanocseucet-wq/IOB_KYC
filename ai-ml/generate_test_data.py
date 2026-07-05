"""Generate synthetic training data for testing the pipeline."""
import os, cv2, numpy as np

data_dir = os.path.join(os.path.dirname(__file__), 'data', 'casia-fasd', 'release')
real_dir = os.path.join(data_dir, 'real')
spoof_dir = os.path.join(data_dir, 'warped_photo')
os.makedirs(real_dir, exist_ok=True)
os.makedirs(spoof_dir, exist_ok=True)

np.random.seed(42)

for i in range(200):
    img = np.random.randint(100, 200, (224, 224, 3), dtype=np.uint8)
    cv2.circle(img, (112, 100), 60, (180, 150, 130), -1)
    cv2.circle(img, (90, 90), 8, (50, 30, 20), -1)
    cv2.circle(img, (134, 90), 8, (50, 30, 20), -1)
    cv2.ellipse(img, (112, 125), (15, 8), 0, 0, 180, (80, 40, 40), 2)
    noise = np.random.normal(0, 10, img.shape).astype(np.int16)
    img = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    cv2.imwrite(os.path.join(real_dir, f'real_{i:04d}.jpg'), img)

for i in range(200):
    img = np.zeros((224, 224, 3), dtype=np.uint8)
    cv2.rectangle(img, (20, 20), (204, 204), (200, 200, 200), -1)
    cv2.circle(img, (112, 100), 55, (170, 140, 120), -1)
    cv2.circle(img, (90, 90), 7, (40, 25, 15), -1)
    cv2.circle(img, (134, 90), 7, (40, 25, 15), -1)
    cv2.ellipse(img, (112, 125), (12, 6), 0, 0, 180, (70, 35, 35), 1)
    cv2.rectangle(img, (5, 5), (219, 219), (100, 100, 100), 2)
    cv2.imwrite(os.path.join(spoof_dir, f'spoof_{i:04d}.jpg'), img)

print(f"Generated {len(os.listdir(real_dir))} real + {len(os.listdir(spoof_dir))} spoof images")
