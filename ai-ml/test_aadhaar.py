import re

test_cases = [
    ("1234 5678 9012", "123456789012", "standard spaced Aadhaar"),
    ("123456789012", "123456789012", "no spaces Aadhaar"),
    ("1234-5678-9012", "123456789012", "dash separated"),
    ("g0a / 231020041234", None, "DOB+AAD merged - not 12 standalone"),
    ("2310 2004 1234 5678 9012", "123456789012", "spaced DOB + Aadhaar"),
    ("DOB 23/10/2004 1234 5678 9012", "123456789012", "DOB label + Aadhaar"),
    ("23/10/2004123456789012", "123456789012", "DOB with sep + Aadhaar"),
    ("15/07/2001 g0a /", None, "DOB only"),
    ("08092004123456789012", "123456789012", "compact DOB + Aadhaar"),
    ("01012000987654321098", "987654321098", "compact DOB 01012000 + Aadhaar"),
]

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

def extract_aadhaar(text):
    d = re.sub(r'\D', '', text)
    if _is_valid_aadhaar(d):
        return d
    cleaned = _strip_dob_digits(text)
    if _is_valid_aadhaar(cleaned):
        return cleaned
    if len(cleaned) > 12:
        for i in range(len(cleaned) - 11):
            sub = cleaned[i:i + 12]
            if _is_valid_aadhaar(sub):
                return sub
    return None

for text, expected, desc in test_cases:
    result = extract_aadhaar(text)
    status = "OK" if str(result) == str(expected) else "FAIL"
    print(f"[{status}] {desc}")
    print(f"  Input:    '{text}'")
    print(f"  Expected: {expected}")
    print(f"  Got:      {result}")
    print()
