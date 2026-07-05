"""
Fraud Detection Module
Detects suspicious patterns including multiple accounts,
rapid login attempts, and geolocation anomalies.
"""

import json
import time
from collections import defaultdict
from datetime import datetime, timedelta


class FraudDetector:
    def __init__(self):
        self.login_attempts = defaultdict(list)
        self.MAX_LOGIN_ATTEMPTS = 10
        self.MAX_LOGIN_WINDOW = 60
        self.SAME_IP_LIMIT = 3

    def check_multiple_accounts(self, ip_address, device_fingerprint,
                                 existing_accounts):
        """
        Check if multiple accounts are being created from same device/IP.

        Args:
            ip_address: str
            device_fingerprint: str
            existing_accounts: list of dicts with 'ip' and 'fingerprint' keys

        Returns:
            dict with is_suspicious, reason, risk_score
        """
        same_ip_count = sum(
            1 for acc in existing_accounts
            if acc.get('ip') == ip_address
        )
        same_device_count = sum(
            1 for acc in existing_accounts
            if acc.get('fingerprint') == device_fingerprint
        )

        risk_score = 0
        reasons = []

        if same_ip_count >= self.SAME_IP_LIMIT:
            risk_score += 40
            reasons.append(f"Multiple accounts ({same_ip_count}) from same IP")

        if same_device_count >= 2:
            risk_score += 50
            reasons.append(f"Multiple accounts ({same_device_count}) from same device")

        if same_ip_count >= 5:
            risk_score += 30
            reasons.append("Mass account creation detected from single IP")

        return {
            'is_suspicious': risk_score >= 40,
            'risk_score': min(risk_score, 100),
            'reasons': reasons,
            'same_ip_count': same_ip_count,
            'same_device_count': same_device_count
        }

    def check_rapid_login(self, user_id, ip_address):
        """
        Detect rapid or repeated login attempts.

        Args:
            user_id: str
            ip_address: str

        Returns:
            dict with is_attack, attempts_in_window, risk_score
        """
        now = time.time()
        key = f"{user_id}:{ip_address}"

        self.login_attempts[key] = [
            t for t in self.login_attempts[key]
            if now - t < self.MAX_LOGIN_WINDOW
        ]

        self.login_attempts[key].append(now)
        recent_count = len(self.login_attempts[key])

        risk_score = 0
        is_attack = False

        if recent_count > self.MAX_LOGIN_ATTEMPTS:
            risk_score = 90
            is_attack = True
        elif recent_count > 5:
            risk_score = 50
        elif recent_count > 3:
            risk_score = 25

        return {
            'is_attack': is_attack,
            'attempts_in_window': recent_count,
            'window_seconds': self.MAX_LOGIN_WINDOW,
            'risk_score': risk_score
        }

    def check_geolocation_anomaly(self, ip_address, last_known_ip=None):
        """
        Detect geolocation anomalies based on IP changes.
        """
        if not last_known_ip:
            return {'is_anomalous': False, 'risk_score': 0}

        if ip_address != last_known_ip:
            return {
                'is_anomalous': True,
                'risk_score': 30,
                'reason': f"IP address changed from {last_known_ip} to {ip_address}"
            }

        return {'is_anomalous': False, 'risk_score': 0}

    def check_device_mismatch(self, current_fingerprint, known_fingerprints):
        """
        Check if device fingerprint matches known fingerprints for user.
        """
        if current_fingerprint not in known_fingerprints:
            return {
                'is_mismatch': True,
                'risk_score': 35,
                'reason': "Device not recognized for this user"
            }
        return {'is_mismatch': False, 'risk_score': 0}

    def analyze_file_metadata(self, file_data):
        """
        Check file metadata for signs of tampering.
        """
        risk_score = 0
        reasons = []

        if file_data.get('has_exif', False):
            if file_data.get('is_screenshot', False):
                risk_score += 30
                reasons.append("Document appears to be a screenshot")

        if file_data.get('edit_history_count', 0) > 5:
            risk_score += 20
            reasons.append("File has extensive edit history")

        if file_data.get('resolution') and file_data['resolution'] < (500, 500):
            risk_score += 15
            reasons.append("Low resolution document")

        if file_data.get('file_size_mb', 0) > 10:
            risk_score += 10
            reasons.append("Unusually large file size")

        return {
            'is_suspicious': risk_score >= 30,
            'risk_score': min(risk_score, 100),
            'reasons': reasons
        }

    def assess_overall_risk(self, checks):
        """
        Combine all fraud checks into an overall risk assessment.
        """
        total = sum(check.get('risk_score', 0) for check in checks.values())
        avg = total / max(len(checks), 1)

        severity = 'LOW'
        if avg >= 70:
            severity = 'HIGH'
        elif avg >= 40:
            severity = 'MEDIUM'

        triggered = [
            {
                'check': name,
                'risk_score': check.get('risk_score', 0),
                'details': check.get('reasons', check.get('reason', ''))
            }
            for name, check in checks.items()
            if check.get('risk_score', 0) >= 30
        ]

        return {
            'overall_risk_score': min(round(avg), 100),
            'severity': severity,
            'triggers': triggered,
            'needs_review': avg >= 40,
            'block_access': avg >= 80,
            'assessed_at': datetime.now().isoformat()
        }


if __name__ == '__main__':
    detector = FraudDetector()

    accounts = [
        {'ip': '192.168.1.100', 'fingerprint': 'fp_abc123'},
        {'ip': '192.168.1.100', 'fingerprint': 'fp_def456'},
    ]

    multi = detector.check_multiple_accounts('192.168.1.100', 'fp_xyz789', accounts)
    rapid = detector.check_rapid_login('user_001', '10.0.0.55')

    overall = detector.assess_overall_risk({
        'multiple_accounts': multi,
        'rapid_login': rapid,
    })

    print(json.dumps(overall, indent=2))
