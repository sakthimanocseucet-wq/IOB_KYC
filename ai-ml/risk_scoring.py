"""
AI Risk Scoring Module
Calculates risk scores for KYC applications based on multiple factors.
"""

import json
import math
from datetime import datetime


class RiskScorer:
    def __init__(self):
        self.weights = {
            'face_match': 0.30,
            'device_fingerprint': 0.20,
            'ip_reputation': 0.20,
            'geolocation': 0.15,
            'behavioral': 0.15
        }

    def score_face_match(self, face_confidence):
        """Score based on face match confidence (0-100 scale)."""
        if face_confidence >= 90:
            return 5
        elif face_confidence >= 80:
            return 15
        elif face_confidence >= 70:
            return 30
        elif face_confidence >= 50:
            return 50
        else:
            return 75

    def score_device_fingerprint(self, device_data):
        """Score based on device fingerprinting analysis."""
        risk = 0
        if device_data.get('is_vm', False):
            risk += 30
        if device_data.get('is_proxy', False):
            risk += 25
        if device_data.get('is_tor', False):
            risk += 40
        if device_data.get('multiple_sessions', 0) > 3:
            risk += 20
        if device_data.get('screen_resolution_anomaly', False):
            risk += 10
        if device_data.get('timezone_mismatch', False):
            risk += 15
        return min(risk, 100)

    def score_ip_reputation(self, ip_data):
        """Score based on IP reputation analysis."""
        risk = 0
        if ip_data.get('is_vpn', False):
            risk += 30
        if ip_data.get('is_datacenter', False):
            risk += 20
        if ip_data.get('is_unknown', False):
            risk += 25
        if ip_data.get('abuse_score', 0) > 50:
            risk += 25
        if ip_data.get('is_tor_exit', False):
            risk += 40
        return min(risk, 100)

    def score_geolocation(self, geo_data):
        """Score based on geolocation analysis."""
        risk = 0
        if geo_data.get('distance_km', 0) > 1000:
            risk += 25
        if geo_data.get('country_change', False):
            risk += 30
        if geo_data.get('timezone_mismatch', False):
            risk += 20
        if geo_data.get('high_risk_country', False):
            risk += 35
        if geo_data.get('gps_mismatch', False):
            risk += 25
        return min(risk, 100)

    def score_behavioral(self, behavior_data):
        """Score based on behavioral biometrics."""
        risk = 0
        if behavior_data.get('typing_speed_anomaly', False):
            risk += 20
        if behavior_data.get('mouse_movement_anomaly', False):
            risk += 15
        if behavior_data.get('form_filling_time_too_fast', False):
            risk += 25
        if behavior_data.get('copy_paste_detected', False):
            risk += 15
        if behavior_data.get('multiple_attempts', 0) > 2:
            risk += 25
        return min(risk, 100)

    def calculate(self, face_data=None, device_data=None,
                  ip_data=None, geo_data=None, behavior_data=None):
        """
        Calculate overall risk score from all factors.

        Args:
            face_data: dict with 'confidence' key
            device_data: dict with fingerprinting info
            ip_data: dict with IP reputation info
            geo_data: dict with geolocation info
            behavior_data: dict with behavioral biometrics

        Returns:
            dict with total_score, risk_level, and breakdown
        """
        scores = {}

        if face_data:
            scores['face_match'] = self.score_face_match(
                face_data.get('confidence', 0)
            )

        if device_data:
            scores['device_fingerprint'] = self.score_device_fingerprint(device_data)

        if ip_data:
            scores['ip_reputation'] = self.score_ip_reputation(ip_data)

        if geo_data:
            scores['geolocation'] = self.score_geolocation(geo_data)

        if behavior_data:
            scores['behavioral'] = self.score_behavioral(behavior_data)

        if not scores:
            return {
                'total_score': 0,
                'risk_level': 'LOW',
                'breakdown': {},
                'assessed_at': datetime.now().isoformat()
            }

        total = sum(
            scores.get(key, 0) * self.weights.get(key, 0)
            for key in self.weights
        )
        total = min(max(round(total), 0), 100)

        if total < 30:
            level = 'LOW'
        elif total < 60:
            level = 'MEDIUM'
        else:
            level = 'HIGH'

        return {
            'total_score': total,
            'risk_level': level,
            'breakdown': scores,
            'weights_used': self.weights,
            'assessed_at': datetime.now().isoformat()
        }

    def get_risk_label(self, score):
        """Get risk label for a score."""
        if score < 30:
            return 'LOW'
        elif score < 60:
            return 'MEDIUM'
        else:
            return 'HIGH'


if __name__ == '__main__':
    scorer = RiskScorer()
    result = scorer.calculate(
        face_data={'confidence': 92},
        device_data={'is_vm': False, 'is_proxy': False, 'timezone_mismatch': True},
        ip_data={'is_vpn': True, 'abuse_score': 30},
        geo_data={'distance_km': 500, 'country_change': False},
        behavior_data={'typing_speed_anomaly': False, 'form_filling_time_too_fast': True}
    )
    print(json.dumps(result, indent=2))
