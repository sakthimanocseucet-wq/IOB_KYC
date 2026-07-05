import easyocr, cv2, numpy as np

reader = easyocr.Reader(['en'], gpu=False)

img = np.ones((350, 800, 3), dtype=np.uint8) * 255
cv2.putText(img, 'Government of India', (30, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,0), 2)
cv2.putText(img, 'Rajesh Kumar Sharma', (30, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,0), 2)
cv2.putText(img, 'DOB: 15/08/1990', (30, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,0), 2)
cv2.putText(img, 'Male', (30, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,0), 2)
cv2.putText(img, '1234 5678 9012', (30, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,0), 2)
cv2.putText(img, 'Address: 42 Gandhi Nagar,', (30, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,0), 2)
cv2.putText(img, 'Chennai, Tamil Nadu 600001', (30, 270), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,0), 2)

results = reader.readtext(img, detail=1, paragraph=True)
print("Blocks with paragraph=True:")
for r in results:
    print(f"  [{r[2]:.1f}%] {r[1]}")

results2 = reader.readtext(img, detail=1, paragraph=False)
print("\nItems with paragraph=False:")
for r in results2:
    bbox = r[0]
    y_center = (bbox[0][1] + bbox[2][1]) / 2
    print(f"  y={y_center:.0f} [{r[2]:.1f}%] {r[1]}")
