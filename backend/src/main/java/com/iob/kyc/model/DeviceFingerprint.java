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
@Table(name = "device_fingerprints")
public class DeviceFingerprint {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private Long userId;

    @Column(nullable = false)
    private String fingerprintHash;

    private String deviceName;

    private String os;

    private String browser;

    private String ipAddress;

    private String userAgent;

    private boolean trusted;

    private LocalDateTime firstSeen;

    private LocalDateTime lastSeen;
}
