package com.iob.kyc.model;

import jakarta.persistence.*;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
@Entity
@Table(name = "fraud_alerts")
public class FraudAlert {

    public enum AlertType {
        MULTIPLE_ACCOUNTS, RAPID_LOGIN, GEO_ANOMALY, DEVICE_MISMATCH, SUSPICIOUS_FILE,
        DEEPFAKE_DETECTED, DUPLICATE_AADHAAR, DUPLICATE_PAN, MULTIPLE_IP
    }

    public enum Severity {
        LOW, MEDIUM, HIGH
    }

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private Long applicationId;

    @Enumerated(EnumType.STRING)
    private AlertType alertType;

    @Enumerated(EnumType.STRING)
    private Severity severity;

    @Column(columnDefinition = "TEXT")
    private String description;

    private boolean resolved;

    private Long resolvedBy;

    private LocalDateTime resolvedAt;

    private LocalDateTime createdAt;
}
