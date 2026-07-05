package com.iob.kyc.model;

import jakarta.persistence.*;
import lombok.*;
import java.time.LocalDateTime;

@Entity
@Table(name = "risk_scores")
@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class RiskScore {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "application_id", nullable = false)
    private KYCApplication application;

    @Column(name = "device_fingerprint_score")
    private int deviceFingerprintScore;

    @Column(name = "ip_reputation_score")
    private int ipReputationScore;

    @Column(name = "geolocation_score")
    private int geolocationScore;

    @Column(name = "face_match_score")
    private int faceMatchScore;

    @Column(name = "behavioral_score")
    private int behavioralScore;

    @Column(name = "total_score")
    private int totalScore;

    @Column(name = "assessed_at")
    private LocalDateTime assessedAt;

    @PrePersist
    protected void onCreate() { assessedAt = LocalDateTime.now(); }
}
