import sys
sys.path.insert(0, '.')
from qr_verification import parse_aadhaar_qr, parse_pan_qr

tests = [
    ("XML attr", "PrintLetterBarcodeData uid=\"654782139654\" name=\"ARJUN MEHRA\" dob=\"22/08/2000\" gender=\"M\""),
    ("JSON", '{"uid":"654782139654","name":"ARJUN MEHRA","dob":"22/08/2000","gender":"M"}'),
    ("XML tags", "<uid>654782139654</uid><name>ARJUN MEHRA</name><dob>22/08/2000</dob>"),
    ("Pipe", "654782139654|ARJUN MEHRA|22/08/2000|M"),
    ("UIDAI XML", '<?xml version="1.0" encoding="UTF-8"?><PrintLetterBarcodeData uid="654782139654" name="ARJUN MEHRA" dob="22/08/2000" gender="M"/>'),
    ("UIDAI with extra attrs", '<PrintLetterBarcodeData uid="654782139654" name="ARJUN MEHRA" dob="22/08/2000" gender="M" phone="" email=""/>'),
    ("No name tag", '<uid>654782139654</uid><dob>22/08/2000</dob>'),
    ("Plain text", "ARJUN MEHRA 654782139654 22/08/2000"),
]

for label, data in tests:
    result = parse_aadhaar_qr(data)
    print(f"[{label}] name='{result['name']}' dob='{result['dob']}' aadhaar='{result['aadhaar_number']}'")
