"""
QR Code Verification Module for Digital KYC System

Detects and decodes QR codes from Aadhaar/PAN card images,
then compares extracted fields against OCR output.

Supports:
  - Aadhaar QR: Name, DOB, Aadhaar Number
  - PAN QR: Name, DOB, PAN Number

Normalization:
  - Case-insensitive comparison
  - Strip leading/trailing spaces
  - Remove spaces and hyphens from ID numbers
  - Normalize dates to DD-MM-YYYY format
"""

import cv2
import numpy as np
import re
import json
import logging
import base64
import time
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    from pyzbar import pyzbar
    HAS_PYZBAR = True
except ImportError:
    HAS_PYZBAR = False
    logger.warning("pyzbar not available — QR detection will use OpenCV fallback only")


def _decode_image(image_data):
    """Decode base64 string or bytes to BGR numpy array."""
    if isinstance(image_data, str):
        if ',' in image_data:
            image_data = image_data.split(',')[1]
        image_bytes = base64.b64decode(image_data)
    elif isinstance(image_data, bytes):
        image_bytes = image_data
    else:
        raise ValueError("Unsupported image data type")

    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode image - invalid format")
    return img


def _preprocess_for_qr(img):
    """Apply preprocessing to improve QR detection on ID documents."""
    preprocessed = []

    preprocessed.append(('original', img))

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    preprocessed.append(('gray', cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)))

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    preprocessed.append(('clahe', cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)))

    _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    preprocessed.append(('binary', cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)))

    _, binary_inv = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    preprocessed.append(('binary_inv', cv2.cvtColor(binary_inv, cv2.COLOR_GRAY2BGR)))

    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    _, sharp_binary = cv2.threshold(blurred, 127, 255, cv2.THRESH_BINARY)
    preprocessed.append(('sharp', cv2.cvtColor(sharp_binary, cv2.COLOR_GRAY2BGR)))

    return preprocessed


def _detect_qr_opencv(img):
    """Detect QR codes using OpenCV QRCodeDetector."""
    detector = cv2.QRCodeDetector()
    data, points, _ = detector.detectAndDecode(img)
    if data and points is not None:
        return data
    return None


def _detect_qr_pyzbar(img):
    """Detect QR codes using pyzbar."""
    if not HAS_PYZBAR:
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    decoded_objects = pyzbar.decode(gray)
    for obj in decoded_objects:
        if obj.type == 'QRCODE':
            return obj.data.decode('utf-8', errors='ignore')
    for obj in decoded_objects:
        if obj.type in ('QRCODE', 'CODE128', 'EAN13', 'UPCA'):
            return obj.data.decode('utf-8', errors='ignore')
    return None


def detect_qr_code(image_data):
    """Detect and decode QR code from image using multiple strategies.

    Args:
        image_data: base64 string, bytes, or file of the document image

    Returns:
        dict with 'detected' (bool) and 'data' (str or None)
    """
    start = time.time()

    try:
        img = _decode_image(image_data)
    except Exception as e:
        logger.warning("[QR] Image decode failed: %s", e)
        return {'detected': False, 'data': None, 'error': str(e)}

    h, w = img.shape[:2]
    if max(h, w) > 2000:
        scale = 2000 / max(h, w)
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    preprocessed = _preprocess_for_qr(img)

    qr_data = None

    for name, proc_img in preprocessed:
        data = _detect_qr_pyzbar(proc_img)
        if data:
            qr_data = data
            logger.info("[QR] Decoded via pyzbar (%s) in %.1fms", name, (time.time() - start) * 1000)
            break

        data = _detect_qr_opencv(proc_img)
        if data:
            qr_data = data
            logger.info("[QR] Decoded via OpenCV (%s) in %.1fms", name, (time.time() - start) * 1000)
            break

    if not qr_data:
        h_orig, w_orig = img.shape[:2]
        for scale_factor in [1.5, 2.0, 0.5]:
            resized = cv2.resize(img, None, fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_CUBIC)
            for name, proc_img in _preprocess_for_qr(resized):
                data = _detect_qr_pyzbar(proc_img)
                if data:
                    qr_data = data
                    logger.info("[QR] Decoded via pyzbar (scale %.1f, %s) in %.1fms",
                                scale_factor, name, (time.time() - start) * 1000)
                    break
                data = _detect_qr_opencv(proc_img)
                if data:
                    qr_data = data
                    logger.info("[QR] Decoded via OpenCV (scale %.1f, %s) in %.1fms",
                                scale_factor, name, (time.time() - start) * 1000)
                    break
            if qr_data:
                break

    elapsed = round((time.time() - start) * 1000, 1)

    if qr_data:
        logger.info("[QR] QR code detected and decoded in %.1fms (length=%d)", elapsed, len(qr_data))
        return {'detected': True, 'data': qr_data}
    else:
        logger.info("[QR] No QR code found in %.1fms", elapsed)
        return {'detected': False, 'data': None}


def normalize_name(name):
    """Normalize name for comparison: lowercase, strip, collapse spaces."""
    if not name:
        return ''
    name = name.strip().lower()
    name = re.sub(r'\s+', ' ', name)
    name = re.sub(r'[^a-z\s]', '', name)
    return name


def normalize_id_number(number):
    """Normalize Aadhaar/PAN number: strip, remove spaces and hyphens."""
    if not number:
        return ''
    number = number.strip()
    number = re.sub(r'[\s\-]', '', number)
    return number.upper()


def normalize_date(date_str):
    """Normalize date to DD-MM-YYYY format."""
    if not date_str:
        return ''
    date_str = date_str.strip()

    patterns = [
        (r'(\d{2})[/-](\d{2})[/-](\d{4})', lambda m: f"{m.group(1)}-{m.group(2)}-{m.group(3)}"),
        (r'(\d{4})[/-](\d{2})[/-](\d{2})', lambda m: f"{m.group(3)}-{m.group(2)}-{m.group(1)}"),
        (r'(\d{2})\.(\d{2})\.(\d{4})', lambda m: f"{m.group(1)}-{m.group(2)}-{m.group(3)}"),
    ]

    for pattern, formatter in patterns:
        m = re.search(pattern, date_str)
        if m:
            return formatter(m)

    return date_str.lower()


def normalize_address(address):
    """Normalize address for fuzzy comparison."""
    if not address:
        return ''
    addr = address.lower().strip()
    addr = re.sub(r'[,\s]+', ' ', addr)
    addr = re.sub(r'\b(s/o|d/o|w/o|son of|daughter of|wife of)\b', '', addr)
    addr = re.sub(r'\b(po|ps|dist|state|pin|pincode|taluk|tehsil|village|city|town)\b\.?', '', addr)
    addr = re.sub(r'\bandhra\s*pradesh\b', 'ap', addr)
    addr = re.sub(r'\btamil\s*nadu\b', 'tn', addr)
    addr = re.sub(r'\bkarnataka\b', 'ka', addr)
    addr = re.sub(r'\bkerala\b', 'kl', addr)
    addr = re.sub(r'\bmadhya\s*pradesh\b', 'mp', addr)
    addr = re.sub(r'\bwest\s*bengal\b', 'wb', addr)
    addr = re.sub(r'\bumar\s*pradesh\b', 'up', addr)
    addr = re.sub(r'\brajasthan\b', 'rj', addr)
    addr = re.sub(r'\bodisha\b', 'od', addr)
    addr = re.sub(r'\bchhattisgarh\b', 'cg', addr)
    addr = re.sub(r'\bjharkhand\b', 'jh', addr)
    addr = re.sub(r'\b uttarakhand\b', 'uk', addr)
    addr = re.sub(r'\bhimachal\s*pradesh\b', 'hp', addr)
    addr = re.sub(r'\bgoa\b', 'ga', addr)
    addr = re.sub(r'\bgujarat\b', 'gj', addr)
    addr = re.sub(r'\bmaharashtra\b', 'mh', addr)
    addr = re.sub(r'\bpunjab\b', 'pb', addr)
    addr = re.sub(r'\bharyana\b', 'hr', addr)
    addr = re.sub(r'\bassam\b', 'as', addr)
    addr = re.sub(r'\bmanipur\b', 'mn', addr)
    addr = re.sub(r'\bmeghalaya\b', 'ml', addr)
    addr = re.sub(r'\bnagaland\b', 'nl', addr)
    addr = re.sub(r'\bmizoram\b', 'mz', addr)
    addr = re.sub(r'\btripura\b', 'tr', addr)
    addr = re.sub(r'\bsikkim\b', 'sk', addr)
    addr = re.sub(r'\barunachal\s*pradesh\b', 'ar', addr)
    addr = re.sub(r'\bjammu\s*&?\s*kashmir\b', 'jk', addr)
    addr = re.sub(r'\bladakh\b', 'la', addr)
    addr = re.sub(r'\bchandigarh\b', 'ch', addr)
    addr = re.sub(r'\s+', ' ', addr).strip()
    return addr


def parse_aadhaar_qr(qr_data):
    """Parse Aadhaar QR code data to extract name, DOB, and Aadhaar number.

    Aadhaar QR codes may contain:
    - XML-like data with attributes (PrintLetterBarcodeData)
    - XML-like data with tags
    - Pipe-separated fields
    - Plain text with embedded numbers
    - URL with embedded data (e.g. https://uidai.gov.in/qr?data=...)
    - Base64-encoded JSON/XML
    """
    result = {'name': '', 'dob': '', 'aadhaar_number': '', 'gender': '', 'address': ''}

    if not qr_data:
        return result

    logger.info("[QR-PARSE-Aadhaar] raw_data (first 300): %s", qr_data[:300])

    if qr_data.startswith('http://') or qr_data.startswith('https://'):
        try:
            from urllib.parse import urlparse, parse_qs
            parsed_url = urlparse(qr_data)
            params = parse_qs(parsed_url.query)
            for key in ('data', 'qr', 'content', 'payload'):
                if key in params:
                    embedded = params[key][0]
                    try:
                        decoded = base64.b64decode(embedded).decode('utf-8', errors='ignore')
                        qr_data = decoded
                        logger.info("[QR-PARSE-Aadhaar] decoded URL param '%s', new data (first 300): %s", key, qr_data[:300])
                        break
                    except Exception:
                        qr_data = embedded
                        break
        except Exception as e:
            logger.warning("[QR-PARSE-Aadhaar] URL parse failed: %s", e)

    try:
        if qr_data.startswith('{') or qr_data.startswith('['):
            parsed = json.loads(qr_data)
            if isinstance(parsed, dict):
                result['name'] = parsed.get('name', parsed.get('Name', parsed.get('NAME', '')))
                result['dob'] = parsed.get('dob', parsed.get('DOB', parsed.get('dateOfBirth', parsed.get('dob', ''))))
                result['aadhaar_number'] = parsed.get('aadhaarNumber', parsed.get('uid', parsed.get('aadhaar', parsed.get('number', ''))))
                if result['aadhaar_number']:
                    result['aadhaar_number'] = normalize_id_number(str(result['aadhaar_number']))
                logger.info("[QR-PARSE-Aadhaar] JSON parsed: name=%s dob=%s uid=%s", bool(result['name']), bool(result['dob']), bool(result['aadhaar_number']))
                return result
    except (json.JSONDecodeError, TypeError):
        pass

    plc_match = re.search(r'PrintLetterBarcodeData\b([^>]*)', qr_data, re.IGNORECASE | re.DOTALL)
    if plc_match:
        attrs_str = plc_match.group(1)
        logger.info("[QR-PARSE-Aadhaar] PrintLetterBarcodeData attrs: %s", attrs_str[:200])
        name_m = re.search(r'\bname\s*=\s*["\']([^"\']+)["\']', attrs_str, re.IGNORECASE)
        if name_m:
            result['name'] = name_m.group(1).strip()
        uid_m = re.search(r'\buid\s*=\s*["\'](\d{12})["\']', attrs_str, re.IGNORECASE)
        if uid_m:
            result['aadhaar_number'] = uid_m.group(1)
        dob_m = re.search(r'\bdob\s*=\s*["\']([^"\']+)["\']', attrs_str, re.IGNORECASE)
        if dob_m:
            result['dob'] = dob_m.group(1).strip()
        gender_m = re.search(r'\bgender\s*=\s*["\']([MF])["\']', attrs_str, re.IGNORECASE)
        if gender_m:
            result['gender'] = 'Male' if gender_m.group(1).upper() == 'M' else 'Female'
        addr_m = re.search(r'\b(?:address|house|street|loc|vtc|dist|state|pc)\s*=\s*["\']([^"\']+)["\']', attrs_str, re.IGNORECASE)
        if addr_m:
            result['address'] = addr_m.group(1).strip()
        if any(result.values()):
            logger.info("[QR-PARSE-Aadhaar] PLC parsed: name=%s dob=%s uid=%s", bool(result['name']), bool(result['dob']), bool(result['aadhaar_number']))
            return result
    if not result['name']:
        name_attr_match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', qr_data, re.IGNORECASE)
        if name_attr_match:
            result['name'] = name_attr_match.group(1).strip()

    uid_match = re.search(r'<uid[^>]*>(\d{12})</uid>', qr_data, re.IGNORECASE)
    if uid_match:
        result['aadhaar_number'] = uid_match.group(1)

    if not result['aadhaar_number']:
        uid_attr_match = re.search(r'uid\s*=\s*["\']?(\d{12})["\']?', qr_data, re.IGNORECASE)
        if uid_attr_match:
            result['aadhaar_number'] = uid_attr_match.group(1)

    if not result['aadhaar_number']:
        uid_match = re.search(r'\b(\d{4}\s?\d{4}\s?\d{4})\b', qr_data)
        if uid_match:
            candidate = uid_match.group(1)
            candidate = re.sub(r'\s', '', candidate)
            if len(candidate) == 12:
                result['aadhaar_number'] = candidate

    if not result['name']:
        name_match = re.search(r'<name[^>]*>([^<]+)</name>', qr_data, re.IGNORECASE)
        if name_match:
            result['name'] = name_match.group(1).strip()

    if not result['name']:
        name_match = re.search(r'<naam[^>]*>([^<]+)</naam>', qr_data, re.IGNORECASE)
        if name_match:
            result['name'] = name_match.group(1).strip()

    # XML attribute format: dob="..."
    if not result['dob']:
        dob_attr_match = re.search(r'dob\s*=\s*["\']([^"\']+)["\']', qr_data, re.IGNORECASE)
        if dob_attr_match:
            result['dob'] = dob_attr_match.group(1).strip()

    dob_match = re.search(r'<dob[^>]*>([^<]+)</dob>', qr_data, re.IGNORECASE)
    if dob_match:
        result['dob'] = dob_match.group(1).strip()

    if not result['dob']:
        dob_match = re.search(r'<dpob[^>]*>([^<]+)</dpob>', qr_data, re.IGNORECASE)
        if dob_match:
            result['dob'] = dob_match.group(1).strip()

    if not result['dob']:
        lines = qr_data.split('\n')
        for line in lines:
            label_m = re.match(r'^dob\s*:\s*(.+)', line, re.IGNORECASE)
            if label_m:
                result['dob'] = label_m.group(1).strip()
                break

    if not result['dob']:
        dob_match = re.search(r'\b(\d{2}[/-]\d{2}[/-]\d{4})\b', qr_data)
        if dob_match:
            result['dob'] = dob_match.group(1)

    if not result['gender']:
        lines = qr_data.split('\n')
        for line in lines:
            label_m = re.match(r'^gender\s*:\s*(.+)', line, re.IGNORECASE)
            if label_m:
                val = label_m.group(1).strip().lower()
                if 'male' in val and 'female' not in val:
                    result['gender'] = 'Male'
                elif 'female' in val:
                    result['gender'] = 'Female'
                break

    if not result['name']:
        parts = qr_data.split('|')
        for part in parts:
            part = part.strip()
            if re.match(r'^[A-Za-z\s]+$', part) and len(part) > 3:
                result['name'] = part
                break

    if not result['name']:
        lines = qr_data.split('\n')
        for line in lines:
            line = line.strip()
            label_m = re.match(r'^name\s*:\s*(.+)', line, re.IGNORECASE)
            if label_m:
                val = label_m.group(1).strip()
                if re.match(r'^[A-Za-z\s]+$', val) and len(val) > 3:
                    result['name'] = val
                    break
            if re.match(r'^[A-Za-z\s]+$', line) and len(line) > 3:
                result['name'] = line
                break

    if not result['aadhaar_number']:
        all_numbers = re.findall(r'\b\d{12}\b', qr_data)
        for num in all_numbers:
            if num and len(num) == 12:
                result['aadhaar_number'] = num
                break

    if not result['dob']:
        all_dates = re.findall(r'\b(\d{2}[/-]\d{2}[/-]\d{4})\b', qr_data)
        if all_dates:
            result['dob'] = all_dates[0]

    if not result['address']:
        lines = qr_data.split('\n')
        for line in lines:
            label_m = re.match(r'^address\s*:\s*(.+)', line, re.IGNORECASE)
            if label_m:
                result['address'] = label_m.group(1).strip()
                break

    logger.info("[QR-PARSE-Aadhaar] name=%s dob=%s aadhaar=%s",
                bool(result['name']), bool(result['dob']), bool(result['aadhaar_number']))
    return result


def parse_pan_qr(qr_data):
    """Parse PAN QR code data to extract name, DOB, and PAN number.

    PAN QR codes typically contain:
    - XML-like data with tags or attributes
    - JSON data
    - Pipe-separated or comma-separated fields
    - Plain text with PAN pattern
    """
    result = {'name': '', 'dob': '', 'pan_number': ''}

    if not qr_data:
        return result

    try:
        if qr_data.startswith('{') or qr_data.startswith('['):
            parsed = json.loads(qr_data)
            if isinstance(parsed, dict):
                result['name'] = parsed.get('name', parsed.get('Name', parsed.get('NAME', '')))
                result['dob'] = parsed.get('dob', parsed.get('DOB', parsed.get('dateOfBirth', '')))
                result['pan_number'] = parsed.get('panNumber', parsed.get('pan', parsed.get('PAN', parsed.get('number', ''))))
                if result['pan_number']:
                    result['pan_number'] = normalize_id_number(str(result['pan_number']))
                return result
    except (json.JSONDecodeError, TypeError):
        pass

    # XML attribute format: pan="ABCPM1234D" or name="ARJUN MEHRA"
    pan_attr_match = re.search(r'pan\s*=\s*["\']([A-Z0-9]{10})["\']', qr_data, re.IGNORECASE)
    if pan_attr_match:
        result['pan_number'] = pan_attr_match.group(1).upper()

    if not result['pan_number']:
        pan_match = re.search(r'\b([A-Z]{5}\d{4}[A-Z])\b', qr_data)
        if pan_match:
            result['pan_number'] = pan_match.group(1)

    if not result['pan_number']:
        pan_match = re.search(r'<pan[^>]*>([A-Z0-9]{10})</pan>', qr_data, re.IGNORECASE)
        if pan_match:
            result['pan_number'] = pan_match.group(1).upper()

    # XML attribute format: name="..."
    name_attr_match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', qr_data, re.IGNORECASE)
    if name_attr_match:
        result['name'] = name_attr_match.group(1).strip()

    if not result['name']:
        name_match = re.search(r'<name[^>]*>([^<]+)</name>', qr_data, re.IGNORECASE)
        if name_match:
            result['name'] = name_match.group(1).strip()

    if not result['name']:
        name_match = re.search(r'<naam[^>]*>([^<]+)</naam>', qr_data, re.IGNORECASE)
        if name_match:
            result['name'] = name_match.group(1).strip()

    # XML attribute format: dob="..."
    if not result['dob']:
        dob_attr_match = re.search(r'dob\s*=\s*["\']([^"\']+)["\']', qr_data, re.IGNORECASE)
        if dob_attr_match:
            result['dob'] = dob_attr_match.group(1).strip()

    dob_match = re.search(r'<dob[^>]*>([^<]+)</dob>', qr_data, re.IGNORECASE)
    if dob_match:
        result['dob'] = dob_match.group(1).strip()

    if not result['dob']:
        dob_match = re.search(r'\b(\d{2}[/-]\d{2}[/-]\d{4})\b', qr_data)
        if dob_match:
            result['dob'] = dob_match.group(1)

    if not result['name']:
        parts = qr_data.split('|')
        for part in parts:
            part = part.strip()
            if re.match(r'^[A-Za-z\s]+$', part) and len(part) > 3:
                result['name'] = part
                break

    if not result['name']:
        lines = qr_data.split('\n')
        for line in lines:
            line = line.strip()
            if re.match(r'^[A-Za-z\s]+$', line) and len(line) > 3:
                result['name'] = line
                break

    if not result['dob']:
        all_dates = re.findall(r'\b(\d{2}[/-]\d{2}[/-]\d{4})\b', qr_data)
        if all_dates:
            result['dob'] = all_dates[0]

    logger.info("[QR-PARSE-PAN] name=%s dob=%s pan=%s",
                bool(result['name']), bool(result['dob']), bool(result['pan_number']))
    return result


def compare_fields(ocr_data, qr_data, doc_type):
    """Compare OCR and QR extracted fields.

    Args:
        ocr_data: dict with OCR-extracted fields
        qr_data: dict with QR-decoded fields
        doc_type: 'aadhaar' or 'pan'

    Returns:
        dict with comparison results
    """
    results = {}
    match_count = 0
    total_fields = 0

    fields_to_compare = [
        ('name', 'name', 'Name'),
        ('dob', 'dob', 'Date of Birth'),
        ('aadhaar_number', 'aadhaar_number', 'Aadhaar Number'),
        ('pan_number', 'pan_number', 'PAN Number'),
        ('address', 'address', 'Address'),
    ]

    for ocr_key, qr_key, label in fields_to_compare:
        ocr_val = ocr_data.get(ocr_key, '')
        qr_val = qr_data.get(qr_key, '')

        if not ocr_val and ocr_key == 'aadhaar_number':
            ocr_val = ocr_data.get('id_number', '')
        if not ocr_val and ocr_key == 'pan_number':
            ocr_val = ocr_data.get('id_number', '') or ocr_data.get('pan_number', '')

        total_fields += 1

        if ocr_key == 'name':
            norm_ocr = normalize_name(str(ocr_val))
            norm_qr = normalize_name(str(qr_val))
        elif ocr_key == 'dob':
            norm_ocr = normalize_date(str(ocr_val))
            norm_qr = normalize_date(str(qr_val))
        elif ocr_key == 'address':
            norm_ocr = normalize_address(str(ocr_val))
            norm_qr = normalize_address(str(qr_val))
        else:
            norm_ocr = normalize_id_number(str(ocr_val))
            norm_qr = normalize_id_number(str(qr_val))

        matched = bool(norm_ocr and norm_qr and norm_ocr == norm_qr)
        if matched:
            match_count += 1

        results[ocr_key] = {
            'ocr': str(ocr_val) if ocr_val else '',
            'qr': str(qr_val) if qr_val else '',
            'match': matched
        }

    match_percentage = round((match_count / total_fields * 100) if total_fields > 0 else 0, 1)

    if total_fields > 0 and match_count == total_fields:
        status = 'Passed'
    elif total_fields > 0:
        status = 'Failed'
    else:
        status = 'Skipped'

    return {
        'results': results,
        'match_count': match_count,
        'total_fields': total_fields,
        'match_percentage': match_percentage,
        'verification_status': status
    }


def verify_qr(image_data, ocr_data, doc_type='aadhaar'):
    """Main entry point: detect QR code, parse data, and compare with OCR.

    Args:
        image_data: base64 string or bytes of the document image
        ocr_data: dict with OCR-extracted fields (from ocr_extraction.py)
        doc_type: 'aadhaar' or 'pan'

    Returns:
        dict with full verification results
    """
    start = time.time()

    qr_result = detect_qr_code(image_data)

    if not qr_result['detected'] or not qr_result['data']:
        return {
            'qr_detected': False,
            'verification_status': 'Skipped',
            'message': 'QR code not found or unreadable. Continue remaining KYC verification.',
            'match_percentage': 0,
            'results': {},
            'processing_time_ms': round((time.time() - start) * 1000, 1)
        }

    qr_raw = qr_result['data']

    if doc_type.lower() == 'aadhaar':
        parsed_qr = parse_aadhaar_qr(qr_raw)
    elif doc_type.lower() == 'pan':
        parsed_qr = parse_pan_qr(qr_raw)
    else:
        return {
            'qr_detected': True,
            'verification_status': 'Skipped',
            'message': f'Unsupported document type: {doc_type}',
            'match_percentage': 0,
            'results': {},
            'processing_time_ms': round((time.time() - start) * 1000, 1)
        }

    if not any(parsed_qr.values()):
        return {
            'qr_detected': True,
            'verification_status': 'Skipped',
            'message': 'QR code detected but could not extract valid fields.',
            'match_percentage': 0,
            'results': {},
            'qr_raw_data': qr_raw[:500],
            'processing_time_ms': round((time.time() - start) * 1000, 1)
        }

    comparison = compare_fields(ocr_data, parsed_qr, doc_type)

    elapsed = round((time.time() - start) * 1000, 1)

    return {
        'qr_detected': True,
        'verification_status': comparison['verification_status'],
        'match_percentage': comparison['match_percentage'],
        'results': comparison['results'],
        'document_type': doc_type.capitalize(),
        'qr_raw_data': qr_raw[:500],
        'processing_time_ms': elapsed
    }


if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 3:
        print("Usage: python qr_verification.py <image_path> <ocr_json_path> [aadhaar|pan]")
        sys.exit(1)

    image_path = sys.argv[1]
    ocr_json_path = sys.argv[2]
    doc_type = sys.argv[3] if len(sys.argv) > 3 else 'aadhaar'

    with open(image_path, 'rb') as f:
        image_data = f.read()

    with open(ocr_json_path, 'r') as f:
        ocr_data = json.load(f)

    result = verify_qr(image_data, ocr_data, doc_type)
    print(json.dumps(result, indent=2, ensure_ascii=False))


# ============================================================
# QR FACE vs CARD FACE COMPARISON
# ============================================================

def compare_qr_face_with_card_face(card_image_data, face_image_data=None):
    """Compare face from QR code / verification data against face on ID card.

    Uses OpenCV Haar cascade for face detection and cosine similarity
    of histogram features for comparison.

    Args:
        card_image_data: base64 or bytes of the ID card image (Aadhaar/PAN)
        face_image_data: base64 or bytes of the face image from QR/verification data (optional)

    Returns:
        dict with match_percentage, confidence, status, tampering_flag
    """
    start = time.time()

    try:
        card_img = _decode_image(card_image_data)
    except Exception as e:
        return {
            'match_percentage': 0,
            'confidence': 0,
            'status': 'ERROR',
            'tampering_flag': False,
            'message': f'Failed to decode card image: {e}',
            'processing_time_ms': round((time.time() - start) * 1000, 1),
        }

    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

    card_gray = cv2.cvtColor(card_img, cv2.COLOR_BGR2GRAY)
    card_faces = cascade.detectMultiScale(card_gray, 1.1, 5, minSize=(60, 60))

    if len(card_faces) == 0:
        return {
            'match_percentage': 0,
            'confidence': 0,
            'status': 'NO_FACE_ON_CARD',
            'tampering_flag': True,
            'message': 'No face detected on the ID card',
            'processing_time_ms': round((time.time() - start) * 1000, 1),
        }

    x, y, w, h = max(card_faces, key=lambda r: r[2] * r[3])
    card_face = card_img[y:y+h, x:x+w]

    if face_image_data is None:
        return {
            'match_percentage': 0,
            'confidence': 0,
            'status': 'NO_QR_FACE',
            'tampering_flag': False,
            'message': 'No face image from QR code available for comparison',
            'processing_time_ms': round((time.time() - start) * 1000, 1),
        }

    try:
        face_img = _decode_image(face_image_data)
    except Exception as e:
        return {
            'match_percentage': 0,
            'confidence': 0,
            'status': 'ERROR',
            'tampering_flag': False,
            'message': f'Failed to decode face image: {e}',
            'processing_time_ms': round((time.time() - start) * 1000, 1),
        }

    face_gray = cv2.cvtColor(face_img, cv2.COLOR_BGR2GRAY)
    qr_faces = cascade.detectMultiScale(face_gray, 1.1, 5, minSize=(60, 60))

    if len(qr_faces) == 0:
        return {
            'match_percentage': 0,
            'confidence': 0,
            'status': 'NO_FACE_IN_QR',
            'tampering_flag': True,
            'message': 'No face detected in QR verification image',
            'processing_time_ms': round((time.time() - start) * 1000, 1),
        }

    fx, fy, fw, fh = max(qr_faces, key=lambda r: r[2] * r[3])
    qr_face = face_img[fy:fy+fh, fx:fx+fw]

    card_face_resized = cv2.resize(card_face, (128, 128))
    qr_face_resized = cv2.resize(qr_face, (128, 128))

    card_hist = cv2.calcHist([card_face_resized], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
    qr_hist = cv2.calcHist([qr_face_resized], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
    cv2.normalize(card_hist, card_hist)
    cv2.normalize(qr_hist, qr_hist)
    hist_similarity = cv2.compareHist(card_hist, qr_hist, cv2.HISTCMP_CORREL)

    card_gray_resized = cv2.resize(card_face_resized, (64, 64)).flatten().astype(np.float32)
    qr_gray_resized = cv2.resize(qr_face_resized, (64, 64)).flatten().astype(np.float32)
    cos_sim = float(np.dot(card_gray_resized, qr_gray_resized) / (np.linalg.norm(card_gray_resized) * np.linalg.norm(qr_gray_resized) + 1e-6))

    match_percentage = round((hist_similarity * 0.6 + max(0, cos_sim) * 0.4) * 100, 2)
    confidence = round(min(1.0, match_percentage / 100.0), 4)

    THRESHOLD = 50.0
    tampering_flag = match_percentage < THRESHOLD

    if match_percentage >= 80:
        status = 'MATCH'
    elif match_percentage >= 50:
        status = 'PARTIAL_MATCH'
    else:
        status = 'NO_MATCH'

    elapsed = round((time.time() - start) * 1000, 1)

    return {
        'match_percentage': match_percentage,
        'confidence': confidence,
        'status': status,
        'tampering_flag': tampering_flag,
        'message': f'Face comparison: {status} ({match_percentage:.1f}%)',
        'details': {
            'histogram_similarity': round(hist_similarity, 4),
            'cosine_similarity': round(cos_sim, 4),
            'card_face_detected': True,
            'qr_face_detected': True,
        },
        'processing_time_ms': elapsed,
    }
