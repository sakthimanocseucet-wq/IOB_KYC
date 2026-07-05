import sys, os, base64, json, requests, cv2, numpy as np
sys.path.insert(0, os.path.dirname(__file__))

r = requests.get('http://localhost:5001/health', timeout=5)
print('Health:', r.json().get('status'))

r = requests.post('http://localhost:5001/api/ai/liveness/challenge', json={}, timeout=10)
data = r.json()
session_id = data['data']['session_id']
challenge = data['data']['challenge']
ct = challenge['challenge_type']
print('Challenge:', ct, 'session:', session_id)

frames = []
for i in range(15):
    img = np.ones((480, 640, 3), dtype=np.uint8) * 128
    cx, cy = 320, 240
    cv2.ellipse(img, (cx, cy), (120, 150), 0, 0, 360, (180, 160, 140), -1)
    eye_y = cy - 30 + (i % 3)
    left_eye_x = cx - 50
    right_eye_x = cx + 50
    cv2.ellipse(img, (left_eye_x, eye_y), (12, 6), 0, 0, 360, (50, 50, 50), -1)
    cv2.circle(img, (left_eye_x + 2, eye_y - 2), 3, (20, 20, 20), -1)
    cv2.ellipse(img, (right_eye_x, eye_y), (12, 6), 0, 0, 360, (50, 50, 50), -1)
    cv2.circle(img, (right_eye_x + 2, eye_y - 2), 3, (20, 20, 20), -1)
    cv2.ellipse(img, (cx, cy + 50), (20, 5), 0, 0, 360, (100, 80, 80), 2)
    cv2.line(img, (cx, cy - 10), (cx - 5, cy + 20), (140, 120, 120), 2)
    _, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    b64 = base64.b64encode(buf).decode('utf-8')
    frames.append('data:image/jpeg;base64,' + b64)

print('Created', len(frames), 'frames')

r = requests.post('http://localhost:5001/api/ai/liveness/verify-challenge',
                 json={'session_id': session_id, 'challenge': challenge, 'frames': frames},
                 timeout=30)
result = r.json()
d = result.get('data', {})
print('Result:', 'passed=' + str(d.get('passed')), 'reason=' + str(d.get('reason', 'none')))
print('Full result keys:', list(d.keys()))
