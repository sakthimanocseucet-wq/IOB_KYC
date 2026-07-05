package com.iob.kyc.service;

import com.iob.kyc.model.DeviceFingerprint;
import com.iob.kyc.model.FraudAlert;
import com.iob.kyc.model.KYCApplication;
import com.iob.kyc.repository.DeviceFingerprintRepository;
import com.iob.kyc.repository.FraudAlertRepository;
import com.iob.kyc.repository.KYCApplicationRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Service
public class FraudDetectionService {

    private final DeviceFingerprintRepository deviceFingerprintRepository;
    private final FraudAlertRepository fraudAlertRepository;
    private final KYCApplicationRepository kycApplicationRepository;

    public FraudDetectionService(DeviceFingerprintRepository deviceFingerprintRepository,
                                  FraudAlertRepository fraudAlertRepository,
                                  KYCApplicationRepository kycApplicationRepository) {
        this.deviceFingerprintRepository = deviceFingerprintRepository;
        this.fraudAlertRepository = fraudAlertRepository;
        this.kycApplicationRepository = kycApplicationRepository;
    }

    public boolean checkMultipleAccounts(String ipAddress, String deviceFingerprint) {
        return deviceFingerprintRepository.findByFingerprintHash(deviceFingerprint).isPresent();
    }

    public boolean checkGeolocationAnomaly(String ipAddress, String lastKnownLocation) {
        return false;
    }

    public int calculateRiskScore(KYCApplication app) {
        int score = 0;

        if (app.getRiskLevel() == KYCApplication.RiskLevel.HIGH) {
            score += 40;
        } else if (app.getRiskLevel() == KYCApplication.RiskLevel.MEDIUM) {
            score += 20;
        }

        if (app.getFaceMatchPercentage() != null && app.getFaceMatchPercentage().doubleValue() < 80.0) {
            score += 30;
        }

        if (!app.isLivenessPassed()) {
            score += 20;
        }

        return Math.min(score, 100);
    }

    public Map<String, Object> checkDuplicates(KYCApplication app) {
        Map<String, Object> result = new HashMap<>();
        List<String> issues = new ArrayList<>();
        boolean suspicious = false;

        if (app.getOcrIdNumber() != null && !app.getOcrIdNumber().isEmpty()) {
            List<KYCApplication> dups = kycApplicationRepository.findByOcrIdNumberExcludingId(
                    app.getOcrIdNumber(), app.getId() != null ? app.getId() : 0L);
            if (!dups.isEmpty()) {
                suspicious = true;
                issues.add("Duplicate Aadhaar: " + app.getOcrIdNumber() + " found in " + dups.size() + " other application(s)");
            }
        }

        if (app.getOcrPanNumber() != null && !app.getOcrPanNumber().isEmpty()) {
            List<KYCApplication> panDups = kycApplicationRepository.findByOcrPanNumberExcludingId(
                    app.getOcrPanNumber(), app.getId() != null ? app.getId() : 0L);
            if (!panDups.isEmpty()) {
                suspicious = true;
                issues.add("Duplicate PAN: " + app.getOcrPanNumber() + " found in " + panDups.size() + " other application(s)");
            }
        }

        if (app.getIpAddress() != null && !app.getIpAddress().isEmpty()) {
            List<KYCApplication> ipDups = kycApplicationRepository.findByIpAddressExcludingId(
                    app.getIpAddress(), app.getId() != null ? app.getId() : 0L);
            if (ipDups.size() >= 3) {
                suspicious = true;
                issues.add("Multiple applications (" + (ipDups.size() + 1) + ") from same IP: " + app.getIpAddress());
            }
        }

        result.put("is_suspicious", suspicious);
        result.put("issues", issues);
        return result;
    }

    @Transactional
    public FraudAlert createFraudAlert(Long applicationId, String alertType, String severity, String description) {
        FraudAlert alert = FraudAlert.builder()
                .applicationId(applicationId)
                .alertType(FraudAlert.AlertType.valueOf(alertType))
                .severity(FraudAlert.Severity.valueOf(severity))
                .description(description)
                .resolved(false)
                .createdAt(LocalDateTime.now())
                .build();
        return fraudAlertRepository.save(alert);
    }
}
