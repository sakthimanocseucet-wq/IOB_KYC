"""
OCR Extraction for Aadhaar/PAN cards using RapidOCR (ONNX Runtime).

Aadhaar card layouts:
  Side-by-side: LEFT=Front (Name, DOB, Gender), RIGHT=Back (Address)
  Top-bottom:   TOP=Front (Name, DOB, Gender), BOTTOM=Back (Address)
"""

from rapidocr_onnxruntime import RapidOCR
import cv2
import numpy as np
import re
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

ocr_engine = None


def get_ocr():
    global ocr_engine
    if ocr_engine is None:
        ocr_engine = RapidOCR()
    return ocr_engine


def _clean(w):
    return re.sub(r'[^A-Za-z]', '', w)


def _box_pts(box):
    pts = []
    try:
        for p in box:
            if isinstance(p, (list, tuple)) and len(p) >= 2:
                pts.append((float(p[0]), float(p[1])))
        if len(pts) >= 3:
            return pts
    except Exception:
        pass
    return [(0, 0), (100, 0), (100, 100), (0, 100)]


def _is_date_text(text):
    m = re.search(r'\b(\d{2}[/-]\d{2}[/-]\d{4})\b', text)
    if m:
        parts = re.split(r'[/-]', m.group(1))
        if len(parts) == 3:
            d, mo, y = int(parts[0]), int(parts[1]), int(parts[2])
            return 1 <= d <= 31 and 1 <= mo <= 12 and 1900 <= y <= 2030
    return False



def ocr_image(image_bytes, doc_type='AADHAAR'):
    engine = get_ocr()
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return {'success': False, 'error': 'Invalid image data'}

    h, w = img.shape[:2]
    if max(h, w) > 2000:
        scale = 2000 / max(h, w)
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        h, w = img.shape[:2]

    result, elapse = engine(img)

    items = []
    if result:
        for line in result:
            box, text, conf = line
            text = text.strip()
            if not text or len(text) < 2:
                continue
            pts = box if isinstance(box, (list, np.ndarray)) else _box_pts(box)
            xs = [float(p[0]) for p in pts]
            ys = [float(p[1]) for p in pts]
            items.append({
                'text': text,
                'conf': float(conf) if conf else 0.0,
                'cx': (min(xs) + max(xs)) / 2,
                'cy': (min(ys) + max(ys)) / 2,
            })

    items.sort(key=lambda x: x['cy'])

    all_text = ' '.join(it['text'] for it in items)
    all_text = re.sub(r'[\x00-\x1f\x7f]', ' ', all_text)
    all_text = re.sub(r'\s{2,}', ' ', all_text).strip()

    logger.info(f"OCR items count={len(items)}")
    for it in items:
        logger.info(f"OCR item: text='{it['text'][:80]}', cy={it['cy']:.1f}, cx={it['cx']:.1f}")

    mid_x = w / 2
    mid_y = h / 2
    left_items = [it for it in items if it['cx'] < mid_x]
    right_items = [it for it in items if it['cx'] >= mid_x]
    top_items = [it for it in items if it['cy'] < mid_y]
    bottom_items = [it for it in items if it['cy'] >= mid_y]

    tl = sum(1 for it in items if it['cx'] < mid_x and it['cy'] < mid_y)
    tr = sum(1 for it in items if it['cx'] >= mid_x and it['cy'] < mid_y)
    bl = sum(1 for it in items if it['cx'] < mid_x and it['cy'] >= mid_y)
    br = sum(1 for it in items if it['cx'] >= mid_x and it['cy'] >= mid_y)

    top_balanced = tl > 0 and tr > 0 and max(tl, tr) / min(tl + 1, tr + 1) < 2.5
    bot_balanced = bl > 0 and br > 0 and max(bl, br) / min(bl + 1, br + 1) < 2.5
    is_vertical_layout = not (top_balanced and bot_balanced)
    debug = {
        'all_blocks': [{'text': it['text'], 'cy': round(it['cy'], 1), 'cx': round(it['cx'], 1),
                         'side': 'L' if it['cx'] < mid_x else 'R',
                         'half': 'TOP' if it['cy'] < mid_y else 'BOT'} for it in items],
        'total': len(items),
        'mid_x': round(mid_x, 0),
        'mid_y': round(mid_y, 0),
        'layout': 'vertical' if is_vertical_layout else 'horizontal',
    }

    details = {}
    if doc_type.upper() == 'AADHAAR':
        details = _extract_aadhaar(left_items, right_items, top_items, bottom_items,
                                   all_text, h, w, mid_x, mid_y, is_vertical_layout, debug)
    elif doc_type.upper() == 'PAN':
        details = _extract_pan(items, all_text, h, w, debug)
    else:
        return {'success': False, 'error': f'Unsupported doc_type: {doc_type}'}

    details['raw_text'] = all_text
    details['extracted_at'] = datetime.now().isoformat()
    details['ocr_method'] = 'rapidocr'
    details['debug'] = debug
    details['confidence'] = _calc_confidence(details, doc_type)
    return {'success': True, 'data': _sanitize(details)}


def _extract_aadhaar(left_items, right_items, top_items, bottom_items,
                     all_text, img_h, img_w, mid_x, mid_y, is_vertical, debug):
    details = {}

    if is_vertical:
        front_items = top_items
        back_items = bottom_items
    else:
        front_items = left_items
        back_items = right_items

    all_items = left_items + right_items

    aadhaar_num = None
    _DOB_SEP_RE = re.compile(r'\d{2}[.\-/]\d{2}[.\-/]\d{4}')

    def _is_valid_aadhaar(candidate):
        if len(candidate) != 12 or not candidate.isdigit():
            return False
        for i in range(len(candidate) - 7):
            window = candidate[i:i + 8]
            d1, d2 = int(window[:2]), int(window[2:4])
            d3 = int(window[4:8])
            if 1 <= d1 <= 31 and 1 <= d2 <= 12 and 1900 <= d3 <= 2030:
                return False
        return True

    def _strip_dob_digits(text):
        text = _DOB_SEP_RE.sub('', text)
        all_digits = re.sub(r'\D', '', text)
        if len(all_digits) >= 8:
            for start in range(len(all_digits) - 7):
                window = all_digits[start:start + 8]
                d1, d2 = int(window[:2]), int(window[2:4])
                d3 = int(window[4:8])
                if (1 <= d1 <= 31 and 1 <= d2 <= 12 and 1900 <= d3 <= 2030):
                    all_digits = all_digits[:start] + all_digits[start + 8:]
                    break
        return all_digits

    def _find_aadhaar_in(items_list):
        for it in items_list:
            d = re.sub(r'\D', '', it['text'])
            if _is_valid_aadhaar(d):
                return d
        # Combine nearby numeric items on same row
        numeric_items = [(it['cy'], it['cx'], re.sub(r'\D', '', it['text'])) for it in items_list if re.sub(r'\D', '', it['text'])]
        numeric_items.sort(key=lambda x: (round(x[0] / 5) * 5, x[1]))
        i = 0
        while i < len(numeric_items):
            combined = numeric_items[i][2]
            j = i + 1
            row_cy = round(numeric_items[i][0] / 5) * 5
            while j < len(numeric_items) and abs(round(numeric_items[j][0] / 5) * 5 - row_cy) < 10 and abs(numeric_items[j][1] - numeric_items[i][1]) < 200:
                combined += numeric_items[j][2]
                j += 1
            if len(combined) >= 8:
                for start in range(len(combined) - 7):
                    sub = combined[start:start + 12]
                    if len(sub) == 12 and _is_valid_aadhaar(sub):
                        return sub
            i = j
        for it in items_list:
            cleaned = _strip_dob_digits(it['text'])
            d = re.sub(r'\D', '', cleaned)
            if _is_valid_aadhaar(d):
                return d
            if len(d) > 12:
                for i in range(len(d) - 11):
                    sub = d[i:i + 12]
                    if _is_valid_aadhaar(sub):
                        return sub
        return None

    front_bottom = [it for it in front_items if it['cy'] >= mid_y * 0.6]
    aadhaar_num = _find_aadhaar_in(front_bottom)

    if not aadhaar_num:
        aadhaar_num = _find_aadhaar_in(front_items)

    if not aadhaar_num:
        aadhaar_num = _find_aadhaar_in(all_items)

    if not aadhaar_num:
        merged = ' '.join(it['text'] for it in all_items)
        cleaned = _strip_dob_digits(merged)
        all_digits = re.sub(r'\D', '', cleaned)
        for i in range(len(all_digits) - 11):
            sub = all_digits[i:i + 12]
            if _is_valid_aadhaar(sub):
                aadhaar_num = sub
                break

    if aadhaar_num and len(aadhaar_num) == 12:
        details['id_number'] = aadhaar_num
        details['id_type'] = 'AADHAAR'

    dob = None
    for it in all_items:
        m = re.search(r'(?:DOB|\u091c\u0928\u094d\u092e)\s*[:.]?\s*(\d{2}[/-]\d{2}[/-]\d{4})', it['text'], re.IGNORECASE)
        if m:
            dob = m.group(1).strip()
            break
    if not dob:
        for it in all_items:
            m = re.search(r'\b(\d{2}[/-]\d{2}[/-]\d{4})\b', it['text'])
            if m:
                parts = re.split(r'[/-]', m.group(1))
                if len(parts) == 3:
                    d, mo, y = int(parts[0]), int(parts[1]), int(parts[2])
                    if 1 <= d <= 31 and 1 <= mo <= 12 and 1900 <= y <= 2030:
                        dob = m.group(1).strip()
                        break
    if dob:
        details['dob'] = dob

    name = _extract_name(all_items)
    if name:
        details['name'] = name

    gender = None
    for it in all_items:
        t = it['text'].strip().upper()
        if t == 'MALE' or t == 'FEMALE' or t == 'OTHER':
            gender = t.title()
            break
    if not gender:
        for it in all_items:
            t = it['text'].strip().upper()
            if 'MALE' in t and 'FEMALE' not in t:
                gender = 'Male'
                break
            elif 'FEMALE' in t:
                gender = 'Female'
                break
    if gender:
        details['gender'] = gender

    details['address'] = ''
    details['address_components'] = {'full_address': '', 'house_number': '', 'street': '', 'locality': '',
                                      'city_or_village': '', 'district': '', 'state': '', 'pin_code': '', 'confidence_score': 0.0}

    debug['extracted_name'] = name
    debug['extracted_gender'] = gender
    debug['back_items_count'] = len(back_items)
    return details


def _extract_name(items):
    ABBREVIATIONS = {
        'SO', 'DO', 'WO', 'CO', 'S', 'D', 'W', 'C',
        'HT', 'HR', 'HP', 'PB', 'RJ', 'UP', 'MP', 'AP', 'TN', 'KA', 'KL',
        'MH', 'GJ', 'OR', 'WB', 'BR', 'JH', 'CG', 'TS', 'SK', 'MN',
        'ML', 'NL', 'TR', 'AS', 'GA', 'PY', 'CH', 'DL', 'JK', 'LD',
        'AN', 'DD', 'DN', 'TG', 'OD', 'WB',
        'PO', 'PS', 'SO', 'MO', 'BO', 'TO', 'SDO', 'DM', 'TEHSIL',
        'PIN', 'STD', 'ISD', 'FAX',
        'HNO', 'H', 'NO', 'N', 'ST', 'LN', 'MN', 'RD', 'PL', 'FL',
    }
    SKIP = {
        'GOVERNMENT', 'GOVT', 'GOVTOFINDIA', 'GOVERNMENTOFINDIA',
        'INDIA', 'UNIQUE', 'IDENTIFICATION', 'AUTHORITY',
        'ENROLMENT', 'ENROLLMENT', 'UIDAI', 'DOB', 'DATE', 'BIRTH', 'MALE',
        'FEMALE', 'GENDER', 'AADHAAR', 'AADHAR', 'VID', 'MOBILE', 'EMAIL',
        'SIGNATURE', 'SIGN', 'PHOTO', 'HERE', 'FRONT', 'BACK', 'SIDE',
        'GOVT', 'OF', 'THE', 'AND', 'TO', 'IS', 'IT', 'IN', 'AT', 'BY',
        'COMMISSIONER', 'SYSTEMS', 'BOX', 'FILING', 'NSDL', 'UNIT', 'FLOOR',
        'TOWER', 'PLOT', 'SURVEY', 'CARD', 'NUMBER', 'VALID', 'PERMANENT',
        'ACCOUNT', 'INCOME', 'TAX', 'DEPARTMENT', 'NAME', 'NAAM',
        'S/O', 'D/O', 'W/O', 'C/O', 'DIST', 'STATE',
        'TALUK', 'YEAR', 'BIRTH', 'WARD', 'BLOCK', 'VILLAGE', 'CITY',
        'POST', 'OFFICE', 'STATION', 'POLICE', 'COURT', 'ROAD', 'STREET',
        'LANE', 'NAGAR', 'COLONY', 'SOCIETY', 'BUILDING', 'APARTMENT',
        'FLAT', 'FLOOR', 'GROUND', 'TOWER', 'WING', 'SECTOR', 'PHASE',
        'ZONE', 'AREA', 'LOCALITY', 'NEAR', 'BEHIND', 'OPPOSITE',
    }
    SKIP.update(ABBREVIATIONS)
    SKIP_SUBSTR = ['GOVERNMENT', 'GOVTOFINDIA', 'IDENTIFICATION', 'AUTHORITY',
                   'ENROLMENT', 'ENROLLMENT', 'UIDAI', 'AADHAAR', 'AADHAR',
                   'UNIQUE', 'INDIA', 'AUTHORI', 'SIGNATURE', 'DEPARTMENT']

    def _has_devanagari(text):
        return any('\u0900' <= c <= '\u097F' for c in text)

    def _extract_english_words(text):
        eng = []
        for w in re.split(r'\s+', text):
            cleaned = re.sub(r'[^A-Za-z]', '', w)
            if cleaned and cleaned.isalpha():
                eng.append(cleaned.upper())
        return eng

    def _is_name_candidate(text):
        if not text or _has_devanagari(text):
            return False
        if re.search(r'\d', text):
            return False
        eng = _extract_english_words(text)
        if not eng:
            return False
        filtered = [w for w in eng if w not in SKIP]
        if not filtered:
            return False
        if len(filtered) == 1 and len(filtered[0]) >= 6:
            pass
        elif len(filtered) < 2:
            return False
        longest = max(len(w) for w in filtered)
        if longest < 3:
            return False
        for sub in SKIP_SUBSTR:
            combined = ' '.join(filtered)
            if sub in combined.upper():
                return False
        return True

    def _is_genuine_name(text):
        """Stricter check: at least one word >= 4 chars or two words >= 3 chars,
        or a single long word >= 6 chars (likely concatenated name)."""
        eng = _extract_english_words(text)
        filtered = [w for w in eng if w not in SKIP]
        if len(filtered) < 1:
            return False
        if len(filtered) == 1 and len(filtered[0]) >= 6:
            return True
        long_words = [w for w in filtered if len(w) >= 4]
        med_words = [w for w in filtered if len(w) >= 3]
        if long_words:
            return True
        if len(med_words) >= 2:
            return True
        return False

    def _try_name_after_label(label_item, all_sorted):
        idx = None
        for i, x in enumerate(all_sorted):
            if x is label_item:
                idx = i
                break
        if idx is None:
            return None
        label_cy = label_item['cy']
        for j in range(idx + 1, min(idx + 15, len(all_sorted))):
            nxt = all_sorted[j]
            if abs(nxt['cy'] - label_cy) > 400:
                break
            nxt_t = nxt['text'].strip()
            if not nxt_t:
                continue
            low = nxt_t.lower()
            if re.search(r'\b(name|naam|नाम)\b', low):
                continue
            if _has_devanagari(nxt_t):
                continue
            if re.search(r'\d', nxt_t):
                continue
            if _is_name_candidate(nxt_t) and _is_genuine_name(nxt_t):
                eng = _extract_english_words(nxt_t)
                filtered = [w for w in eng if w not in SKIP]
                if filtered:
                    return ' '.join(filtered)
        return None

    sorted_items = sorted(items, key=lambda x: (x['cy'], x['cx']))

    for it in sorted_items:
        t = it['text'].strip()
        low = t.lower()
        if re.search(r'\b(name|naam|नाम)\b', low):
            after = re.sub(r'\b(name|naam|नाम)\b', '', t, flags=re.IGNORECASE).strip()
            after = re.sub(r'^[/\s:.\-]+', '', after).strip()
            if after and _is_name_candidate(after) and _is_genuine_name(after):
                eng = _extract_english_words(after)
                filtered = [w for w in eng if w not in SKIP]
                if filtered:
                    return ' '.join(filtered)
            result = _try_name_after_label(it, sorted_items)
            if result:
                return result

    for it in sorted_items:
        t = it['text'].strip()
        if _is_name_candidate(t) and _is_genuine_name(t):
            eng = _extract_english_words(t)
            filtered = [w for w in eng if w not in SKIP]
            if len(filtered) >= 2:
                return ' '.join(filtered)

    for it in sorted_items:
        t = it['text'].strip()
        low = t.lower()
        if any(kw in low for kw in ['government', 'govt', 'india', 'aadhaar',
                'aadhar', 'unique', 'identification', 'authority', 'enrolment',
                'son', 'daughter', 'wife', 'father', 'husband']):
            continue
        if _has_devanagari(t):
            continue
        if re.search(r'\b(dob|date|birth|male|female|vid|sign|photo|s/o|d/o|w/o|c/o)\b', low):
            continue
        if _is_date_text(t):
            continue
        d = re.sub(r'\D', '', t)
        if len(d) >= 12:
            continue
        if _is_name_candidate(t) and _is_genuine_name(t):
            eng = _extract_english_words(t)
            filtered = [w for w in eng if w not in SKIP]
            if len(filtered) >= 2:
                return ' '.join(filtered)

    return ''


def _is_english_text(text):
    """Check if text is primarily English (not Hindi/Devanagari)."""
    if not text or not text.strip():
        return False
    devanagari_chars = sum(1 for c in text if '\u0900' <= c <= '\u097F')
    total_alpha = sum(1 for c in text if c.isalpha())
    if total_alpha == 0:
        return devanagari_chars == 0
    return devanagari_chars == 0


def _fix_ocr_errors(text):
    """Fix common OCR character confusion errors."""
    if not text:
        return text

    for _so_fix_old, _so_fix_new in [
        ('SIO', 'S/O'), ('DIO', 'D/O'), ('WIO', 'W/O'), ('CIO', 'C/O'),
        ('S O', 'S/O'), ('s o', 'S/O'), ('S o', 'S/O'), ('s O', 'S/O'),
        ('S  O', 'S/O'), ('s  o', 'S/O'),
        ('D O', 'D/O'), ('d o', 'D/O'),
        ('W O', 'W/O'), ('w o', 'W/O'),
        ('C O', 'C/O'), ('c o', 'C/O'),
    ]:
        text = text.replace(_so_fix_old, _so_fix_new)

    text = re.sub(r'(?<=[A-Za-z])\b0\b(?=[A-Za-z])', 'O', text)
    text = re.sub(r'\b0(?=[A-Za-z]{2,})', 'O', text)
    text = re.sub(r'(?<=[A-Za-z][A-Za-z])0\b', 'O', text)
    text = re.sub(r'(?<=\d)I(?=\d)', '1', text)
    text = re.sub(r'(?<=\d)l(?=\d)', '1', text)
    text = re.sub(r'(?<=\d)O(?=\d)', '0', text)
    text = re.sub(r'(?<=\d)o(?=\d)', '0', text)
    text = re.sub(r'(?<=[A-Za-z])1(?=[A-Za-z][A-Za-z][A-Za-z])', 'l', text)
    text = re.sub(r'(?<=[A-Za-z][A-Za-z][A-Za-z])1(?=[A-Za-z])', 'l', text)

    text = re.sub(r'(?<=[a-z])/(?=[a-z])', 'l', text)
    text = re.sub(r'(?<=[A-Z])/(?=[A-Z])', 'I', text)

    text = re.sub(r'\b(\d{1,3})\s+(\d{3})\s+(\d{4})\b', r'\1\2\3', text)

    return text


def _merge_split_lines(items):
    """Merge OCR items that belong to the same logical line based on Y proximity."""
    if not items:
        return []
    items.sort(key=lambda x: (x['cy'], x['cx']))
    merged = []
    current = dict(items[0])
    for item in items[1:]:
        if abs(item['cy'] - current['cy']) < 10:
            current['text'] += ' ' + item['text']
            current['raw'] = current.get('raw', '') + ' ' + item.get('raw', item['text'])
            current['cx'] = (current['cx'] + item['cx']) / 2
        else:
            merged.append(current)
            current = dict(item)
    merged.append(current)
    return merged


def _merge_split_lines_wide(items):
    """Merge OCR items with a wider Y threshold for address text blocks."""
    if not items:
        return []
    items.sort(key=lambda x: (x['cy'], x['cx']))
    merged = []
    current = dict(items[0])
    for item in items[1:]:
        if abs(item['cy'] - current['cy']) < 20:
            current['text'] += ' ' + item['text']
            current['raw'] = current.get('raw', '') + ' ' + item.get('raw', item['text'])
            current['cx'] = (current['cx'] + item['cx']) / 2
        else:
            merged.append(current)
            current = dict(item)
    merged.append(current)
    return merged


def _clean_ocr_text(text):
    """Clean OCR garbage from text."""
    text = re.sub(r'[^A-Za-z0-9\u0900-\u097F\s,/\-]', ' ', text)
    text = re.sub(r'\s{2,}', ' ', text).strip()
    return text


NON_ADDRESS_KEYWORDS = [
    r'government', r'govt', r'india', r'unique', r'identification', r'authority',
    r'enrolment', r'uidai', r'aadhaar', r'aadhar', r'vid',
    r'1947', r'helpline', r'help\s*uidai', r'www\.', r'\.in', r'\.com',
    r'dob', r'date\s*of\s*birth', r'blood\s*group', r'mobile',
    r'male', r'female', r'year\s*of\s*birth',
    r'govt\.?\s*of\s*india', r'income\s*tax',
    r'email', r'phone', r'contact', r'website', r'www', r'gov', r'help',
    r'\u0906\u0927\u093e\u0930', r'\u091c\u0938\u094d\u091f', r'\u092a\u0939\u093f\u0939\u093e\u0928',
]


def _extract_address(all_items, mid_x=None, img_w=None):
    """
    Extract postal address from OCR items (back side of Aadhaar).
    Finds English S/O or D/O marker, includes name before marker through PIN code.
    Skips Hindi text entirely to avoid confusion with Hindi S/O.
    """
    eng_items = []
    for it in all_items:
        t = it['text']
        cleaned = _clean_ocr_text(t)
        if not cleaned or len(cleaned) < 2:
            continue
        if not _is_english_text(t):
            continue
        has_alpha = any(c.isalpha() for c in cleaned)
        if has_alpha:
            eng_items.append({'text': cleaned, 'raw': t, 'cy': it['cy'], 'cx': it['cx']})

    eng_items = _merge_split_lines_wide(eng_items)
    eng_items.sort(key=lambda x: (x['cy'], x['cx']))

    eng_sdo = re.compile(
        r'\b(S\s*[/.]?\s*o|D\s*[/.]?\s*o|W\s*[/.]?\s*o|C\s*[/.]?\s*o)\b', re.IGNORECASE
    )

    start_item_idx = -1
    start_offset = 0

    for i, it in enumerate(eng_items):
        m = eng_sdo.search(it['text'])
        if m:
            start_item_idx = i
            start_offset = m.start()
            break

    if start_item_idx == -1:
        for i, it in enumerate(eng_items):
            m = re.search(r'Address\s*[:.\s,]*', it['text'], re.IGNORECASE)
            if m:
                start_item_idx = i
                start_offset = m.end()
                break

    if start_item_idx == -1:
        full_text = ' '.join(it['text'] for it in eng_items)
        pin_match = re.search(r'\b(\d{6})\b', full_text)
        if pin_match and len(full_text) > 10:
            start_item_idx = 0
            start_offset = 0

    if start_item_idx == -1:
        return {'full_address': '', 'house_number': '', 'street': '', 'locality': '',
                'city_or_village': '', 'district': '', 'state': '', 'pin_code': '', 'confidence_score': 0.0}

    address_parts = []
    for i in range(start_item_idx, len(eng_items)):
        it = eng_items[i]
        text = it['text']
        if i == start_item_idx:
            text = text[start_offset:].strip()
        if text:
            address_parts.append(text)

    address_text = ' '.join(address_parts)
    address_text = re.sub(r'[\xa0\u2000-\u200b\u202f\u205f\u3000]+', ' ', address_text)
    address_text = _fix_ocr_errors(address_text)

    for _so_fix_old, _so_fix_new in [
        ('SIO', 'S/O'), ('DIO', 'D/O'), ('WIO', 'W/O'), ('CIO', 'C/O'),
        ('S O', 'S/O'), ('s o', 'S/O'), ('S o', 'S/O'), ('s O', 'S/O'),
        ('S  O', 'S/O'), ('s  o', 'S/O'),
        ('D O', 'D/O'), ('d o', 'D/O'),
        ('W O', 'W/O'), ('w o', 'W/O'),
        ('C O', 'C/O'), ('c o', 'C/O'),
    ]:
        address_text = address_text.replace(_so_fix_old, _so_fix_new)
    address_text = re.sub(r'(S/O|D/O|W/O|C/O)(?=[A-Za-z])', r'\1 ', address_text)
    address_text = re.sub(r'^\s*/\s*(S/O|D/O|W/O|C/O)', r'\1', address_text)

    address_text = re.sub(r'\s*/\s*', ' ', address_text)
    address_text = re.sub(r'(?<=[a-zA-Z])\s*q\s*/?\s*(?=[a-zA-Z])', ' ', address_text, flags=re.IGNORECASE)
    address_text = re.sub(r'/\s*(Email|Mobile|Phone|Contact|Website|Help|Govt|Government)\b', r' \1', address_text, flags=re.IGNORECASE)
    address_text = re.sub(r'\b(Dist|District)\s*(?=[A-Z][a-z])', r'\1, ', address_text, flags=re.IGNORECASE)
    address_text = re.sub(r'\bAB\s*/\s*No\b', '', address_text, flags=re.IGNORECASE)

    address_text = re.sub(r'Tamil\s*Nadu', 'Tamil Nadu', address_text, flags=re.IGNORECASE)
    address_text = re.sub(r'Andhra\s*Pradesh', 'Andhra Pradesh', address_text, flags=re.IGNORECASE)
    address_text = re.sub(r'Uttar\s*Pradesh', 'Uttar Pradesh', address_text, flags=re.IGNORECASE)
    address_text = re.sub(r'West\s*Bengal', 'West Bengal', address_text, flags=re.IGNORECASE)
    address_text = re.sub(r'Rajasthan', 'Rajasthan', address_text, flags=re.IGNORECASE)
    address_text = re.sub(r'Karnataka', 'Karnataka', address_text, flags=re.IGNORECASE)
    address_text = re.sub(r'Gujarat', 'Gujarat', address_text, flags=re.IGNORECASE)
    address_text = re.sub(r'Maharashtra', 'Maharashtra', address_text, flags=re.IGNORECASE)
    address_text = re.sub(r'Kerala', 'Kerala', address_text, flags=re.IGNORECASE)
    address_text = re.sub(r'Punjab', 'Punjab', address_text, flags=re.IGNORECASE)
    address_text = re.sub(r'Bihar', 'Bihar', address_text, flags=re.IGNORECASE)
    address_text = re.sub(r'Odisha', 'Odisha', address_text, flags=re.IGNORECASE)
    address_text = re.sub(r'Chhattisgarh', 'Chhattisgarh', address_text, flags=re.IGNORECASE)
    address_text = re.sub(r'Jharkhand', 'Jharkhand', address_text, flags=re.IGNORECASE)
    address_text = re.sub(r'Assam', 'Assam', address_text, flags=re.IGNORECASE)
    address_text = re.sub(r'Goa', 'Goa', address_text, flags=re.IGNORECASE)

    address_text = re.sub(r'(\d)\s+(?=[A-Za-z])', r'\1, ', address_text)
    address_text = re.sub(r'(?<=\w)\s+(?=S/O|D/O|W/O|C/O)', ', ', address_text)
    address_text = re.sub(r'(Colony|Nagar|Society|Enclave|Vihar|Puram)\s+(?=[A-Z])', r'\1, ', address_text, flags=re.IGNORECASE)
    address_text = re.sub(r'(Coimbatore|Chennai|Bangalore|Mumbai|Delhi|Pune|Hyderabad)\s+(?=[A-Za-z])', r'\1, ', address_text, flags=re.IGNORECASE)
    address_text = re.sub(r',\s*,', ',', address_text)
    address_text = re.sub(r'\s+', ' ', address_text).strip()

    for kw in NON_ADDRESS_KEYWORDS:
        address_text = re.sub(r'\b' + kw + r'\b', '', address_text, flags=re.IGNORECASE)

    address_text = re.sub(r'\b\d{2}[/-]\d{2}[/-]\d{4}\b', '', address_text)
    address_text = re.sub(r'\b\d{10}\b', '', address_text)
    address_text = re.sub(r'\b(Blood\s*Group|Mobile\s*No|Gender|Male|Female|DOB|Date\s*of\s*Birth|Email|Phone|Contact|Website|Help)\b', '', address_text, flags=re.IGNORECASE)
    address_text = re.sub(r'[^A-Za-z0-9\u0900-\u097F\s,/\-]', ' ', address_text)
    address_text = re.sub(r'\s{2,}', ' ', address_text).strip()

    pin = ''
    pin_match = re.search(r'\b(\d{6})\b', address_text)
    if pin_match:
        pin = pin_match.group(1)
        address_text = address_text[:pin_match.start()].rstrip(',').strip()

    parts = [p.strip() for p in re.split(r',\s*', address_text) if p.strip()]

    def _is_garbage_part(part):
        words = part.split()
        if not words:
            return True
        clean_words = []
        for w in words:
            cleaned = re.sub(r'[^A-Za-z]', '', w)
            if not cleaned:
                continue
            if len(cleaned) < 2:
                continue
            if cleaned.upper() in ('Q', 'QQ', 'S', 'D', 'W', 'C'):
                continue
            clean_words.append(w)
        if not clean_words:
            return True
        if len(clean_words) < len(words) * 0.3:
            return True
        return False

    seen = set()
    deduped = []
    for p in parts:
        if _is_garbage_part(p):
            continue
        norm = re.sub(r'\s+', ' ', p.lower().strip())
        if norm and norm not in seen:
            seen.add(norm)
            deduped.append(p)

    full_address = ', '.join(deduped)
    full_address = re.sub(r'[\s\-]*\d{6}\s*$', '', full_address).rstrip(',').strip()
    if pin:
        full_address = full_address + ' - ' + pin

    full_address = re.sub(r',\s*,', ',', full_address)
    full_address = re.sub(r'^\s*,\s*', '', full_address)
    full_address = re.sub(r',\s*$', '', full_address)
    full_address = re.sub(r'\s{2,}', ' ', full_address).strip()

    result = _parse_address_components(full_address, pin)
    return result


INDIAN_STATES = [
    'ANDAMAN AND NICOBAR ISLANDS', 'ANDHRA PRADESH', 'ARUNACHAL PRADESH', 'ASSAM',
    'BIHAR', 'CHANDIGARH', 'CHHATTISGARH', 'DADRA AND NAGAR HAVELI', 'DAMAN AND DIU',
    'DELHI', 'GOA', 'GUJARAT', 'HARYANA', 'HIMACHAL PRADESH', 'JAMMU AND KASHMIR',
    'JHARKHAND', 'KARNATAKA', 'KERALA', 'LADAKH', 'LAKSHADWEEP', 'MADHYA PRADESH',
    'MAHARASHTRA', 'MANIPUR', 'MEGHALAYA', 'MIZORAM', 'NAGALAND', 'ODISHA',
    'PUDUCHERRY', 'PUNJAB', 'RAJASTHAN', 'SIKKIM', 'TAMIL NADU', 'TELANGANA',
    'TRIPURA', 'UTTAR PRADESH', 'UTTARAKHAND', 'WEST BENGAL',
]

INDIAN_STATES_SET = set(s.upper() for s in INDIAN_STATES)

STATE_PIN_MAP = {
    '11': 'DELHI', '12': 'HARYANA', '13': 'PUNJAB', '14': 'PUNJAB', '15': 'JAMMU AND KASHMIR',
    '16': 'PUNJAB', '17': 'HIMACHAL PRADESH', '18': 'JAMMU AND KASHMIR', '19': 'JAMMU AND KASHMIR',
    '20': 'UTTAR PRADESH', '21': 'UTTAR PRADESH', '22': 'UTTAR PRADESH', '23': 'UTTAR PRADESH',
    '24': 'UTTAR PRADESH', '25': 'UTTAR PRADESH', '26': 'UTTARAKHAND', '27': 'UTTAR PRADESH',
    '28': 'ANDHRA PRADESH',
    '30': 'RAJASTHAN', '31': 'RAJASTHAN', '32': 'RAJASTHAN', '33': 'RAJASTHAN', '34': 'RAJASTHAN',
    '36': 'GUJARAT', '37': 'GUJARAT', '38': 'GUJARAT', '39': 'GUJARAT',
    '40': 'MAHARASHTRA', '41': 'MAHARASHTRA', '42': 'MAHARASHTRA', '43': 'MAHARASHTRA',
    '44': 'MAHARASHTRA', '45': 'MADHYA PRADESH', '46': 'MADHYA PRADESH', '47': 'MADHYA PRADESH',
    '48': 'MADHYA PRADESH', '49': 'CHHATTISGARH',
    '50': 'TELANGANA', '51': 'ANDHRA PRADESH', '52': 'ANDHRA PRADESH', '53': 'ANDHRA PRADESH',
    '56': 'KARNATAKA', '57': 'KARNATAKA', '58': 'KARNATAKA', '59': 'KARNATAKA',
    '60': 'TAMIL NADU', '61': 'TAMIL NADU', '62': 'TAMIL NADU', '63': 'TAMIL NADU', '64': 'TAMIL NADU',
    '67': 'KERALA', '68': 'KERALA', '69': 'KERALA',
    '70': 'WEST BENGAL', '71': 'WEST BENGAL', '72': 'WEST BENGAL', '73': 'WEST BENGAL', '74': 'WEST BENGAL',
    '75': 'ODISHA', '76': 'ODISHA', '77': 'ODISHA',
    '78': 'ASSAM', '79': 'NORTHEASTERN STATES',
    '80': 'BIHAR', '81': 'BIHAR', '82': 'BIHAR', '83': 'BIHAR', '84': 'BIHAR', '85': 'JHARKHAND',
}

DISTRICT_KEYWORDS = [
    'DIST', 'DISTRICT', 'ZILLA', 'JILLA', 'JN', 'JILL', 'TALUKA', 'TEHSIL',
    'SUB-DIVISION', 'SUBDIVISION', 'BLOCK', 'MANDAL',
]

STATE_KEYWORDS = [
    'STATE', 'Rajya', 'Pradesh', ' Nadu',
]


def _parse_address_components(full_address, pin):
    result = {
        'full_address': full_address,
        'house_number': '',
        'street': '',
        'locality': '',
        'city_or_village': '',
        'district': '',
        'state': '',
        'pin_code': pin or '',
        'confidence_score': 0.0,
    }

    if not full_address:
        return result

    parts = [p.strip() for p in re.split(r',\s*', full_address) if p.strip()]

    state_from_pin = ''
    if pin and len(pin) == 6:
        prefix = pin[:2]
        state_from_pin = STATE_PIN_MAP.get(prefix, '')

    detected_state = ''
    for p in parts:
        upper = p.upper().strip()
        for s in INDIAN_STATES_SET:
            if s in upper or upper in s:
                detected_state = s
                break
        if not detected_state:
            for s in INDIAN_STATES:
                if s.lower() in p.lower():
                    detected_state = s.upper()
                    break
        if detected_state:
            break

    result['state'] = detected_state or state_from_pin

    detected_district = ''
    district_idx = -1
    for i, p in enumerate(parts):
        upper = p.upper().strip()
        for kw in DISTRICT_KEYWORDS:
            m = re.search(r'\b' + kw + r'\b', upper)
            if m:
                before = upper[:m.start()].strip().rstrip(',').strip()
                if before:
                    detected_district = before
                    district_idx = i
                    break
                after = upper[m.end():].strip().lstrip(':').strip()
                if after:
                    detected_district = after
                    district_idx = i
                    break
        if detected_district:
            break

    if not detected_district:
        state_idx = -1
        for i, p in enumerate(parts):
            if detected_state and detected_state.lower() in p.lower():
                state_idx = i
                break
        if state_idx > 0:
            candidate = parts[state_idx - 1].upper().strip()
            if len(candidate.split()) <= 3 and not re.search(r'\d{6}', candidate):
                detected_district = candidate
                district_idx = state_idx - 1

    result['district'] = detected_district

    address_parts = list(range(len(parts)))
    if district_idx >= 0 and district_idx in address_parts:
        address_parts.remove(district_idx)
    state_part_idx = -1
    for i, p in enumerate(parts):
        if detected_state and detected_state.lower() in p.lower():
            state_part_idx = i
            break
    if state_part_idx >= 0 and state_part_idx in address_parts:
        address_parts.remove(state_part_idx)

    house = ''
    street = ''
    locality = ''
    city = ''

    house_patterns = [
        r'(?:H\.?\s*No\.?|House\s*(?:No\.?|Number)|Flat\s*(?:No\.?|Number)|Door\s*(?:No\.?|Number)|House|Flat|Door)\s*[:.]?\s*(.+)',
        r'^(\d+[A-Za-z]?(?:\s*[-/]\s*\d+[A-Za-z]?)?)\s+',
    ]
    street_patterns = [
        r'(?:Street|St\.?|Road|Rd\.?|Lane|Ln\.?|Main\s*Road|Marg|Nagar|Colony|Phase)\s*[:.]?\s*(.*)',
    ]

    for idx in address_parts:
        p = parts[idx]
        upper = p.upper().strip()

        if not house:
            for pat in house_patterns:
                m = re.search(pat, upper, re.IGNORECASE)
                if m:
                    house = m.group(1).strip() if m.lastindex else m.group(0).strip()
                    break
            if not house and re.match(r'^\d+[A-Za-z]?\b', p.strip()):
                m = re.match(r'^(\d+[A-Za-z]?(?:\s*[-/]\s*\d+[A-Za-z]?)?)\s*(.*)', p.strip())
                if m:
                    house = m.group(1).strip()
                    rest = m.group(2).strip().rstrip(',').strip()
                    if rest and not street:
                        street = rest
                    continue

        if not street:
            for pat in street_patterns:
                m = re.search(pat, p, re.IGNORECASE)
                if m:
                    street = p.strip()
                    break

        if pin and re.search(r'\b' + re.escape(pin) + r'\b', p):
            city_part = re.sub(r'\b' + re.escape(pin) + r'\b', '', p).strip().rstrip(',').strip()
            city_part = re.sub(r'\s*-\s*$', '', city_part).strip()
            if city_part:
                city = city_part
            continue

        if detected_state and detected_state.lower() in p.lower():
            continue
        if detected_district and detected_district.lower() == p.upper().strip().lower():
            continue

        if not locality:
            locality = p.strip()
        elif not city:
            city = p.strip()

    result['house_number'] = house
    result['street'] = street
    result['locality'] = locality
    result['city_or_village'] = city

    found_fields = sum(1 for v in [result['full_address'], result['house_number'],
                                    result['street'], result['locality'], result['city_or_village'],
                                    result['district'], result['state'], result['pin_code']] if v)
    result['confidence_score'] = round(min(found_fields / 5.0, 1.0), 2)

    return result


def _merge_so(parts):
    result = []
    i = 0
    while i < len(parts):
        part = parts[i]
        if re.search(r'\bS/?[OI0]/?[OI0]?\b', part, re.IGNORECASE):
            name_text = re.sub(r'\bS/?[OI0]/?[OI0]?\b[:.\s,]*', '', part, flags=re.IGNORECASE).strip()
            name_text = re.sub(r'^(S/?[OI0]/?[OI0]?\s*)+', '', name_text, flags=re.IGNORECASE).strip()
            if name_text:
                clean_name = [_clean(w) for w in name_text.split() if _clean(w)]
                if (clean_name and all(_clean(w).isalpha() and len(_clean(w)) > 1 for w in clean_name)
                        and not all(len(_clean(w)) <= 2 for w in clean_name)):
                    result.append('S/O ' + name_text)
                    i += 1
                    continue
            for j in range(i + 1, min(i + 4, len(parts))):
                next_part = parts[j].strip()
                next_part = re.sub(r'\bS/?[OI0]/?[OI0]?\b', '', next_part, flags=re.IGNORECASE).strip()
                if re.match(r'^\d{1,4}$', next_part):
                    result.append(parts[j].strip())
                    i = j + 1
                    break
                elif next_part:
                    clean_next = [_clean(w) for w in next_part.split() if _clean(w)]
                    if clean_next and all(_clean(w).isalpha() and len(_clean(w)) > 1 for w in clean_next):
                        result.append('S/O ' + next_part)
                        i = j + 1
                        break
            else:
                i += 1
            continue
        elif re.search(r'\bD/?[OI0]/?[OI0]?\b', part, re.IGNORECASE):
            name_text = re.sub(r'\bD/?[OI0]/?[OI0]?\b[:.\s,]*', '', part, flags=re.IGNORECASE).strip()
            if name_text:
                result.append('D/O ' + name_text)
            i += 1
            continue
        elif re.search(r'\bW/?[OI0]/?[OI0]?\b', part, re.IGNORECASE):
            name_text = re.sub(r'\bW/?[OI0]/?[OI0]?\b[:.\s,]*', '', part, flags=re.IGNORECASE).strip()
            if name_text:
                result.append('W/O ' + name_text)
            i += 1
            continue
        else:
            result.append(part.strip())
        i += 1
    return result


def _extract_pan(items, all_text, img_h, img_w, debug):
    details = {}

    def _find_pan_in_text(text):
        fixed = _fix_ocr_errors(text)
        m = re.search(r'\b([A-Z]{5}\d{4}[A-Z])\b', fixed)
        if m:
            return m.group(1).strip()
        m = re.search(r'\b([A-Z]{5}\d{4}[A-Z])\b', text)
        if m:
            return m.group(1).strip()
        return None

    for it in items:
        pan = _find_pan_in_text(it['text'])
        if pan:
            details['id_number'] = pan
            details['id_type'] = 'PAN'
            break

    if 'id_number' not in details:
        fixed_all = _fix_ocr_errors(all_text)
        m = re.search(r'\b([A-Z]{5}\d{4}[A-Z])\b', fixed_all)
        if m:
            details['id_number'] = m.group(1).strip()
            details['id_type'] = 'PAN'

    if 'id_number' not in details:
        for it in items:
            cleaned = re.sub(r'[^A-Za-z0-9]', '', it['text']).upper()
            fixed = _fix_ocr_errors(cleaned)
            m = re.search(r'([A-Z]{5}\d{4}[A-Z])', fixed)
            if m:
                details['id_number'] = m.group(1).strip()
                details['id_type'] = 'PAN'
                break

    for it in items:
        m = re.search(r'(?:DOB)\s*[:.]?\s*(\d{2}[/-]\d{2}[/-]\d{4})', it['text'], re.IGNORECASE)
        if m:
            details['dob'] = m.group(1).strip()
            break
    if 'dob' not in details:
        for it in items:
            m = re.search(r'\b(\d{2}[/-]\d{2}[/-]\d{4})\b', it['text'])
            if m:
                parts = re.split(r'[/-]', m.group(1))
                if len(parts) == 3:
                    d, mo, y = int(parts[0]), int(parts[1]), int(parts[2])
                    if 1 <= d <= 31 and 1 <= mo <= 12 and 1900 <= y <= 2030:
                        details['dob'] = m.group(1).strip()
                        break

    pan_skip = {
        'INCOME', 'TAX', 'DEPARTMENT', 'GOVT', 'GOVERNMENT', 'PERMANENT',
        'ACCOUNT', 'NUMBER', 'FATHER', 'MOTHER', 'DOB', 'DATE', 'BIRTH',
        'SIGNATURE', 'INDIA', 'CARD', 'OF', 'THE', 'AND', 'TO', 'IS', 'IT',
        'FRONT', 'BACK', 'SIDE', 'LOST', 'FOUND', 'RETURN', 'INFORM',
        'VALID', 'OFFENCE', 'MISUSE', 'COMMISSIONER', 'SYSTEMS', 'BOX',
        'FILING', 'NSDL', 'UNIT', 'FLOOR', 'TOWER', 'PLOT', 'SURVEY',
    }
    pan_skip_patterns = [
        r'\b(front\s*side|back\s*side)\b',
        r'\b(income\s*tax|tax\s*department)\b',
        r'\b(govt\.?\s*of\s*india)\b',
        r'\b(permanent\s*account)\b',
        r'\b(card)\b',
        r'\b(this\s*card)\b',
        r'\b(lost|found|return|inform)\b',
        r'\b(valid|offence|misuse)\b',
        r'\b(commissioner|systems|nsdl)\b',
        r'\b(indian)\b',
    ]

    pan_candidates = []

    def is_good_pan_name(cw):
        if len(cw) < 2 or len(cw) > 4:
            return False
        for w in cw:
            if len(w) <= 1 or not w.isalpha():
                return False
            if not w[0].isupper():
                return False
        return not ({w.upper() for w in cw} & pan_skip)

    def _try_split_concatenated(text):
        """Try to split concatenated names like RAMESHKUMAR -> RAMESH KUMAR."""
        cleaned = re.sub(r'[^A-Za-z]', '', text)
        if not cleaned or len(cleaned) < 4:
            return None
        common_parts = [
            'KUMAR', 'SINGH', 'SHARMA', 'VERMA', 'GUPTA', 'YADAV',
            'PANDEY', 'TIWARI', 'MISHRA', 'CHAUDHARY', 'CHOWDHURY',
            'RAJESH', 'RAMESH', 'MAHESH', 'SURESH', 'RAKESH', 'MOHIT',
            'AMIT', 'SUMIT', 'ROHIT', 'NEERAJ', 'MANOJ', 'SANJAY',
        ]
        upper = cleaned.upper()
        for part in common_parts:
            if upper.endswith(part) and len(upper) > len(part):
                first = upper[:-len(part)]
                if len(first) >= 3:
                    return first + ' ' + part
        if len(cleaned) >= 8:
            mid = len(cleaned) // 2
            for offset in range(-2, 3):
                pos = mid + offset
                if 3 <= pos <= len(cleaned) - 3:
                    candidate = cleaned[:pos] + ' ' + cleaned[pos:]
                    words = candidate.split()
                    if all(w[0].isupper() for w in words if w):
                        return candidate
        return None

    def score_pan_name(cw):
        avg_len = sum(len(w) for w in cw) / len(cw)
        has_lower = any(any(c.islower() for c in w[1:]) for w in cw)
        return avg_len + (5 if has_lower else 0)

    mid_y = img_h / 2
    father_cy = None
    for it in items:
        if re.search(r'father', it['text'], re.IGNORECASE):
            father_cy = it['cy']
            break

    for it in items:
        if it['cy'] >= mid_y:
            continue
        if father_cy and it['cy'] > father_cy:
            continue
        t = it['text']
        if 'income' in t.lower() or 'tax' in t.lower() or 'department' in t.lower():
            continue
        if 'government' in t.lower():
            continue
        if re.search(r'\b(dob|date|birth|father|mother|signature|india|card|name)\b', t, re.IGNORECASE):
            continue
        if any(re.search(p, t, re.IGNORECASE) for p in pan_skip_patterns):
            continue
        if _is_date_text(t):
            continue
        words = t.split()
        cw = [_clean(w) for w in words if _clean(w)]
        if is_good_pan_name(cw):
            pan_candidates.append((score_pan_name(cw), ' '.join(cw).title()))
        elif len(cw) == 1 and cw[0] and len(cw[0]) >= 4:
            split = _try_split_concatenated(cw[0])
            if split:
                pan_candidates.append((score_pan_name(split.split()), split.title()))

    if pan_candidates:
        pan_candidates.sort(key=lambda x: -x[0])
        details['name'] = pan_candidates[0][1]

    gender = None
    for it in items:
        t = it['text'].strip().upper()
        if t == 'MALE' or t == 'FEMALE' or t == 'OTHER':
            gender = t.title()
            break
    if not gender:
        for it in items:
            t = it['text'].strip().upper()
            if 'MALE' in t and 'FEMALE' not in t:
                gender = 'Male'
                break
            elif 'FEMALE' in t:
                gender = 'Female'
                break
    if gender:
        details['gender'] = gender

    details['address'] = ''
    details['address_components'] = {'full_address': '', 'house_number': '', 'street': '', 'locality': '',
                                      'city_or_village': '', 'district': '', 'state': '', 'pin_code': '', 'confidence_score': 0.0}

    debug['extracted_name'] = details.get('name')
    debug['extracted_gender'] = gender
    return details


def _sanitize(obj):
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    elif isinstance(obj, str):
        return re.sub(r'[\x00-\x1f\x7f\\]', ' ', obj)
    return obj


def _calc_confidence(details, doc_type='AADHAAR'):
    expected = ['name', 'id_number', 'dob'] if doc_type.upper() == 'AADHAAR' else ['name', 'id_number', 'dob']
    found = sum(1 for f in expected if details.get(f))
    return round((found / len(expected)) * 100, 2)


if __name__ == '__main__':
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else 'test.jpg'
    dtype = sys.argv[2] if len(sys.argv) > 2 else 'AADHAAR'
    with open(path, 'rb') as f:
        result = ocr_image(f.read(), dtype)
    print(json.dumps(result, indent=2, ensure_ascii=False))
